import argparse
import logging
import os
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from typing import Any

import psycopg

from etl_worker.extract import extract_alerts
from etl_worker.timestamps import parse_reading_timestamp

_UPSERT_SITE = """
    INSERT INTO sites (site_id, site_name, site_type, location, capacity_kw, status)
    VALUES (%s, %s, %s, %s, %s, %s)
    ON CONFLICT (site_id) DO UPDATE SET
        site_name = EXCLUDED.site_name,
        site_type = EXCLUDED.site_type,
        location = EXCLUDED.location,
        capacity_kw = EXCLUDED.capacity_kw,
        status = EXCLUDED.status,
        updated_at = now()
    WHERE (
        sites.site_name, sites.site_type, sites.location,
        sites.capacity_kw, sites.status
    ) IS DISTINCT FROM (
        EXCLUDED.site_name, EXCLUDED.site_type, EXCLUDED.location,
        EXCLUDED.capacity_kw, EXCLUDED.status
    )
"""

#Insère les sites nouveaux et met à jour uniquement les sites modifiés.
#Le résultat est le nombre de sites insérés ou modifiés ; les sites identiques sont ignorés.
#Le lot est validé en une transaction, annulée entièrement en cas d'erreur.
def load_sites(
    sites: Sequence[Mapping[str, Any]],
    database_url: str | None = None,
    *,
    connect_timeout: int = 10,
) -> int:
    if not sites:
        return 0

    connection_url = (
        database_url if database_url is not None else os.environ.get("DATABASE_URL", "")
    ).strip()
    if not connection_url:
        raise ValueError("Renseigner DATABASE_URL ou passer une URL à load_sites.")

    rows = [
        (
            site["site_id"],
            site["site_name"],
            site["site_type"],
            site.get("location"),
            site["capacity_kw"],
            site["status"],
        )
        for site in sites
    ]

    with psycopg.connect(connection_url, connect_timeout=connect_timeout) as connection, connection.cursor() as cursor:
            cursor.executemany(_UPSERT_SITE, rows)
            return cursor.rowcount

_INSERT_READING = """
    INSERT INTO readings_raws (
        site_id, ts, site_type, consumption_kw, consumption_kwh, voltage_v, current_a,
        power_factor, temperature_celsius, humidity_percent, null_reasons,
        data_quality
    )
    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
    ON CONFLICT (site_id, ts) DO NOTHING
"""


_PREVIOUS_CONSUMPTIONS = """
    SELECT
        (SELECT consumption_kw FROM readings_raws
         WHERE site_id = %(site_id)s AND ts < %(ts)s
           AND consumption_kw IS NOT NULL
         ORDER BY ts DESC LIMIT 1),
        (SELECT consumption_kwh FROM readings_raws
         WHERE site_id = %(site_id)s AND ts < %(ts)s
           AND consumption_kwh IS NOT NULL
         ORDER BY ts DESC LIMIT 1)
"""

_CONSUMPTION_FIELDS = ("consumption_kw", "consumption_kwh")
_logger = logging.getLogger(__name__)


def _reading_row(reading: Mapping[str, Any]) -> tuple[Any, ...]:
    return (
        reading["site_id"], reading["timestamp"], reading["site_type"],
        reading.get("consumption_kw"), reading.get("consumption_kwh"),
        reading.get("voltage_v"), reading.get("current_a"),
        reading.get("power_factor"), reading.get("temperature_celsius"),
        reading.get("humidity_percent"), reading.get("null_reasons", []),
        reading["data_quality"],
    )


def _fill_consumptions(cursor, reading: dict[str, Any]) -> None:
    missing = [field for field in _CONSUMPTION_FIELDS if reading.get(field) is None]
    if not missing:
        return
    cursor.execute(
        _PREVIOUS_CONSUMPTIONS,
        {"site_id": reading["site_id"], "ts": reading["timestamp"]},
    )
    previous = dict(zip(_CONSUMPTION_FIELDS, cursor.fetchone()))
    for field in missing:
        value = previous[field]
        if value is None:
            _logger.warning(
                "%s %s : aucune valeur antérieure pour %s ; NULL conservé.",
                reading["site_id"], reading["timestamp"].isoformat(), field,
            )
        else:
            reading[field] = value
            _logger.info(
                "%s %s : %s repris depuis la dernière valeur non NULL.",
                reading["site_id"], reading["timestamp"].isoformat(), field,
            )


