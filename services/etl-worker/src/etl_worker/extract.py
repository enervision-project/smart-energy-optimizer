"""Extract : récupération des données depuis l'API énergie."""

import argparse
import base64
import json
import os
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from importlib.resources import files
from typing import Any
from urllib.parse import urlencode
from urllib.request import Request, urlopen

_ALERT_FIELDS = frozenset({
    "alert_id", "timestamp", "site_id", "severity",
    "type", "message", "value", "threshold",
})


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
    url = base_url if base_url is not None else os.environ.get("ENERGY_API_BASE_URL", "")
    url = url.strip().rstrip("/")
    if not url:
        raise ValueError(f"Renseigner ENERGY_API_BASE_URL ou passer une URL à {caller}.")
    return url


def _get_json(base_url: str, path: str, timeout: float, params: dict[str, Any] | None = None) -> Any:
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
    content = files("etl_worker").joinpath("data/site_profiles.json").read_text(encoding="utf-8")
    return _require_list_of_dicts(
        json.loads(content), "site_profiles.json doit être une liste d'objets JSON."
    )


# --- Mesures ---------------------------------------------------------------

def _reading_window(end_time: datetime | None) -> tuple[datetime, datetime]:
    """Fenêtre d'une minute en UTC ; l'heure courante n'est lue qu'une fois pour le lot."""
    reference = end_time if end_time is not None else datetime.now(UTC)
    if reference.utcoffset() is None:
        raise ValueError("end_time doit comporter un fuseau horaire.")
    window_end = reference.astimezone(UTC).replace(second=0, microsecond=0)
    return window_end - timedelta(minutes=1), window_end


def _validate_reading(reading: dict[str, Any], site_id: str, window_start: datetime) -> None:
    if reading.get("site_id") != site_id:
        raise ValueError(f"La mesure reçue ne correspond pas au site {site_id}.")
    try:
        measured_at = datetime.fromisoformat(reading.get("timestamp"))
    except (TypeError, ValueError) as error:
        raise ValueError(f"Timestamp invalide pour le site {site_id}.") from error
    if measured_at.utcoffset() is None or measured_at != window_start:
        raise ValueError(
            f"Timestamp inattendu pour {site_id} : {window_start.isoformat()} attendu."
        )


def _fetch_reading(
    base_url: str, site_id: str, start: datetime, end: datetime, timeout: float
) -> dict[str, Any]:
    payload = _get_json(
        base_url,
        "/api/v1/readings",
        timeout,
        params={
            "site_id": site_id,
            "start_time": start.isoformat(),
            "end_time": end.isoformat(),
            "limit": 1,
        },
    )
    if not isinstance(payload, list) or len(payload) != 1 or not isinstance(payload[0], dict):
        raise ValueError(f"Une seule mesure est attendue pour le site {site_id}.")
    _validate_reading(payload[0], site_id, start)
    return payload[0]


def extract_readings(
    site_ids: Sequence[str],
    base_url: str | None = None,
    *,
    end_time: datetime | None = None,
    timeout: float = 10.0,
) -> list[dict[str, Any]]:
    """Retourne une mesure par site pour une minute commune en UTC.

    end_time est arrondi au début de sa minute ; la fenêtre couvre la minute
    précédente. Sans end_time, l'heure UTC est lue une seule fois pour le lot.
    Un end_time explicite doit comporter un fuseau horaire.
    Les mesures sont conservées telles quelles ; un lot incomplet ou mal aligné échoue.
    """
    if not site_ids:
        return []

    api_base_url = _resolve_base_url(base_url, "extract_readings")
    window_start, window_end = _reading_window(end_time)
    return [
        _fetch_reading(api_base_url, site_id, window_start, window_end, timeout)
        for site_id in site_ids
    ]


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