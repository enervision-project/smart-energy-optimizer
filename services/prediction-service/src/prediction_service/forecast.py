"""Prévisions horaires avec le champion courant et publication atomique."""

import logging
import math
from datetime import UTC, datetime, timedelta
from uuid import UUID
from zoneinfo import ZoneInfo

from prediction_service.registry import available_predictor
from prediction_service.repository import read_site_profiles, save_forecast
from prediction_service.schemas import PredictRequest
from prediction_service.settings import Settings

logger = logging.getLogger(__name__)


def next_24_hours(now: datetime) -> list[datetime]:
    start = now.astimezone(UTC).replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
    return [start + timedelta(hours=offset) for offset in range(24)]


def generate_forecast(settings: Settings, job_id: UUID, now: datetime | None = None) -> UUID:
    now = now or datetime.now(UTC)
    predictor = available_predictor(
        settings.model_dir, settings.mlflow_tracking_uri or None, settings.registered_model_name
    )
    hours = next_24_hours(now)
    profiles = read_site_profiles(settings.database_url)
    known = [profile for profile in profiles if profile.site_id in predictor.site_codes]
    if not known:
        raise ValueError("Aucun site doté d'un profil n'est connu du champion.")
    unknown = sorted(
        {profile.site_id for profile in profiles} - {profile.site_id for profile in known}
    )
    if unknown:
        logger.warning("Sites ignorés car inconnus du champion : %s", unknown)
    zone = ZoneInfo(settings.training_timezone)
    rows = []
    for profile in known:
        for instant in hours:
            local = instant.astimezone(zone)
            request = PredictRequest(
                site_id=profile.site_id,
                hour=local.hour,
                day_of_week=local.weekday(),
                month=local.month,
                is_working_hours=int(
                    local.isoweekday() in profile.working_days
                    and profile.working_hour_start <= local.hour < profile.working_hour_end
                ),
            )
            value = predictor.predict(request)
            if not math.isfinite(value) or value < 0:
                raise ValueError(f"Prévision invalide pour {profile.site_id} à {instant}")
            rows.append((profile.site_id, instant, value))
    return save_forecast(
        settings.database_url,
        job_id,
        settings.registered_model_name,
        predictor.version,
        hours,
        rows,
        len(known),
    )