def load_readings(
    readings: Sequence[Mapping[str, Any]],
    database_url: str | None = None,
    *,
    connect_timeout: int = 10,
    fill_consumptions: bool = False,
) -> int:
    """Charge une copie des mesures, avec timestamps UTC sans fractions de seconde.

    Le mode fill_consumptions, activé par sync-readings, reprend chaque
    consommation NULL depuis le même champ du même site strictement antérieur.
    Sans antécédent, NULL est conservé. Les zéros sont des valeurs disponibles.
    Le mode par défaut conserve les NULL pour les imports historiques existants.

    Aucun objet source n'est modifié. Les autres indicateurs et les informations
    de qualité restent ceux de l'API. La clé (site_id, ts) existante est ignorée ;
    une erreur annule toute la transaction. Les lignes sont traitées dans l'ordre
    chronologique afin que le report fonctionne également à l'intérieur du lot.
    """
    if not readings:
        return 0
    connection_url = (
        database_url if database_url is not None else os.environ.get("DATABASE_URL", "")
    ).strip()
    if not connection_url:
        raise ValueError("Renseigner DATABASE_URL ou passer une URL à load_readings.")

    copies = [
        {
            **reading,
            "timestamp": parse_reading_timestamp(reading["timestamp"]).replace(microsecond=0),
        }
        for reading in readings
    ]
    if not fill_consumptions:
        rows = [_reading_row(reading) for reading in copies]
        with psycopg.connect(connection_url, connect_timeout=connect_timeout) as connection, connection.cursor() as cursor:
            cursor.executemany(_INSERT_READING, rows)
            return cursor.rowcount

    copies.sort(key=lambda reading: reading["timestamp"])
    inserted = 0
    with psycopg.connect(connection_url, connect_timeout=connect_timeout) as connection, connection.cursor() as cursor:
        for reading in copies:
            _fill_consumptions(cursor, reading)
            cursor.execute(_INSERT_READING, _reading_row(reading))
            inserted += cursor.rowcount
    return inserted


def read_site_ids(
    database_url: str | None = None, *, connect_timeout: int = 10
) -> list[str]:
    """Lit les sites connus en base sans solliciter l'API des sites."""
    connection_url = (
        database_url if database_url is not None else os.environ.get("DATABASE_URL", "")
    ).strip()
    if not connection_url:
        raise ValueError("Renseigner DATABASE_URL ou passer une URL à read_site_ids.")

    with psycopg.connect(connection_url, connect_timeout=connect_timeout) as connection, connection.cursor() as cursor:
        cursor.execute("SELECT site_id FROM sites ORDER BY site_id")
        return [row[0] for row in cursor.fetchall()]


# Un profil dont le site n'existe pas (encore) en base est ignoré plutôt que de faire échouer le lot.
_UPSERT_SITE_PROFILE = """
    INSERT INTO site_profiles (
        site_id, base_consumption, peak_consumption, working_hour_start, working_hour_end,
        working_days, seasonal_variation, noise_level, weekend_factor, shift_pattern
    )
    SELECT %s, %s, %s, %s, %s, %s::smallint[], %s, %s, %s, %s
    WHERE EXISTS (SELECT 1 FROM sites WHERE sites.site_id = %s)
    ON CONFLICT (site_id) DO UPDATE SET
        base_consumption = EXCLUDED.base_consumption,
        peak_consumption = EXCLUDED.peak_consumption,
        working_hour_start = EXCLUDED.working_hour_start,
        working_hour_end = EXCLUDED.working_hour_end,
        working_days = EXCLUDED.working_days,
        seasonal_variation = EXCLUDED.seasonal_variation,
        noise_level = EXCLUDED.noise_level,
        weekend_factor = EXCLUDED.weekend_factor,
        shift_pattern = EXCLUDED.shift_pattern
    WHERE (
        site_profiles.base_consumption, site_profiles.peak_consumption,
        site_profiles.working_hour_start, site_profiles.working_hour_end,
        site_profiles.working_days, site_profiles.seasonal_variation,
        site_profiles.noise_level, site_profiles.weekend_factor, site_profiles.shift_pattern
    ) IS DISTINCT FROM (
        EXCLUDED.base_consumption, EXCLUDED.peak_consumption,
        EXCLUDED.working_hour_start, EXCLUDED.working_hour_end,
        EXCLUDED.working_days, EXCLUDED.seasonal_variation,
        EXCLUDED.noise_level, EXCLUDED.weekend_factor, EXCLUDED.shift_pattern
    )
"""


