"""Extract : récupération des données depuis l'API énergie."""

import argparse
from collections.abc import Sequence
from datetime import datetime, timedelta, timezone
import json
import os
from typing import Any
from urllib.parse import urlencode
from urllib.request import Request, urlopen

#Permet d'extraire les différents sites 
#Les erreurs HTTP, réseau et de décodage JSON remontent à l'appelant
#Une réponse qui n'est pas une liste d'objets JSON lève ValueError.
def extract_sites(
    base_url: str | None = None, *, timeout: float = 10.0
) -> list[dict[str, Any]]:
    api_base_url = (
        base_url if base_url is not None else os.environ.get("ENERGY_API_BASE_URL", "")
    ).strip().rstrip("/")
    if not api_base_url:
        raise ValueError(
            "Renseigner ENERGY_API_BASE_URL ou passer une URL à extract_sites."
        )

    request = Request(
        f"{api_base_url}/api/v1/sites", headers={"Accept": "application/json"}
    )
    with urlopen(request, timeout=timeout) as response:
        sites = json.load(response)

    if not isinstance(sites, list) or not all(isinstance(site, dict) for site in sites):
        raise ValueError(
            "La réponse de /api/v1/sites doit être une liste d'objets JSON."
        )

    return sites


# Extrait la dernière minute terminée, avec la même fenêtre pour tous les sites.
# Les mesures sont conservées telles quelles ; un lot incomplet ou mal aligné échoue.
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
    """
    if not site_ids:
        return []

    api_base_url = (
        base_url if base_url is not None else os.environ.get("ENERGY_API_BASE_URL", "")
    ).strip().rstrip("/")
    if not api_base_url:
        raise ValueError(
            "Renseigner ENERGY_API_BASE_URL ou passer une URL à extract_readings."
        )

    reference = end_time if end_time is not None else datetime.now(timezone.utc)
    if reference.utcoffset() is None:
        raise ValueError("end_time doit comporter un fuseau horaire.")
    window_end = reference.astimezone(timezone.utc).replace(second=0, microsecond=0)
    window_start = window_end - timedelta(minutes=1)

    readings = []
    for site_id in site_ids:
        query = urlencode(
            {
                "site_id": site_id,
                "start_time": window_start.isoformat(),
                "end_time": window_end.isoformat(),
                "limit": 1,
            }
        )
        request = Request(
            f"{api_base_url}/api/v1/readings?{query}",
            headers={"Accept": "application/json"},
        )
        with urlopen(request, timeout=timeout) as response:
            payload = json.load(response)

        if (
            not isinstance(payload, list)
            or len(payload) != 1
            or not isinstance(payload[0], dict)
        ):
            raise ValueError(f"Une seule mesure est attendue pour le site {site_id}.")

        reading = payload[0]
        if reading.get("site_id") != site_id:
            raise ValueError(f"La mesure reçue ne correspond pas au site {site_id}.")
        timestamp = reading.get("timestamp")
        try:
            measured_at = datetime.fromisoformat(timestamp)
        except (TypeError, ValueError) as error:
            raise ValueError(f"Timestamp invalide pour le site {site_id}.") from error
        if measured_at.utcoffset() is None or measured_at != window_start:
            raise ValueError(
                f"Timestamp inattendu pour {site_id} : {window_start.isoformat()} attendu."
            )

        readings.append(reading)

    return readings


_ALERT_FIELDS = frozenset({
    "alert_id", "timestamp", "site_id", "severity",
    "type", "message", "value", "threshold",
})

#Récupère toutes les alertes actives
def extract_alerts(
    base_url: str | None = None, *, timeout: float = 10.0
) -> list[dict[str, Any]]:

    api_base_url = (
        base_url if base_url is not None else os.environ.get("ENERGY_API_BASE_URL", "")
    ).strip().rstrip("/")
    if not api_base_url:
        raise ValueError(
            "Renseigner ENERGY_API_BASE_URL ou passer une URL à extract_alerts."
        )

    request = Request(
        f"{api_base_url}/api/v1/alerts", headers={"Accept": "application/json"}
    )
    with urlopen(request, timeout=timeout) as response:
        alerts = json.load(response)

    if not isinstance(alerts, list) or not all(isinstance(alert, dict) for alert in alerts):
        raise ValueError(
            "La réponse de /api/v1/alerts doit être une liste d'objets JSON."
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
