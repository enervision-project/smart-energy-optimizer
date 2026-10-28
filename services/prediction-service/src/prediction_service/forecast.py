"""Prévisions horaires des heures manquantes, recalage de niveau et publication atomique."""

import logging
import math
from collections import defaultdict
from datetime import UTC, datetime, timedelta
from uuid import UUID

from prediction_service.recalibration import NEUTRAL, WINDOW_HOURS, LevelRatios, level_ratios
from prediction_service.registry import available_predictor
from prediction_service.repository import (
    SiteProfile,
    read_covered_hours,
    read_measured_hours,
    read_site_profiles,
    save_forecast,
)
from prediction_service.schemas import PredictRequest
from prediction_service.settings import Settings

logger = logging.getLogger(__name__)


def next_24_hours(now: datetime) -> list[datetime]:
    start = now.astimezone(UTC).replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
    return [start + timedelta(hours=offset) for offset in range(24)]


def calendar_request(profile: SiteProfile, instant: datetime) -> PredictRequest:
    # Calendrier en UTC, comme le CSV d'entraînement et l'API Mock : leurs heures
    # de travail ne suivent pas l'heure d'été (sinon décalage d'1 h l'hiver, 2 h l'été).
    utc = instant.astimezone(UTC)
    return PredictRequest(
        site_id=profile.site_id,
        hour=utc.hour,
        day_of_week=utc.weekday(),
        month=utc.month,
        is_working_hours=int(
            utc.isoweekday() in profile.working_days
            and profile.working_hour_start <= utc.hour < profile.working_hour_end
        ),
    )


def site_ratios(
    settings: Settings, predictor, profiles: list[SiteProfile], now: datetime
) -> dict[str, LevelRatios]:
    """Ratio mesuré / prévu par le champion de chaque site, sur les heures closes de la fenêtre."""
    if not settings.level_recalibration:
        return {profile.site_id: NEUTRAL for profile in profiles}
    end = now.astimezone(UTC).replace(minute=0, second=0, microsecond=0)
    measured = defaultdict(list)
    for site_id, hour, value in read_measured_hours(
        settings.database_url, end - timedelta(hours=WINDOW_HOURS), end
    ):
        measured[site_id].append((hour, value))
    ratios = {}
    for profile in profiles:
        observations = []
        for hour, value in measured[profile.site_id]:
            request = calendar_request(profile, hour)
            observations.append((request.is_working_hours, value, predictor.predict(request)))
        ratios[profile.site_id] = level_ratios(observations)
    return ratios


def missing_hours(
    settings: Settings, predictor, profiles: list[SiteProfile], window: list[datetime]
) -> list[datetime]:
    """Heures de la fenêtre qu'un site au moins n'a pas encore, prévues par ce champion.

    En régime normal, seule la dernière heure (H+24) manque. Après un échec, toutes les
    heures restées sans prévision ; au démarrage ou après un changement de champion, les 24.
    """
    covered = read_covered_hours(
        settings.database_url,
        window[0],
        window[-1] + timedelta(hours=1),
        settings.registered_model_name,
        predictor.version,
    )
    return [
        hour
        for hour in window
        if any((profile.site_id, hour) not in covered for profile in profiles)
    ]


def generate_forecast(settings: Settings, job_id: UUID, now: datetime | None = None) -> UUID | None:
    """Publie les heures manquantes des 24 prochaines ; None si toutes sont déjà prévues."""
    now = now or datetime.now(UTC)
    predictor = available_predictor(
        settings.model_dir, settings.mlflow_tracking_uri or None, settings.registered_model_name
    )
    profiles = read_site_profiles(settings.database_url)
    known = [profile for profile in profiles if profile.site_id in predictor.site_codes]
    if not known:
        raise ValueError("Aucun site doté d'un profil n'est connu du champion.")
    unknown = sorted(
        {profile.site_id for profile in profiles} - {profile.site_id for profile in known}
    )
    if unknown:
        logger.warning("Sites ignorés car inconnus du champion : %s", unknown)
    hours = missing_hours(settings, predictor, known, next_24_hours(now))
    if not hours:
        logger.info("Prévisions déjà à jour pour les 24 prochaines heures.")
        return None
    logger.info("%d heure(s) à prévoir sur 24 avec le champion %s", len(hours), predictor.version)
    ratios = site_ratios(settings, predictor, known, now)
    rows = []
    for profile in known:
        ratio = ratios[profile.site_id]
        logger.info(
            "Recalage %s : %.3f (heures travaillées %.3f, autres %.3f, %d h mesurées)",
            profile.site_id,
            ratio.overall,
            ratio.working,
            ratio.off,
            ratio.hours,
        )
        if ratio.clamped:
            logger.warning(
                "Ratio de %s ramené dans les bornes : données à vérifier.", profile.site_id
            )
        for instant in hours:
            request = calendar_request(profile, instant)
            raw = predictor.predict(request)
            if not math.isfinite(raw) or raw < 0:
                raise ValueError(f"Prévision invalide pour {profile.site_id} à {instant}")
            applied = ratio.for_hour(request.is_working_hours)
            rows.append((profile.site_id, instant, raw * applied, raw, applied))
    return save_forecast(
        settings.database_url,
        job_id,
        settings.registered_model_name,
        predictor.version,
        hours,
        rows,
        len(known),
    )
