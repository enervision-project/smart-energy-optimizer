from datetime import UTC, datetime, timedelta
from itertools import pairwise
from uuid import UUID
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
import pytest

from prediction_service.datasets import FEATURES, load_bootstrap
from prediction_service.forecast import generate_forecast, next_24_hours
from prediction_service.repository import SiteProfile
from prediction_service.settings import Settings
from prediction_service.training import needs_catchup, should_promote


def test_promotion_uses_relative_four_percent():
    assert should_promote(5.0, 4.8)
    assert not should_promote(5.0, 4.81)
    assert not should_promote(0.0, 0.0)
    assert not should_promote(5.0, None)
    assert should_promote(None, 7.0)


def test_catchup_is_strictly_after_25_hours():
    now = datetime(2026, 10, 26, 12, tzinfo=UTC)
    assert needs_catchup(None, now)
    assert not needs_catchup(now - timedelta(hours=25), now)
    assert needs_catchup(now - timedelta(hours=25, seconds=1), now)


def test_rolling_24_hours_remain_distinct_during_dst():
    local = datetime(2026, 10, 25, 1, 5, tzinfo=ZoneInfo("Europe/Paris"))
    hours = next_24_hours(local)
    assert len(hours) == len(set(hours)) == 24
    assert all(b - a == timedelta(hours=1) for a, b in pairwise(hours))
    labels = [hour.astimezone(ZoneInfo("Europe/Paris")).hour for hour in hours]
    assert labels.count(2) == 2


def test_forecast_uses_loaded_champion_while_training_is_irrelevant(monkeypatch, tmp_path):
    from prediction_service import forecast

    class FakePredictor:
        version = "7"

        def __init__(self):
            self.site_codes = {"SITE001": 0}

        def predict(self, request):
            return float(request.hour + request.is_working_hours)

    captured = {}

    def save(*args):
        captured["args"] = args
        return UUID(int=1)

    monkeypatch.setattr(forecast, "available_predictor", lambda *args: FakePredictor())
    monkeypatch.setattr(
        forecast,
        "read_site_profiles",
        lambda *args: [SiteProfile("SITE001", 9, 18, (1, 2, 3, 4, 5))],
    )
    monkeypatch.setattr(forecast, "save_forecast", save)
    settings = Settings(model_dir=tmp_path, database_url="postgresql://unused")
    assert generate_forecast(
        settings, UUID(int=2), datetime(2026, 10, 26, 0, 5, tzinfo=UTC)
    ) == UUID(int=1)
    assert captured["args"][3] == "7"
    assert len(captured["args"][4]) == len(captured["args"][5]) == 24
    assert all(np.isfinite(value) for _, _, value in captured["args"][5])


@pytest.fixture
def parquet_splits(tmp_path):
    for day, name in enumerate(("train", "validation", "test"), start=1):
        pd.DataFrame(
            {
                "timestamp": [pd.Timestamp(f"2024-01-0{day}")],
                "site_id": ["SITE001"],
                "hour": [0],
                "day_of_week": [day - 1],
                "month": [1],
                "is_working_hours": [0],
                "consumption_kwh": [float(day)],
            }
        ).to_parquet(tmp_path / f"{name}.parquet")
    return tmp_path


@pytest.mark.parametrize(
    ("column", "value", "message"),
    [
        ("site_id", "SITE002", "mêmes sites"),
        ("timestamp", pd.Timestamp("2023-01-01"), "chronologiques"),
        ("consumption_kwh", -1.0, "cibles"),
        ("consumption_kwh", np.nan, "cibles"),
    ],
)
def test_bootstrap_rejects_invalid_test_split(parquet_splits, column, value, message):
    path = parquet_splits / "test.parquet"
    frame = pd.read_parquet(path)
    frame[column] = value
    frame.to_parquet(path)
    with pytest.raises(ValueError, match=message):
        load_bootstrap(str(parquet_splits))


def test_bootstrap_requires_test_parquet(parquet_splits):
    (parquet_splits / "test.parquet").unlink()
    with pytest.raises(FileNotFoundError):
        load_bootstrap(str(parquet_splits))


def test_bootstrap_reads_the_same_three_splits_from_s3(parquet_splits):
    from io import BytesIO
    from unittest.mock import Mock

    client = Mock()
    client.get_object.side_effect = lambda **kwargs: {
        "Body": BytesIO((parquet_splits / kwargs["Key"].split("/")[-1]).read_bytes())
    }
    train, validation, test, manifest = load_bootstrap("s3://datasets/bootstrap/v1", client)
    assert len(train) == len(validation) == len(test) == 1
    assert set(manifest) == {"train", "validation", "test"}
    assert [call.kwargs["Key"] for call in client.get_object.call_args_list] == [
        "bootstrap/v1/train.parquet",
        "bootstrap/v1/validation.parquet",
        "bootstrap/v1/test.parquet",
    ]
    assert train.columns.tolist() == ["timestamp", *FEATURES, "consumption_kwh"]
    assert "temperature_celsius" not in train
