"""Imputation de la consommation et agrégats horaires calculés depuis les seules données brutes."""

import os
from datetime import UTC, datetime, timedelta

import psycopg

_UPSERT_HOURS = """
    INSERT INTO readings_hours (
        site_id, ts, consumption_kwh, voltage_v, current_a,
        power_factor, temperature_celsius, humidity_percent,
        minutes_received, minutes_consumption, minutes_backfilled
    )
    SELECT
        sites.site_id,
        hours.start,
        round(avg(raw.consumption_kw::numeric), 2),
        round(avg(raw.voltage_v::numeric), 2),
        round(avg(raw.current_a::numeric), 2),
        round(avg(raw.power_factor::numeric), 2),
        round(avg(raw.temperature_celsius::numeric), 2),
        round(avg(raw.humidity_percent::numeric), 2),
        count(raw.ts),
        count(raw.consumption_kw),
        count(raw.ts) FILTER (WHERE raw.source = 'backfill')
    FROM sites
    CROSS JOIN generate_series(
        %(first)s::timestamptz, %(last)s::timestamptz, interval '1 hour'
    ) AS hours(start)
    LEFT JOIN readings_raws AS raw
        ON raw.site_id = sites.site_id
        AND raw.ts >= hours.start
        AND raw.ts < hours.start + interval '1 hour'
    GROUP BY sites.site_id, hours.start
    ON CONFLICT (site_id, ts) DO UPDATE SET
        consumption_kwh = EXCLUDED.consumption_kwh,
        voltage_v = EXCLUDED.voltage_v,
        current_a = EXCLUDED.current_a,
        power_factor = EXCLUDED.power_factor,
        temperature_celsius = EXCLUDED.temperature_celsius,
        humidity_percent = EXCLUDED.humidity_percent,
        minutes_received = EXCLUDED.minutes_received,
        minutes_consumption = EXCLUDED.minutes_consumption,
        minutes_backfilled = EXCLUDED.minutes_backfilled
"""


def aggregate_hour(
    database_url: str | None = None,
    *,
    end_time: datetime | None = None,
    hours: int = 1,
    connect_timeout: int = 10,
) -> int:
    """Recalcule les dernières heures terminées et retourne le nombre de lignes écrites.

    end_time, ou l'heure courante par défaut, est ramené au début de son heure
    en UTC ; les hours heures qui précèdent sont recalculées (une ligne par site
    et par heure). Chaque fenêtre inclut son début et exclut sa fin. Une référence
    explicite doit comporter un fuseau horaire.

    La puissance moyenne des valeurs non nulles est supposée représentative
    de l'heure entière : énergie estimée = avg(consumption_kw) × 1 heure.
    Une heure incomplète est donc estimée depuis les seules valeurs disponibles.
    L'énergie reste NULL seulement si aucune puissance n'est disponible.
    consumption_kwh brut n'est pas utilisé.
    Les autres indicateurs sont moyennés indépendamment, en ignorant leurs NULL.
    Les calculs décimaux gardent leur précision jusqu'à l'arrondi final à 2 décimales.
    Un site sans mesure reçoit une ligne dont tous les indicateurs sont NULL.
    Complétude : minutes_received (lignes reçues), minutes_consumption (dont
    consommation non NULL) et minutes_backfilled (dont rattrapées) ; 0 signifie
    qu'aucune mesure n'a été reçue.
    Le lot est validé en une transaction et les lignes existantes sont recalculées.
    """
    if hours < 1:
        raise ValueError("hours doit valoir au moins 1.")
    reference = end_time if end_time is not None else datetime.now(UTC)
    if reference.utcoffset() is None:
        raise ValueError("end_time doit comporter un fuseau horaire.")
    window_end = reference.astimezone(UTC).replace(
        minute=0, second=0, microsecond=0
    )

    connection_url = (
        database_url if database_url is not None else os.environ.get("DATABASE_URL", "")
    ).strip()
    if not connection_url:
        raise ValueError("Renseigner DATABASE_URL ou passer une URL à aggregate_hour.")

    with psycopg.connect(connection_url, connect_timeout=connect_timeout) as connection, connection.cursor() as cursor:
        cursor.execute(_UPSERT_HOURS, {
            "first": window_end - timedelta(hours=hours),
            "last": window_end - timedelta(hours=1),
        })
        return cursor.rowcount


