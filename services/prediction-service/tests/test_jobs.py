from concurrent.futures import Future
from contextlib import contextmanager
from datetime import UTC, datetime
from uuid import UUID
from zoneinfo import ZoneInfo

import pytest

from prediction_service import jobs
from prediction_service.settings import Settings


def test_training_and_forecast_claim_jobs(monkeypatch):
    calls = []
    settings = Settings(database_url="postgresql://unused")
    monkeypatch.setattr(jobs, "get_settings", lambda: settings)

    @contextmanager
    def claim(_url, kind, key, trigger):
        calls.append((kind, key, trigger))
        yield UUID(int=1)

    monkeypatch.setattr(jobs, "claimed_job", claim)
    monkeypatch.setattr(jobs, "train_challenger", lambda *args: calls.append("trained"))
    monkeypatch.setattr(jobs, "generate_forecast", lambda *args: UUID(int=2))
    monkeypatch.setattr(jobs, "log_forecast_errors", lambda *args: calls.append("monitored"))
    jobs._training("scheduled", "2026-10-26")
    monkeypatch.setattr(jobs, "latest_hour", lambda *args: None)
    with pytest.raises(ValueError, match="trop ancien"):
        jobs._forecast("2026-10-26T12:00Z")
    monkeypatch.setattr(jobs, "latest_hour", lambda *args: datetime.now(UTC))
    jobs._forecast("2026-10-26T12:00Z")
    assert calls == [
        ("training", "2026-10-26", "scheduled"),
        "trained",
        ("forecast", "2026-10-26T12:00Z", "scheduled"),
        "monitored",
    ]


def test_monitoring_runs_only_after_a_publication_and_never_fails_the_forecast(monkeypatch, caplog):
    settings = Settings(database_url="postgresql://unused")
    monkeypatch.setattr(jobs, "get_settings", lambda: settings)
    monkeypatch.setattr(jobs, "latest_hour", lambda *args: datetime.now(UTC))
    monkeypatch.setattr(jobs, "generate_forecast", lambda *args: UUID(int=2))
    monitored = []

    def broken_monitoring(*_args):
        monitored.append(True)
        raise RuntimeError("base indisponible")

    monkeypatch.setattr(jobs, "log_forecast_errors", broken_monitoring)

    @contextmanager
    def already_published(*_args):
        yield None

    monkeypatch.setattr(jobs, "claimed_job", already_published)
    jobs._forecast("2026-10-26T12:00Z")
    assert not monitored

    @contextmanager
    def claim(*_args):
        yield UUID(int=1)

    monkeypatch.setattr(jobs, "claimed_job", claim)
    jobs._forecast("2026-10-26T12:00Z")
    assert monitored == [True]
    assert "Suivi du modèle impossible" in caplog.text


def test_forecast_key_is_the_current_utc_hour():
    paris = datetime(2026, 10, 26, 15, 5, 42, tzinfo=UTC).astimezone(ZoneInfo("Europe/Paris"))
    assert jobs.forecast_key(paris) == "2026-10-26T15:00Z"


@pytest.mark.parametrize(
    ("instant", "last_success", "expected_trigger", "forecast_expected"),
    [
        (datetime(2026, 10, 26, 0, 0, tzinfo=UTC), None, "scheduled", False),
        # 00:05 à Paris : les prévisions tournent aussi la nuit, avant l'entraînement de 01:00.
        (
            datetime(2026, 10, 25, 23, 5, tzinfo=UTC),
            datetime(2026, 10, 25, 1, tzinfo=UTC),
            None,
            True,
        ),
        (datetime(2026, 10, 26, 12, 5, tzinfo=UTC), None, "catchup", True),
        (
            datetime(2026, 10, 26, 12, 5, tzinfo=UTC),
            datetime(2026, 10, 26, 11, tzinfo=UTC),
            None,
            True,
        ),
    ],
)
def test_scheduler_decides_training_and_forecast(
    monkeypatch, instant, last_success, expected_trigger, forecast_expected
):
    settings = Settings(database_url="postgresql://unused", mlflow_tracking_uri="http://unused")
    monkeypatch.setattr(jobs, "get_settings", lambda: settings)

    class Clock:
        @staticmethod
        def now(zone):
            return instant.astimezone(zone)

    class Executor:
        def __init__(self, **_kwargs):
            pass

        def submit(self, function, *args):
            result = Future()
            result.set_result(function(*args))
            return result

    calls = []
    monkeypatch.setattr(jobs, "datetime", Clock)
    monkeypatch.setattr(jobs, "ThreadPoolExecutor", Executor)
    monkeypatch.setattr(jobs, "last_successful_training", lambda *args: last_success)
    monkeypatch.setattr(jobs, "_training", lambda trigger, key: calls.append((trigger, key)))
    monkeypatch.setattr(jobs, "_forecast", lambda key: calls.append(("forecast", key)))

    def stop(_seconds):
        raise StopIteration

    monkeypatch.setattr(jobs.time, "sleep", stop)
    with pytest.raises(StopIteration):
        jobs.run_scheduler()
    assert (expected_trigger is not None) == any(kind != "forecast" for kind, _ in calls)
    assert forecast_expected == any(kind == "forecast" for kind, _ in calls)
    if forecast_expected:
        assert ("forecast", instant.strftime("%Y-%m-%dT%H:00Z")) in calls


def test_scheduler_requires_connections(monkeypatch):
    monkeypatch.setattr(jobs, "get_settings", lambda: Settings())
    with pytest.raises(ValueError, match="DATABASE_URL"):
        jobs.run_scheduler()
