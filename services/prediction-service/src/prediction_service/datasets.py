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


def load_bootstrap(uri: str, s3_client=None) -> tuple[pd.DataFrame, dict]:
    frames, manifest = [], {}
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
        frames.append(frame)
        manifest[name] = {"sha256": sha256(content).hexdigest(), "rows": len(frame)}
    if frames[0].timestamp.max() >= frames[1].timestamp.min():
        raise ValueError("Les splits historiques ne sont pas chronologiques.")
    return pd.concat(frames, ignore_index=True), manifest


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
    historical: pd.DataFrame, current: pd.DataFrame, validation_days: int = 14
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Validation sur les dernières journées disponibles, sans jeu test historique."""
    combined = pd.concat([historical, current], ignore_index=True)
    combined = combined.dropna(subset=[TARGET]).sort_values(["timestamp", "site_id"])
    if combined.duplicated(["site_id", "timestamp"]).any():
        raise ValueError("Doublons site/heure entre historique et SQL.")
    if combined.empty or (combined[TARGET] < 0).any():
        raise ValueError("Cibles absentes ou négatives.")
    latest = combined.timestamp.max()
    cutoff = latest - pd.Timedelta(days=validation_days)
    train = combined.loc[combined.timestamp < cutoff].reset_index(drop=True)
    validation = combined.loc[combined.timestamp >= cutoff].reset_index(drop=True)
    if train.empty or validation.empty:
        raise ValueError("Historique insuffisant pour train et validation.")
    if set(train.site_id) != set(validation.site_id):
        raise ValueError("Train et validation doivent couvrir les mêmes sites.")
    return train, validation


def current_ready(current: pd.DataFrame, historical: pd.DataFrame, minimum_hours: int) -> bool:
    """Attend une semaine de données SQL valides pour chaque site historique."""
    if current.empty:
        return False
    counts = current.groupby("site_id")[TARGET].count()
    return all(counts.get(site, 0) >= minimum_hours for site in historical.site_id.unique())
