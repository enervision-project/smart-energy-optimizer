"""Extract : récupération des données depuis l'API énergie."""

import argparse
import base64
import json
import os
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from importlib.resources import files
from typing import Any
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen

from etl_worker.timestamps import parse_reading_timestamp

# Plafond de limit pour GET /readings (documentation de l'API Mock).
HISTORY_MAX_MINUTES = 1000

_ALERT_FIELDS = frozenset(
    {
        "alert_id",
        "timestamp",
        "site_id",
        "severity",
        "type",
        "message",
        "value",
        "threshold",
    }
)


# --- Helpers communs -------------------------------------------------------


def _api_headers() -> dict[str, str]:
    """En-têtes communs ; authentification Basic si ENERGY_API_USERNAME est renseigné."""
    headers = {"Accept": "application/json"}
    username = os.environ.get("ENERGY_API_USERNAME", "")
    if username:
        password = os.environ.get("ENERGY_API_PASSWORD", "")
        token = base64.b64encode(f"{username}:{password}".encode()).decode("ascii")
        headers["Authorization"] = f"Basic {token}"
    return headers


def _resolve_base_url(base_url: str | None, caller: str) -> str:
    url = (
        base_url if base_url is not None else os.environ.get("ENERGY_API_BASE_URL", "")
    )
    url = url.strip().rstrip("/")
    if not url:
        raise ValueError(
            f"Renseigner ENERGY_API_BASE_URL ou passer une URL à {caller}."
        )
    return url


def _get_json(
    base_url: str, path: str, timeout: float, params: dict[str, Any] | None = None
) -> Any:
    """GET JSON ; les erreurs HTTP, réseau et de décodage remontent à l'appelant."""
    url = f"{base_url}{path}"
    if params:
        url = f"{url}?{urlencode(params)}"
    with urlopen(Request(url, headers=_api_headers()), timeout=timeout) as response:
        return json.load(response)


def _require_list_of_dicts(data: Any, message: str) -> list[dict[str, Any]]:
    if not isinstance(data, list) or not all(isinstance(item, dict) for item in data):
        raise ValueError(message)
    return data


# --- Sites et profils ------------------------------------------------------


def extract_sites(
    base_url: str | None = None, *, timeout: float = 10.0
) -> list[dict[str, Any]]:
    """Récupère les sites. Une réponse qui n'est pas une liste d'objets JSON lève ValueError."""
    api_base_url = _resolve_base_url(base_url, "extract_sites")
    return _require_list_of_dicts(
        _get_json(api_base_url, "/api/v1/sites", timeout),
        "La réponse de /api/v1/sites doit être une liste d'objets JSON.",
    )


def read_site_profiles() -> list[dict[str, Any]]:
    """Lit les profils de référence livrés avec le paquet (data/site_profiles.json).

    Source : clé « profile » des fichiers *_metadata.json du jeu de données (pas d'endpoint API).
    Le format source est conservé (jours 0 = lundi, working_hours [début, fin]) ; load les convertit.
    """
    content = (
        files("etl_worker")
        .joinpath("data/site_profiles.json")
        .read_text(encoding="utf-8")
    )
    return _require_list_of_dicts(
        json.loads(content), "site_profiles.json doit être une liste d'objets JSON."
    )


# --- Mesures ---------------------------------------------------------------


def _validate_reading(reading: dict[str, Any], site_id: str) -> None:
    if reading.get("site_id") != site_id:
        raise ValueError(f"La mesure reçue ne correspond pas au site {site_id}.")
    try:
        parse_reading_timestamp(reading.get("timestamp"))
    except ValueError as error:
        raise ValueError(f"Timestamp invalide pour le site {site_id}.") from error


def _fetch_reading(base_url: str, site_id: str, timeout: float) -> dict[str, Any]:
    payload = _get_json(
        base_url,
        f"/api/v1/sites/{quote(site_id, safe='')}/current",
        timeout,
    )
    if not isinstance(payload, dict):
        raise TypeError(f"Un objet de mesure est attendu pour le site {site_id}.")
    _validate_reading(payload, site_id)
    return payload


