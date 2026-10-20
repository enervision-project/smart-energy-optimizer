import os
from collections.abc import Mapping, Sequence
from typing import Any

import psycopg


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
