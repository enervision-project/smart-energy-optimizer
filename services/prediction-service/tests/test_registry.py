import joblib
import mlflow
import mlflow.sklearn
import pandas as pd
from mlflow import MlflowClient

from prediction_service.registry import (
    activate_cached,
    cached_predictor,
    champion_version,
    prepare_version,
)


def test_registry_alias_and_cache_round_trip(tmp_path, sklearn_model_dir):
    mlflow.set_tracking_uri(f"sqlite:///{tmp_path / 'mlflow.db'}")
    mlflow.set_registry_uri(mlflow.get_tracking_uri())
    MlflowClient().create_experiment("registry-test", artifact_location=str(tmp_path / "artifacts"))
    mlflow.set_experiment("registry-test")
    pipeline = joblib.load(sklearn_model_dir / "model.joblib")
    sample = pd.DataFrame(
        [
            {
                "site_id": "SITE001",
                "hour": 12,
                "day_of_week": 0,
                "month": 1,
                "is_working_hours": 1,
            }
        ]
    )
    with mlflow.start_run():
        info = mlflow.sklearn.log_model(
            pipeline,
            name="model",
            input_example=sample,
            serialization_format=mlflow.sklearn.SERIALIZATION_FORMAT_CLOUDPICKLE,
        )
        version = mlflow.register_model(info.model_uri, "hourly-test")
    client = MlflowClient()
    assert champion_version(client, "hourly-test") is None
    predictor = prepare_version(tmp_path / "cache", "hourly-test", str(version.version))
    client.set_registered_model_alias("hourly-test", "champion", version.version)
    activate_cached(tmp_path / "cache", str(version.version))
    assert champion_version(client, "hourly-test") == str(version.version)
    assert cached_predictor(tmp_path / "cache").version == predictor.version