def extract_readings(
    site_ids: Sequence[str],
    base_url: str | None = None,
    *,
    timeout: float = 10.0,
) -> tuple[list[dict[str, Any]], dict[str, str]]:
    """Retourne les mesures /current reçues et les erreurs par site.

    Les timestamps, leur précision et leurs éventuels fuseaux sont conservés
    tels que reçus, tout comme les NULL, la qualité et les champs supplémentaires.
    Chaque site est interrogé indépendamment : une erreur HTTP, réseau ou une
    réponse invalide est retournée pour ce site sans empêcher la collecte des autres.
    Une URL d'API absente reste une erreur de configuration qui arrête tout.
    """
    if not site_ids:
        return [], {}
    api_base_url = _resolve_base_url(base_url, "extract_readings")
    readings: list[dict[str, Any]] = []
    errors: dict[str, str] = {}
    for site_id in site_ids:
        try:
            readings.append(_fetch_reading(api_base_url, site_id, timeout))
        # OSError couvre HTTPError, URLError et les délais dépassés ; ValueError le JSON invalide.
        except (OSError, TypeError, ValueError) as error:
            errors[site_id] = str(error) or type(error).__name__
    return readings, errors


def extract_history(
    site_id: str,
    start: datetime,
    end: datetime,
    base_url: str | None = None,
    *,
    timeout: float = 30.0,
) -> list[dict[str, Any]]:
    """Retourne une mesure /readings par minute de [start, end), pour le rattrapage.

    start et end sont des débuts de minute avec fuseau ; la plage compte au plus
    HISTORY_MAX_MINUTES minutes. limit vaut le nombre de minutes : avec moins,
    l'API échantillonnerait la plage au lieu de renvoyer chaque minute.
    La réponse doit contenir exactement une mesure de ce site pour chaque minute,
    sinon ValueError (ou TypeError) : rien n'est retourné pour une plage douteuse.
    Les valeurs sont recalculées par l'API à chaque appel (historique simulé).
    """
    for bound in (start, end):
        if bound.utcoffset() is None or bound.second or bound.microsecond:
            raise ValueError(
                "Les bornes du rattrapage doivent être des minutes avec fuseau."
            )
    start, end = start.astimezone(UTC), end.astimezone(UTC)
    minutes = int((end - start) / timedelta(minutes=1))
    if not 1 <= minutes <= HISTORY_MAX_MINUTES:
        raise ValueError(
            f"Une plage de rattrapage compte de 1 à {HISTORY_MAX_MINUTES} minutes."
        )

    api_base_url = _resolve_base_url(base_url, "extract_history")
    payload = _get_json(
        api_base_url,
        "/api/v1/readings",
        timeout,
        params={
            "site_id": site_id,
            "start_time": start.isoformat(),
            "end_time": end.isoformat(),
            "limit": minutes,
        },
    )
    if not isinstance(payload, list) or not all(
        isinstance(item, dict) for item in payload
    ):
        raise TypeError(f"Une liste de mesures est attendue pour le site {site_id}.")
    for reading in payload:
        _validate_reading(reading, site_id)
    received = sorted(
        parse_reading_timestamp(reading["timestamp"]) for reading in payload
    )
    expected = [start + timedelta(minutes=offset) for offset in range(minutes)]
    if received != expected:
        raise ValueError(
            f"Rattrapage {site_id} : {len(payload)} mesures reçues, "
            f"une par minute attendue de {start.isoformat()} à {end.isoformat()}."
        )
    return payload


# --- Alertes ---------------------------------------------------------------


def extract_alerts(
    base_url: str | None = None, *, timeout: float = 10.0
) -> list[dict[str, Any]]:
    """Récupère toutes les alertes actives."""
    api_base_url = _resolve_base_url(base_url, "extract_alerts")
    alerts = _require_list_of_dicts(
        _get_json(api_base_url, "/api/v1/alerts", timeout),
        "La réponse de /api/v1/alerts doit être une liste d'objets JSON.",
    )
    for alert in alerts:
        missing = _ALERT_FIELDS.difference(alert)
        if missing:
            raise ValueError(
                f"Champs manquants dans une alerte : {', '.join(sorted(missing))}."
            )
    return alerts


def alerts_main() -> None:
    """Extrait une fois les alertes et affiche le JSON, sans base de données."""
    parser = argparse.ArgumentParser(
        description="Extrait une fois les alertes actives de l'API et affiche le JSON."
    )
    parser.parse_args()
    print(json.dumps(extract_alerts(), ensure_ascii=False))
