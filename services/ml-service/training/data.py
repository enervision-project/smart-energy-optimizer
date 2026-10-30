from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path

import numpy as np
import pandas as pd

FEATURES = [
    "site_id", "hour", "day_of_week", "month", "is_working_hours",
    "lag_24h", "lag_168h", "temperature_celsius",
]
TARGET = "consumption_kwh"
COLUMNS = ["timestamp", *FEATURES, TARGET]
REQUIRED = ["timestamp", "site_id", "hour", "day_of_week", "month", "is_working_hours", TARGET]


@dataclass(frozen=True)
class TrainingData:
    train: pd.DataFrame
    validation: pd.DataFrame
    manifest: dict


def validate_frame(frame: pd.DataFrame, name: str) -> None:
    if frame.columns.tolist() != COLUMNS:
        raise ValueError(f"{name} : colonnes attendues {COLUMNS}, reçues {frame.columns.tolist()}")
    if frame.empty or frame[REQUIRED].isna().any().any():
        raise ValueError(f"{name} : jeu vide ou clé, calendrier, flag ou cible manquant.")
    if not pd.api.types.is_datetime64_any_dtype(frame.timestamp):
        raise ValueError(f"{name} : timestamp doit être une date.")
    if not frame.timestamp.is_monotonic_increasing:
        raise ValueError(f"{name} : les lignes doivent être ordonnées par timestamp.")
    if frame.duplicated(["site_id", "timestamp"]).any():
        raise ValueError(f"{name} : doublons site/timestamp.")
    for column in [*FEATURES[1:], TARGET]:
        values = frame[column]
        if not pd.api.types.is_numeric_dtype(values) or not np.isfinite(values.dropna()).all():
            raise ValueError(f"{name} : valeurs non numériques ou infinies dans {column}.")
    if frame[TARGET].lt(0).any() or not frame.is_working_hours.isin([0, 1]).all():
        raise ValueError(f"{name} : consommation négative ou flag hors 0/1.")
    for column, expected in [
        ("hour", frame.timestamp.dt.hour),
        ("day_of_week", frame.timestamp.dt.dayofweek),
        ("month", frame.timestamp.dt.month),
    ]:
        if not frame[column].eq(expected).all():
            raise ValueError(f"{name} : {column} ne correspond pas au timestamp.")


def load_data(directory: Path) -> TrainingData:
    frames, manifest = {}, {}
    for name in ("train", "validation"):
        path = directory / f"{name}.parquet"
        frame = pd.read_parquet(path)
        validate_frame(frame, name)
        frames[name] = frame
        manifest[name] = {
            "path": str(path), "sha256": sha256(path.read_bytes()).hexdigest(),
            "rows": len(frame), "columns": frame.columns.tolist(),
            "first_timestamp": frame.timestamp.min().isoformat(),
            "last_timestamp": frame.timestamp.max().isoformat(),
            "sites": sorted(frame.site_id.unique().tolist()),
        }
    if frames["train"].timestamp.max() >= frames["validation"].timestamp.min():
        raise ValueError("Train et validation doivent être séparés chronologiquement.")
    if set(frames["train"].site_id) != set(frames["validation"].site_id):
        raise ValueError("Train et validation doivent couvrir les mêmes sites.")
    return TrainingData(frames["train"], frames["validation"], manifest)
