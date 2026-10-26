from datetime import UTC, datetime, timedelta
from itertools import pairwise
from uuid import UUID
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
import pytest

from prediction_service.datasets import FEATURES, current_ready, make_splits, prepare_current
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


def test_current_data_uses_local_calendar_without_temperature():
    frame = pd.DataFrame(
        {
            "site_id": ["SITE001"],
            "timestamp": [datetime(2026, 7, 1, 8, tzinfo=UTC)],
            "consumption_kwh": [10],
        }
    )
    profile = SiteProfile("SITE001", 9, 18, (1, 2, 3, 4, 5))
    prepared = prepare_current(frame, [profile])
    assert prepared.columns.tolist() == ["timestamp", *FEATURES, "consumption_kwh"]
    assert prepared.iloc[0].hour == 10
    assert prepared.iloc[0].is_working_hours == 1
    assert "temperature_celsius" not in prepared


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


def test_splits_reject_missing_validation_sites():
    historical = pd.DataFrame(
        {
            "timestamp": pd.to_datetime(["2024-01-01", "2024-02-01"], utc=True),
            "site_id": ["SITE001", "SITE002"],
            "consumption_kwh": [10.0, 20.0],
        }
    )
    with pytest.raises(ValueError, match="mêmes sites"):
        make_splits(historical, historical.iloc[0:0], validation_days=14)


def test_sparse_sql_does_not_replace_historical_validation():
    historical = pd.DataFrame({"site_id": ["SITE001", "SITE002"]})
    current = pd.DataFrame(
        {
            "site_id": ["SITE001", "SITE002"],
            "consumption_kwh": [10.0, 20.0],
        }
    )
    assert not current_ready(current, historical, 168)
