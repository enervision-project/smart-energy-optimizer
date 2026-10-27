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


@pytest.mark.parametrize(
    "now",
    [
        datetime(2026, 10, 27, 6, 5, tzinfo=UTC),  # heure d'hiver (UTC+1)
        datetime(2026, 7, 7, 6, 5, tzinfo=UTC),  # heure d'été (UTC+2)
    ],
)
def test_forecast_features_follow_utc_hours_whatever_the_season(monkeypatch, tmp_path, now):
    from prediction_service import forecast

    recorded = []

    class RecordingPredictor:
        version = "7"

        def __init__(self):
            self.site_codes = {"SITE001": 0}

        def predict(self, request):
            recorded.append(request)
            return 1.0

    monkeypatch.setattr(forecast, "available_predictor", lambda *args: RecordingPredictor())
    monkeypatch.setattr(
        forecast,
        "read_site_profiles",
        lambda *args: [SiteProfile("SITE001", 8, 19, (1, 2, 3, 4, 5))],
    )
    # Pas d'historique : aucune prévision du passé, seulement les 24 heures à venir.
    monkeypatch.setattr(forecast, "read_measured_hours", lambda *args: [])
    monkeypatch.setattr(forecast, "save_forecast", lambda *args: UUID(int=1))
    settings = Settings(model_dir=tmp_path, database_url="postgresql://unused")

    generate_forecast(settings, UUID(int=2), now)

    # Un seul site : une requête par heure prévue, dans l'ordre de next_24_hours.
    by_utc_hour = {
        instant.hour: request for instant, request in zip(next_24_hours(now), recorded, strict=True)
    }
    # Mardi, heures de travail 8 h-19 h UTC.
    assert all(hour == request.hour for hour, request in by_utc_hour.items())
    assert by_utc_hour[7].is_working_hours == 0
    assert by_utc_hour[8].is_working_hours == 1
    assert by_utc_hour[18].is_working_hours == 1
    assert by_utc_hour[19].is_working_hours == 0
    assert by_utc_hour[8].day_of_week == 1


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
    monkeypatch.setattr(forecast, "read_measured_hours", lambda *args: [])
    monkeypatch.setattr(forecast, "save_forecast", save)
    settings = Settings(model_dir=tmp_path, database_url="postgresql://unused")
    assert generate_forecast(
        settings, UUID(int=2), datetime(2026, 10, 26, 0, 5, tzinfo=UTC)
    ) == UUID(int=1)
    assert captured["args"][3] == "7"
    assert len(captured["args"][4]) == len(captured["args"][5]) == 24
    assert all(np.isfinite(value) for _, _, value, _, _ in captured["args"][5])
    # Sans historique, la prévision du champion est publiée telle quelle (ratio 1).
    assert all(value == raw and ratio == 1.0 for _, _, value, raw, ratio in captured["args"][5])


def test_forecast_applies_the_level_ratio_of_the_last_week(monkeypatch, tmp_path):
    from prediction_service import forecast

    class FlatPredictor:
        """100 kWh en heures travaillées, 50 sinon."""

        version = "7"

        def __init__(self):
            self.site_codes = {"SITE001": 0}

        def predict(self, request):
            return 100.0 if request.is_working_hours else 50.0

    now = datetime(2026, 10, 27, 6, 5, tzinfo=UTC)
    profile = SiteProfile("SITE001", 8, 19, (1, 2, 3, 4, 5))
    end = now.replace(minute=0)
    # Semaine passée : le site consomme 76 % du prévu en journée, 80 % le reste du temps.
    history = []
    for back in range(1, 169):
        hour = end - timedelta(hours=back)
        working = forecast.calendar_request(profile, hour).is_working_hours
        history.append(("SITE001", hour, 76.0 if working else 40.0))
    windows = []

    def measured(_url, start, stop):
        windows.append((start, stop))
        return history

    captured = {}

    def save(*args):
        captured["rows"] = args[5]
        return UUID(int=1)

    monkeypatch.setattr(forecast, "available_predictor", lambda *args: FlatPredictor())
    monkeypatch.setattr(forecast, "read_site_profiles", lambda *args: [profile])
    monkeypatch.setattr(forecast, "read_measured_hours", measured)
    monkeypatch.setattr(forecast, "save_forecast", save)
    settings = Settings(model_dir=tmp_path, database_url="postgresql://unused")

    generate_forecast(settings, UUID(int=2), now)

    assert windows == [(end - timedelta(hours=168), end)]
    by_hour = {hour.hour: (value, raw, ratio) for _, hour, value, raw, ratio in captured["rows"]}
    assert by_hour[10] == pytest.approx((76.0, 100.0, 0.76))
    assert by_hour[22] == pytest.approx((40.0, 50.0, 0.8))


def test_recalibration_can_be_disabled(monkeypatch, tmp_path):
    from prediction_service import forecast

    class FlatPredictor:
        version = "7"

        def __init__(self):
            self.site_codes = {"SITE001": 0}

        def predict(self, _request):
            return 100.0

    def unexpected(*_args):
        raise AssertionError("L'historique ne doit pas être lu.")

    captured = {}
    monkeypatch.setattr(forecast, "available_predictor", lambda *args: FlatPredictor())
    monkeypatch.setattr(
        forecast, "read_site_profiles", lambda *args: [SiteProfile("SITE001", 8, 19, (1,))]
    )
    monkeypatch.setattr(forecast, "read_measured_hours", unexpected)
    monkeypatch.setattr(
        forecast, "save_forecast", lambda *args: captured.setdefault("rows", args[5])
    )
    settings = Settings(
        model_dir=tmp_path, database_url="postgresql://unused", level_recalibration=False
    )

    generate_forecast(settings, UUID(int=2), datetime(2026, 10, 27, 6, 5, tzinfo=UTC))

    assert all(row[2:] == (100.0, 100.0, 1.0) for row in captured["rows"])


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
