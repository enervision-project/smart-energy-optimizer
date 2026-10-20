"""Extract : récupération des données depuis l'API énergie."""

import json
import os
from typing import Any
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
