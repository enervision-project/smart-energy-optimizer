"""Suivi du modèle en production : erreur du champion seul et erreur publiée, par site.

Écrit une ligne de log par site après chaque série ; Loki la collecte et Grafana en tire les
courbes (ligne « Modèle » du dashboard). L'erreur du champion seul révèle la dérive que le
recalage de niveau masque dans l'erreur publiée.
"""

import logging
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from prediction_service.repository import read_forecast_errors

logger = logging.getLogger(__name__)

#: Heures closes comparées à chaque série.
WINDOW_HOURS = 24


@dataclass(frozen=True)
class ErrorSummary:
    hours: int
    champion_nmae_pct: float
    published_nmae_pct: float
    published_bias_pct: float


def summarize(rows: Iterable[tuple[float, float, float]]) -> ErrorSummary | None:
    """nMAE et biais à partir de `(mesuré, champion seul, publié)` ; None sans heure exploitable.

    Même nMAE que l'entraînement : 100 * moyenne(|réel - prévu|) / moyenne(réel).
    """
    rows = list(rows)
    total = sum(measured for measured, _, _ in rows)
    if not rows or total <= 0:
        return None
    return ErrorSummary(
        hours=len(rows),
        champion_nmae_pct=100 * sum(abs(c - m) for m, c, _ in rows) / total,
        published_nmae_pct=100 * sum(abs(p - m) for m, _, p in rows) / total,
        published_bias_pct=100 * sum(p - m for m, _, p in rows) / total,
    )


def log_forecast_errors(database_url: str, now: datetime | None = None) -> None:
    """Erreurs des 24 dernières heures closes, avec la dernière prévision publiée avant chacune."""
    end = (now or datetime.now(UTC)).astimezone(UTC).replace(minute=0, second=0, microsecond=0)
    by_site = defaultdict(list)
    for site_id, measured, champion, published in read_forecast_errors(
        database_url, end - timedelta(hours=WINDOW_HOURS), end
    ):
        by_site[site_id].append((measured, champion, published))
    for site_id in sorted(by_site):
        summary = summarize(by_site[site_id])
        if summary is None:
            continue
        # Format lu par Grafana (regexp LogQL) : le modifier impose de mettre à jour overview.json.
        logger.info(
            "Suivi modèle %s : nMAE champion %.1f %%, publiée %.1f %%, biais publié %+.1f %% "
            "(%d h)",
            site_id,
            summary.champion_nmae_pct,
            summary.published_nmae_pct,
            summary.published_bias_pct,
            summary.hours,
        )
