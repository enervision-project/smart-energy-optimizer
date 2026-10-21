import argparse
import os
from datetime import datetime, timezone
from collections.abc import Mapping, Sequence
from typing import Any

import psycopg

from etl_worker.extract import extract_alerts


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

    with psycopg.connect(connection_url, connect_timeout=connect_timeout) as connection:
        with connection.cursor() as cursor:
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


def load_readings(
    readings: Sequence[Mapping[str, Any]],
    database_url: str | None = None,
    *,
    connect_timeout: int = 10,
) -> int:
    """Insère les consommations et retourne le nombre de nouvelles mesures.

    timestamp est stocké dans la colonne ts. Les valeurs nulles et les raisons
    fournies par l'API, y compris site_type, sont conservées dans leurs colonnes.
    Une clé (site_id, ts) existante est
    ignorée, sans modification de ses valeurs ni de loaded_at.
    Les sites doivent déjà exister en base. Tout le lot est annulé en cas
    d'erreur. Une liste vide retourne 0 sans ouvrir de connexion.
    """
    if not readings:
        return 0

    connection_url = (
        database_url if database_url is not None else os.environ.get("DATABASE_URL", "")
    ).strip()
    if not connection_url:
        raise ValueError("Renseigner DATABASE_URL ou passer une URL à load_readings.")

    rows = [
        (
            reading["site_id"],
            reading["timestamp"],
            reading["site_type"],
            reading.get("consumption_kw"),
            reading.get("consumption_kwh"),
            reading.get("voltage_v"),
            reading.get("current_a"),
            reading.get("power_factor"),
            reading.get("temperature_celsius"),
            reading.get("humidity_percent"),
            reading.get("null_reasons", []),
            reading["data_quality"],
        )
        for reading in readings
    ]

    with psycopg.connect(connection_url, connect_timeout=connect_timeout) as connection:
        with connection.cursor() as cursor:
            cursor.executemany(_INSERT_READING, rows)
            return cursor.rowcount


def read_site_ids(
    database_url: str | None = None, *, connect_timeout: int = 10
) -> list[str]:
    """Lit les sites connus en base sans solliciter l'API des sites."""
    connection_url = (
        database_url if database_url is not None else os.environ.get("DATABASE_URL", "")
    ).strip()
    if not connection_url:
        raise ValueError("Renseigner DATABASE_URL ou passer une URL à read_site_ids.")

    with psycopg.connect(connection_url, connect_timeout=connect_timeout) as connection:
        with connection.cursor() as cursor:
            cursor.execute("SELECT site_id FROM sites ORDER BY site_id")
            return [row[0] for row in cursor.fetchall()]


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
        timestamp = timestamp.replace(tzinfo=timezone.utc)
    return timestamp.astimezone(timezone.utc)

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
    with psycopg.connect(connection_url, connect_timeout=connect_timeout) as connection:
        with connection.cursor() as cursor:
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
