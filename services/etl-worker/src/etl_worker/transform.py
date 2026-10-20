"""Calcul et chargement des agrégats horaires depuis les seules données brutes."""

import os
from datetime import datetime, timedelta, timezone

import psycopg


_UPSERT_HOUR = """
    INSERT INTO readings_hours (
        site_id, ts, consumption_kwh, voltage_v, current_a,
        power_factor, temperature_celsius, humidity_percent
    )
    SELECT
        sites.site_id,
        %(start)s::timestamptz,
        round(avg(raw.consumption_kw::numeric), 2),
        round(avg(raw.voltage_v::numeric), 2),
        round(avg(raw.current_a::numeric), 2),
        round(avg(raw.power_factor::numeric), 2),
        round(avg(raw.temperature_celsius::numeric), 2),
        round(avg(raw.humidity_percent::numeric), 2)
    FROM sites
    LEFT JOIN readings_raws AS raw
        ON raw.site_id = sites.site_id
        AND raw.ts >= %(start)s
        AND raw.ts < %(end)s
    GROUP BY sites.site_id
    ON CONFLICT (site_id, ts) DO UPDATE SET
        consumption_kwh = EXCLUDED.consumption_kwh,
        voltage_v = EXCLUDED.voltage_v,
        current_a = EXCLUDED.current_a,
        power_factor = EXCLUDED.power_factor,
        temperature_celsius = EXCLUDED.temperature_celsius,
        humidity_percent = EXCLUDED.humidity_percent
"""


def aggregate_hour(
    database_url: str | None = None,
    *,
    end_time: datetime | None = None,
    connect_timeout: int = 10,
) -> int:
    """Recalcule la dernière heure terminée et retourne le nombre de sites traités.

    end_time, ou l'heure courante par défaut, est ramené au début de son heure
    en UTC. La fenêtre inclut son début et exclut sa fin. Une référence explicite
    doit comporter un fuseau horaire.

    La puissance moyenne des valeurs non nulles est supposée représentative
    de l'heure entière : énergie estimée = avg(consumption_kw) × 1 heure.
    Une heure incomplète est donc estimée depuis les seules valeurs disponibles.
    L'énergie reste NULL seulement si aucune puissance n'est disponible.
    consumption_kwh brut n'est pas utilisé.
    Les autres indicateurs sont moyennés indépendamment, en ignorant leurs NULL.
    Les calculs décimaux gardent leur précision jusqu'à l'arrondi final à 2 décimales.
    Un site sans mesure reçoit une ligne dont tous les indicateurs sont NULL.
    Le lot est validé en une transaction et les lignes existantes sont recalculées.
    """
    reference = end_time if end_time is not None else datetime.now(timezone.utc)
    if reference.utcoffset() is None:
        raise ValueError("end_time doit comporter un fuseau horaire.")
    window_end = reference.astimezone(timezone.utc).replace(
        minute=0, second=0, microsecond=0
    )
    window_start = window_end - timedelta(hours=1)

    connection_url = (
        database_url if database_url is not None else os.environ.get("DATABASE_URL", "")
    ).strip()
    if not connection_url:
        raise ValueError("Renseigner DATABASE_URL ou passer une URL à aggregate_hour.")

    with psycopg.connect(connection_url, connect_timeout=connect_timeout) as connection:
        with connection.cursor() as cursor:
            cursor.execute(_UPSERT_HOUR, {"start": window_start, "end": window_end})
            return cursor.rowcount
