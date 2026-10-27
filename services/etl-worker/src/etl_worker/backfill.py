"""Rattrapage des minutes jamais reçues, via l'historique simulé GET /readings."""

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from etl_worker.bronze import write_readings_bronze
from etl_worker.extract import HISTORY_MAX_MINUTES, extract_history
from etl_worker.load import load_readings, read_missing_ranges


@dataclass
class BackfillResult:
    ranges: int = 0
    received: int = 0
    inserted: int = 0
    errors: dict[str, str] = field(default_factory=dict)


def backfill_window(
    hours: int, now: datetime | None = None
) -> tuple[datetime, datetime]:
    """Fenêtre [début, fin) de minutes UTC à examiner.

    La fin exclut la minute en cours et la précédente : l'API refuse une fin
    dans le futur (avec quelques secondes de marge) et sync-readings a encore
    la minute précédente à collecter.
    """
    if hours < 1:
        raise ValueError("hours doit valoir au moins 1.")
    reference = now if now is not None else datetime.now(UTC)
    if reference.utcoffset() is None:
        raise ValueError("now doit comporter un fuseau horaire.")
    end = reference.astimezone(UTC).replace(second=0, microsecond=0) - timedelta(
        minutes=1
    )
    return end - timedelta(hours=hours), end


def split_range(start: datetime, end: datetime) -> list[tuple[datetime, datetime]]:
    """Découpe [start, end) en morceaux d'au plus HISTORY_MAX_MINUTES minutes.

    Les bornes passent en UTC : la base renvoie des dates dans le fuseau de session
    (Europe/Paris), et Python ajoute un timedelta en heure locale, ce qui fausse la
    durée d'un morceau qui traverse un changement d'heure (1060 minutes au lieu de 1000).
    """
    start, end = start.astimezone(UTC), end.astimezone(UTC)
    step = timedelta(minutes=HISTORY_MAX_MINUTES)
    chunks = []
    while start < end:
        chunks.append((start, min(start + step, end)))
        start += step
    return chunks


def backfill_readings(
    hours: int,
    *,
    now: datetime | None = None,
    base_url: str | None = None,
    database_url: str | None = None,
) -> BackfillResult:
    """Comble les minutes sans ligne des dernières heures et retourne le bilan.

    Chaque morceau est archivé dans le bronze puis inséré avec source = backfill ;
    ON CONFLICT DO NOTHING garantit qu'une mesure /current n'est jamais remplacée.
    Un morceau en erreur (API, réponse incomplète) est noté dans errors sans
    empêcher les autres ; il sera retenté au prochain passage.
    """
    start, end = backfill_window(hours, now)
    result = BackfillResult()
    for site_id, first, last in read_missing_ranges(start, end, database_url):
        result.ranges += 1
        for chunk_start, chunk_end in split_range(first, last):
            label = f"{site_id}_{chunk_start:%Y%m%dT%H%M}-{chunk_end:%Y%m%dT%H%M}"
            try:
                readings = extract_history(site_id, chunk_start, chunk_end, base_url)
                write_readings_bronze(readings, kind="backfill", label=label)
                result.inserted += load_readings(
                    readings, database_url, source="backfill"
                )
            # OSError couvre HTTPError, URLError et les délais dépassés ; ValueError le JSON invalide.
            except (OSError, TypeError, ValueError) as error:
                result.errors[label] = str(error) or type(error).__name__
                continue
            result.received += len(readings)
    return result
