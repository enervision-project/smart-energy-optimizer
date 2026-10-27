from datetime import UTC, datetime, timedelta
from uuid import UUID

import mlflow
import pandas as pd
from mlflow import MlflowClient

from prediction_service import training
from prediction_service.datasets import FEATURES, load_bootstrap
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
    frame.iloc[: 16 * 48].to_parquet(bootstrap / "train.parquet")
    frame.iloc[16 * 48 : 18 * 48].to_parquet(bootstrap / "validation.parquet")
    test_frame = frame.iloc[18 * 48 :].copy()
    test_frame["consumption_kwh"] += 60
    test_frame.to_parquet(bootstrap / "test.parquet")
    train, validation, test, manifest = load_bootstrap(str(bootstrap))
    assert manifest["train"]["rows"] == len(train) == 768
    assert len(validation) == len(test) == 96
    assert set(train.site_id) == set(validation.site_id)
    assert train.timestamp.max() < validation.timestamp.min()
    assert validation.timestamp.max() < test.timestamp.min()
    assert set(manifest) == {"train", "validation", "test"}

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
    from prediction_service import repository

    def reject_sql(*_args, **_kwargs):
        raise AssertionError("L'entraînement historique ne doit pas lire PostgreSQL.")

    monkeypatch.setattr(repository.psycopg, "connect", reject_sql)
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
    assert first["train_rows"] == len(train)
    assert first["validation_rows"] == len(validation)
    assert first["test_rows"] == len(test)
    run = MlflowClient().get_run(first["run_id"])
    assert run.data.tags["promotion_metric"] == "test_macro_nmae_pct"
    assert first["challenger_score"] == run.data.metrics["test_macro_nmae_pct"]
    assert run.data.metrics["test_macro_nmae_pct"] != run.data.metrics["val_macro_nmae_pct"]
    assert training.last_successful_training(tracking_uri, "coverage-training") is not None
    second = training.train_challenger(settings, UUID(int=2), "scheduled")
    assert second["promoted"] is False
    assert second["champion_score"] is not None
    assert second["version"] == "2"
    second_run = MlflowClient().get_run(second["run_id"])
    assert second["champion_score"] == second_run.data.metrics["champion_test_macro_nmae_pct"]
    assert second["champion_score"] == first["challenger_score"]
