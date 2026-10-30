from hashlib import sha256
from io import BytesIO
from pathlib import Path
from urllib.parse import urlparse

import boto3
import numpy as np
import pandas as pd

FEATURES = ["site_id", "hour", "day_of_week", "month", "is_working_hours"]
TARGET = "consumption_kwh"


def _bootstrap_file(uri: str, name: str, s3_client=None) -> bytes:
    if uri.startswith("s3://"):
        parsed = urlparse(uri)
        key = f"{parsed.path.lstrip('/').rstrip('/')}/{name}.parquet"
        client = s3_client or boto3.client("s3")
        return client.get_object(Bucket=parsed.netloc, Key=key)["Body"].read()
    return (Path(uri) / f"{name}.parquet").read_bytes()


def load_bootstrap(
    uri: str, s3_client=None
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, dict]:
    frames, manifest = {}, {}
    for name in ("train", "validation", "test"):
        content = _bootstrap_file(uri, name, s3_client)
        frame = pd.read_parquet(BytesIO(content))
        required = {"timestamp", *FEATURES, TARGET}
        if not required.issubset(frame.columns):
            raise ValueError(f"{name}: colonnes manquantes {sorted(required - set(frame.columns))}")
        frame = frame[["timestamp", *FEATURES, TARGET]].copy()
        frame["timestamp"] = pd.to_datetime(frame.timestamp)
        if frame.timestamp.dt.tz is None:
            # The history has 24 hours per day, even across DST changes; dates only give the order.
            frame["timestamp"] = frame.timestamp.dt.tz_localize("UTC")
        else:
            frame["timestamp"] = frame.timestamp.dt.tz_convert("UTC")
        frame[TARGET] = pd.to_numeric(frame[TARGET], errors="raise").astype(float)
        if frame.empty or frame.timestamp.isna().any():
            raise ValueError(f"{name}: split vide ou dates absentes.")
        if not np.isfinite(frame[TARGET]).all() or (frame[TARGET] < 0).any():
            raise ValueError(f"{name}: cibles absentes, non finies ou négatives.")
        if frame.duplicated(["site_id", "timestamp"]).any():
            raise ValueError(f"{name}: doublons site/heure.")
        frames[name] = frame
        manifest[name] = {
            "sha256": sha256(content).hexdigest(),
            "rows": len(frame),
            "min_timestamp": frame.timestamp.min().isoformat(),
            "max_timestamp": frame.timestamp.max().isoformat(),
        }
    train, validation, test = (frames[name] for name in ("train", "validation", "test"))
    if not (
        train.timestamp.max() < validation.timestamp.min()
        and validation.timestamp.max() < test.timestamp.min()
    ):
        raise ValueError("Les splits historiques ne sont pas chronologiques.")
    if not (set(train.site_id) == set(validation.site_id) == set(test.site_id)):
        raise ValueError("Train, Validation et Test doivent couvrir les mêmes sites.")
    return train, validation, test, manifest
