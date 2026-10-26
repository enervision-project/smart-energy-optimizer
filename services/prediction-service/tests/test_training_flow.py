from datetime import UTC, datetime, timedelta
from uuid import UUID

import mlflow
import pandas as pd
from mlflow import MlflowClient

from prediction_service import training
from prediction_service.datasets import FEATURES, current_ready, load_bootstrap, make_splits
from prediction_service.settings import Settings


def test_bootstrap_and_training_register_a_champion(tmp_path, monkeypatch):
    rows = []
    start = datetime(2024, 1, 1, tzinfo=UTC)
    for day in range(20):
        for hour in range(24):
            for site in ("SITE001", "SITE002"):
                instant = start + timedelta(days=day, hours=hour)
                rows.append(
                    {
                        "timestamp": instant,
                        "site_id": site,
                        "hour": hour,
                        "day_of_week": instant.weekday(),
                        "month": instant.month,
                        "is_working_hours": int(9 <= hour < 18),
                        "consumption_kwh": float(10 + hour + (site == "SITE002") * 5),
                    }
                )
    bootstrap = tmp_path / "bootstrap"
    bootstrap.mkdir()
    frame = pd.DataFrame(rows)
    frame.iloc[: 18 * 48].to_parquet(bootstrap / "train.parquet")
    frame.iloc[18 * 48 :].to_parquet(bootstrap / "validation.parquet")
    bootstrap_train, bootstrap_validation, manifest = load_bootstrap(str(bootstrap))
    historical = pd.concat([bootstrap_train, bootstrap_validation], ignore_index=True)
    assert len(historical) == 960
    assert manifest["train"]["rows"] == 864
    assert not current_ready(historical.iloc[0:0], historical, 168)
    assert current_ready(historical, historical, 168)
    train, validation = make_splits(bootstrap_train, bootstrap_validation, historical.iloc[0:0], 1)
    assert len(train) == len(bootstrap_train)
    assert len(validation) == len(bootstrap_validation)
    assert set(train.site_id) == set(validation.site_id)

    current = frame.iloc[-48:].copy()
    current["timestamp"] += pd.Timedelta(days=30)
    train_live, validation_live = make_splits(bootstrap_train, bootstrap_validation, current, 1)
    assert set(bootstrap_validation.timestamp).issubset(set(train_live.timestamp))
    assert validation_live.timestamp.min() == current.timestamp.max() - pd.Timedelta(
        days=1
    ) + pd.Timedelta(hours=1)
    assert not set(validation_live.timestamp).intersection(set(train_live.timestamp))

    config = tmp_path / "hgb.yaml"
    config.write_text(
        "model: hist_gradient_boosting\n"
        "experiment: coverage-training\n"
        "run_name: small-hgb\n"
        f"features: {FEATURES!r}\n"
        "parameters:\n"
        "  max_iter: 8\n"
        "  min_samples_leaf: 2\n"
        "  random_state: 42\n",
        encoding="utf-8",
    )
    tracking_uri = f"sqlite:///{tmp_path / 'mlflow.db'}"
    mlflow.set_tracking_uri(tracking_uri)
    mlflow.set_registry_uri(tracking_uri)
    MlflowClient().create_experiment(
        "coverage-training", artifact_location=str(tmp_path / "artifacts")
    )
    monkeypatch.setattr(training, "read_recent_hours", lambda *args: historical.iloc[0:0])
    monkeypatch.setattr(training, "read_site_profiles", lambda *args: [])
    settings = Settings(
        model_dir=tmp_path / "models",
        database_url="postgresql://unused",
        mlflow_tracking_uri=tracking_uri,
        registered_model_name="coverage-hourly",
        training_experiment="coverage-training",
        training_bootstrap_uri=str(bootstrap),
        training_config=config,
        validation_days=1,
    )
    first = training.train_challenger(settings, UUID(int=1), "catchup")
    assert first["promoted"] is True
    assert first["version"] == "1"
    assert training.last_successful_training(tracking_uri, "coverage-training") is not None
    second = training.train_challenger(settings, UUID(int=2), "scheduled")
    assert second["promoted"] is False
    assert second["champion_score"] is not None
    assert second["version"] == "2"