def _site_profile_row(profile: Mapping[str, Any]) -> tuple[Any, ...]:
    """Convertit un profil du format source vers les colonnes de site_profiles.

    Jours : 0 = lundi dans la source (weekday() Python), ISO 1 = lundi en base.
    working_hours [début, fin] devient deux colonnes. shift_pattern absent vaut
    false, weekend_factor absent vaut NULL.
    """
    start, end = profile["working_hours"]
    return (
        profile["site_id"],
        profile["base_consumption"],
        profile["peak_consumption"],
        start,
        end,
        [day + 1 for day in profile["working_days"]],
        profile.get("seasonal_variation"),
        profile.get("noise_level"),
        profile.get("weekend_factor"),
        profile.get("shift_pattern", False),
        profile["site_id"],
    )


#Insère les nouveaux profils de référence et met à jour uniquement les profils modifiés.
#Le résultat est le nombre de profils insérés ou modifiés ; identiques ou sans site en base : ignorés.
#Le lot est validé en une transaction, annulée entièrement en cas d'erreur (ex. CHECK).
def load_site_profiles(
    profiles: Sequence[Mapping[str, Any]],
    database_url: str | None = None,
    *,
    connect_timeout: int = 10,
) -> int:
    if not profiles:
        return 0

    connection_url = (
        database_url if database_url is not None else os.environ.get("DATABASE_URL", "")
    ).strip()
    if not connection_url:
        raise ValueError("Renseigner DATABASE_URL ou passer une URL à load_site_profiles.")

    rows = [_site_profile_row(profile) for profile in profiles]

    with psycopg.connect(connection_url, connect_timeout=connect_timeout) as connection, connection.cursor() as cursor:
        cursor.executemany(_UPSERT_SITE_PROFILE, rows)
        return cursor.rowcount


_INSERT_ALERT = """
    INSERT INTO alerts (
        alert_id, "timestamp", site_id, severity, type, message, value, threshold
    )
    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
    ON CONFLICT (alert_id) DO NOTHING
"""


def _alert_timestamp(value: str) -> datetime:
    try:
        timestamp = datetime.fromisoformat(value)
    except (TypeError, ValueError) as error:
        raise ValueError("Timestamp d'alerte invalide.") from error

    if timestamp.utcoffset() is None:
        # Vérifié avec /health et l'en-tête HTTP Date : cette API utilise UTC.
        timestamp = timestamp.replace(tzinfo=UTC)
    return timestamp.astimezone(UTC)

#Insère les nouvelles alertes et retourne le nombre de lignes insérées
#Les huit champs API sont conservés, sans arrondir les nombres.
#Un alert_id existant est ignoré, même si son contenu diffère
#Le lot est validé en une transaction et annulé entièrement en cas d'erreur.
#Une liste vide retourne 0 sans ouvrir de connexion. La table doit exister.
def load_alerts(
    alerts: Sequence[Mapping[str, Any]],
    database_url: str | None = None,
    *,
    connect_timeout: int = 10,
) -> int:

    if not alerts:
        return 0

    connection_url = (
        database_url if database_url is not None else os.environ.get("DATABASE_URL", "")
    ).strip()
    if not connection_url:
        raise ValueError("Renseigner DATABASE_URL ou passer une URL à load_alerts.")

    rows = [
        (
            alert["alert_id"],
            _alert_timestamp(alert["timestamp"]),
            alert["site_id"],
            alert["severity"],
            alert["type"],
            alert["message"],
            alert["value"],
            alert["threshold"],
        )
        for alert in alerts
    ]
    with psycopg.connect(connection_url, connect_timeout=connect_timeout) as connection, connection.cursor() as cursor:
        cursor.executemany(_INSERT_ALERT, rows)
        return cursor.rowcount


def alerts_main() -> None:
    """Extrait et charge une fois les alertes, sans planification."""
    parser = argparse.ArgumentParser(
        description="Récupère les alertes de l'API et les insère dans PostgreSQL."
    )
    parser.parse_args()
    alerts = extract_alerts()
    inserted = load_alerts(alerts)
    print(
        f"Alertes reçues : {len(alerts)} ; insérées : {inserted} ; "
        f"déjà présentes : {len(alerts) - inserted}."
    )