# Stratégies du sujet (PDF 04 p. 13) : valeur précédente pour les consommations
# stables, interpolation linéaire pour une panne courte (< 3 mesures) ailleurs.
STABLE_SITE_TYPES = ("datacenter", "hospital")
PREVIOUS_VALUE_MAX_AGE = timedelta(minutes=15)
LINEAR_MAX_SPAN = timedelta(minutes=3)

_IMPUTE_CONSUMPTION = """
    WITH candidates AS (
        SELECT raw.site_id, raw.ts, sites.site_type = ANY(%(stable)s) AS stable,
               prev.ts AS prev_ts, prev.kw AS prev_kw,
               next.ts AS next_ts, next.kw AS next_kw
        FROM readings_raws AS raw
        JOIN sites USING (site_id)
        LEFT JOIN LATERAL (
            SELECT p.ts, p.consumption_kw AS kw
            FROM readings_raws AS p
            WHERE p.site_id = raw.site_id
              AND p.ts < raw.ts AND p.ts >= raw.ts - %(max_age)s
              AND p.consumption_kw IS NOT NULL
            ORDER BY p.ts DESC
            LIMIT 1
        ) AS prev ON true
        LEFT JOIN LATERAL (
            SELECT n.ts, n.consumption_kw AS kw
            FROM readings_raws AS n
            WHERE n.site_id = raw.site_id
              AND n.ts > raw.ts AND n.ts <= raw.ts + %(max_span)s
              AND n.consumption_kw IS NOT NULL
            ORDER BY n.ts
            LIMIT 1
        ) AS next ON true
        WHERE raw.ts >= %(start)s AND raw.ts < %(end)s
          AND raw.consumption_kw IS NULL
          AND raw.consumption_kw_imputed IS NULL
    ),
    resolved AS (
        SELECT site_id, ts,
               CASE WHEN stable THEN prev_kw
                    ELSE prev_kw + (next_kw - prev_kw)
                         * extract(epoch FROM ts - prev_ts) / extract(epoch FROM next_ts - prev_ts)
               END AS kw,
               CASE WHEN stable THEN 'previous_value' ELSE 'linear' END AS method
        FROM candidates
        WHERE prev_ts IS NOT NULL
          AND (stable OR (next_ts IS NOT NULL AND next_ts - prev_ts <= %(max_span)s))
    )
    UPDATE readings_raws AS raw
    SET consumption_kw_imputed = round(resolved.kw::numeric, 2)::double precision,
        imputation_method = resolved.method
    FROM resolved
    WHERE raw.site_id = resolved.site_id AND raw.ts = resolved.ts
"""


def impute_consumption(
    database_url: str | None = None,
    *,
    minutes: int,
    end_time: datetime | None = None,
    connect_timeout: int = 10,
) -> int:
    """Impute les consommations NULL des dernières minutes et retourne le nombre de lignes imputées.

    La fenêtre [end_time − minutes, end_time) porte sur les lignes à imputer ;
    leurs voisines peuvent être plus anciennes. La valeur brute reste NULL :
    le résultat va dans consumption_kw_imputed, avec sa méthode.
    - datacenter, hôpital : dernière valeur brute d'au plus 15 min (previous_value) ;
    - autres sites : interpolation entre les valeurs brutes qui encadrent la minute,
      distantes d'au plus 3 min (linear), soit au plus 2 minutes manquantes,
      lignes absentes comprises. Sans valeur suivante, la ligne est retentée
      au passage suivant.
    Seules des valeurs brutes servent de base, jamais une valeur déjà imputée.
    Une ligne déjà imputée n'est pas recalculée : la fonction peut être relancée.
    """
    if minutes < 1:
        raise ValueError("minutes doit valoir au moins 1.")
    reference = end_time if end_time is not None else datetime.now(UTC)
    if reference.utcoffset() is None:
        raise ValueError("end_time doit comporter un fuseau horaire.")

    connection_url = (
        database_url if database_url is not None else os.environ.get("DATABASE_URL", "")
    ).strip()
    if not connection_url:
        raise ValueError("Renseigner DATABASE_URL ou passer une URL à impute_consumption.")

    with psycopg.connect(connection_url, connect_timeout=connect_timeout) as connection, connection.cursor() as cursor:
        cursor.execute(_IMPUTE_CONSUMPTION, {
            "start": reference - timedelta(minutes=minutes),
            "end": reference,
            "stable": list(STABLE_SITE_TYPES),
            "max_age": PREVIOUS_VALUE_MAX_AGE,
            "max_span": LINEAR_MAX_SPAN,
        })
        return cursor.rowcount
