"""Ordonnanceur unique : entraînement à 01:00 Europe/Paris, prévisions chaque heure à :05."""

import logging
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from prediction_service.forecast import generate_forecast
from prediction_service.repository import claimed_job, latest_hour
from prediction_service.settings import get_settings
from prediction_service.training import last_successful_training, needs_catchup, train_challenger

logger = logging.getLogger(__name__)


def _training(trigger: str, schedule_key: str) -> None:
    settings = get_settings()
    with claimed_job(settings.database_url, "training", schedule_key, trigger) as job_id:
        if job_id is not None:
            train_challenger(settings, job_id, trigger)


def _forecast(schedule_key: str) -> None:
    settings = get_settings()
    newest = latest_hour(settings.database_url)
    expected = datetime.now(UTC).replace(minute=0, second=0, microsecond=0) - timedelta(hours=1)
    if newest is None or newest < expected:
        raise ValueError(f"Agrégat horaire trop ancien : {newest}, attendu au moins {expected}.")
    with claimed_job(settings.database_url, "forecast", schedule_key, "scheduled") as job_id:
        if job_id is not None:
            run_id = generate_forecast(settings, job_id)
            logger.info("Prévisions publiées : %s", run_id)


def forecast_key(now: datetime) -> str:
    """Créneau de prévision : l'heure UTC en cours (par exemple 2026-10-26T14:00Z)."""
    return now.astimezone(UTC).strftime("%Y-%m-%dT%H:00Z")


def run_scheduler() -> None:
    settings = get_settings()
    logging.basicConfig(level=settings.log_level)
    if not settings.database_url or not settings.mlflow_tracking_uri:
        raise ValueError("DATABASE_URL et MLFLOW_TRACKING_URI sont requis pour les jobs.")
    zone = ZoneInfo(settings.training_timezone)
    last_catchup_attempt: datetime | None = None
    executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="training")
    active_training = None
    while True:
        now = datetime.now(UTC)
        local = now.astimezone(zone)
        day = local.date().isoformat()
        try:
            if local.hour == 1 and local.minute == 0:
                last = last_successful_training(
                    settings.mlflow_tracking_uri, settings.training_experiment
                )
                if (last is None or now - last > timedelta(hours=1)) and (
                    active_training is None or active_training.done()
                ):
                    active_training = executor.submit(_training, "scheduled", day)
            elif last_catchup_attempt is None or now - last_catchup_attempt >= timedelta(hours=1):
                last_catchup_attempt = now
                last = last_successful_training(
                    settings.mlflow_tracking_uri, settings.training_experiment
                )
                if needs_catchup(last, now) and (active_training is None or active_training.done()):
                    active_training = executor.submit(_training, "catchup", f"catchup-{day}")
        except Exception:
            logger.exception("Entraînement impossible")
        if active_training is not None and active_training.done():
            try:
                active_training.result()
            except Exception:
                logger.exception("Job d'entraînement échoué")
            active_training = None
        try:
            # Une série par heure UTC (clé SQL) : les 24 heures suivantes restent couvertes.
            # :05 laisse à l'ETL le temps de calculer l'heure close (sync-hours à :02) ;
            # en cas d'échec, nouvel essai à :20, :35 et :50.
            if local.minute % 15 == 5:
                _forecast(forecast_key(now))
        except Exception:
            logger.exception("Prévisions impossibles")
        time.sleep(60 - datetime.now(UTC).second)


if __name__ == "__main__":
    run_scheduler()
