"""Snapshot d'entraînement à partir des Parquet historiques et des heures SQL."""

from hashlib import sha256
from io import BytesIO
from pathlib import Path
from urllib.parse import urlparse

import boto3
import pandas as pd

from prediction_service.repository import SiteProfile

FEATURES = ["site_id", "hour", "day_of_week", "month", "is_working_hours"]
TARGET = "consumption_kwh"


def _bootstrap_file(uri: str, name: str, s3_client=None) -> bytes:
    if uri.startswith("s3://"):
        parsed = urlparse(uri)
        key = f"{parsed.path.lstrip('/').rstrip('/')}/{name}.parquet"
        client = s3_client or boto3.client("s3")
        return client.get_object(Bucket=parsed.netloc, Key=key)["Body"].read()
    return (Path(uri) / f"{name}.parquet").read_bytes()


def load_bootstrap(uri: str, s3_client=None) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    """Charge les splits d'origine séparément ; le split test n'entre jamais dans le job."""
    frames, manifest = {}, {}
    for name in ("train", "validation"):
        content = _bootstrap_file(uri, name, s3_client)
        frame = pd.read_parquet(BytesIO(content))
        required = {"timestamp", *FEATURES, TARGET}
        if not required.issubset(frame.columns):
            raise ValueError(f"{name}: colonnes manquantes {sorted(required - set(frame.columns))}")
        frame = frame[["timestamp", *FEATURES, TARGET]].copy()
        frame["timestamp"] = pd.to_datetime(frame.timestamp)
        if frame.timestamp.dt.tz is None:
            # Le CSV historique encode 24 heures par jour, même aux changements d'heure.
            # Ses dates servent uniquement à l'ordre chronologique, pas aux lags UTC.
            frame["timestamp"] = frame.timestamp.dt.tz_localize("UTC")
        else:
            frame["timestamp"] = frame.timestamp.dt.tz_convert("UTC")
        frames[name] = frame
        manifest[name] = {"sha256": sha256(content).hexdigest(), "rows": len(frame)}
    if frames["train"].timestamp.max() >= frames["validation"].timestamp.min():
        raise ValueError("Les splits historiques ne sont pas chronologiques.")
    return frames["train"], frames["validation"], manifest


def prepare_current(
    hours: pd.DataFrame, profiles: list[SiteProfile], timezone: str = "Europe/Paris"
) -> pd.DataFrame:
    if hours.empty:
        return pd.DataFrame(columns=["timestamp", *FEATURES, TARGET])
    data = hours.copy()
    data[TARGET] = pd.to_numeric(data[TARGET], errors="raise").astype(float)
    data["timestamp"] = pd.to_datetime(data.timestamp, utc=True)
    local = data.timestamp.dt.tz_convert(timezone)
    data["hour"] = local.dt.hour
    data["day_of_week"] = local.dt.day_of_week
    data["month"] = local.dt.month
    by_site = {profile.site_id: profile for profile in profiles}
    missing = set(data.site_id) - set(by_site)
    if missing:
        raise ValueError(f"Sites sans profil horaire : {sorted(missing)}")
    data["is_working_hours"] = [
        int(
            int(weekday) + 1 in by_site[site].working_days
            and by_site[site].working_hour_start <= int(hour) < by_site[site].working_hour_end
        )
        for site, weekday, hour in zip(data.site_id, data.day_of_week, data.hour, strict=True)
    ]
    return data[["timestamp", *FEATURES, TARGET]]


def make_splits(
    bootstrap_train: pd.DataFrame,
    bootstrap_validation: pd.DataFrame,
    current: pd.DataFrame,
    validation_days: int = 14,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Préserve les splits initiaux, puis valide sur les données SQL récentes."""
    if current.empty:
        train, validation = bootstrap_train.copy(), bootstrap_validation.copy()
    else:
        cutoff = current.timestamp.max() - pd.Timedelta(days=validation_days)
        current_train = current.loc[current.timestamp < cutoff]
        validation = current.loc[current.timestamp >= cutoff].copy()
        # Après le choix du HGB, le split historique de validation rejoint le train.
        train = pd.concat([bootstrap_train, bootstrap_validation, current_train], ignore_index=True)
    train = train.dropna(subset=[TARGET]).sort_values(["timestamp", "site_id"])
    validation = validation.dropna(subset=[TARGET]).sort_values(["timestamp", "site_id"])
    combined = pd.concat([train, validation], ignore_index=True)
    if combined.duplicated(["site_id", "timestamp"]).any():
        raise ValueError("Doublons site/heure entre historique et SQL.")
    if combined.empty or (combined[TARGET] < 0).any():
        raise ValueError("Cibles absentes ou négatives.")
    if train.empty or validation.empty:
        raise ValueError("Historique insuffisant pour train et validation.")
    if set(train.site_id) != set(validation.site_id):
        raise ValueError("Train et validation doivent couvrir les mêmes sites.")
    return train.reset_index(drop=True), validation.reset_index(drop=True)


def current_ready(current: pd.DataFrame, historical: pd.DataFrame, minimum_hours: int) -> bool:
    """Attend une semaine de données SQL valides pour chaque site historique."""
    if current.empty:
        return False
    counts = current.groupby("site_id")[TARGET].count()
    return all(counts.get(site, 0) >= minimum_hours for site in historical.site_id.unique())
