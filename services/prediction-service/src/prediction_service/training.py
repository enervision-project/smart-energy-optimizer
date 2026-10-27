"""Entraînement quotidien d'un challenger HGB et promotion contrôlée."""

import json
import logging
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID

import mlflow
import mlflow.sklearn
import numpy as np
import yaml
from mlflow import MlflowClient
from mlflow.models import infer_signature
from training.metrics import evaluate, flatten_metrics
from training.models import build_pipeline

from prediction_service.datasets import (
    FEATURES,
    TARGET,
    load_bootstrap,
)
from prediction_service.registry import (
    activate_cached,
    champion_version,
    configure,
    prepare_version,
)
from prediction_service.settings import Settings

logger = logging.getLogger(__name__)


def last_successful_training(tracking_uri: str, experiment_name: str) -> datetime | None:
    configure(tracking_uri)
    client = MlflowClient()
    experiment = client.get_experiment_by_name(experiment_name)
    if experiment is None:
        return None
    runs = client.search_runs(
        [experiment.experiment_id],
        filter_string=(
            "attributes.status = 'FINISHED' and tags.run_type = 'training' "
            "and tags.training_success = 'true'"
        ),
        order_by=["attributes.end_time DESC"],
        max_results=1,
    )
    if not runs:
        return None
    return datetime.fromtimestamp(runs[0].info.end_time / 1000, UTC)


def needs_catchup(last_success: datetime | None, now: datetime) -> bool:
    if last_success is None:
        return True
    return now.astimezone(UTC) - last_success.astimezone(UTC) > timedelta(hours=25)


def should_promote(champion_score: float | None, challenger_score: float | None) -> bool:
    if challenger_score is None or not np.isfinite(challenger_score):
        return False
    if champion_score is None:
        return True
    return bool(
        np.isfinite(champion_score)
        and champion_score > 0
        and challenger_score <= 0.96 * champion_score
    )


def _configuration(path: Path) -> dict:
    config = yaml.safe_load(path.read_text(encoding="utf-8"))
    if config["model"] != "hist_gradient_boosting" or config["features"] != FEATURES:
        raise ValueError("La configuration de production doit être HGB à cinq features.")
    return config


def train_challenger(settings: Settings, job_id: UUID, trigger: str) -> dict:
    """Le succès d'entraînement inclut enregistrement et rechargement du challenger."""
    if not settings.training_bootstrap_uri:
        raise ValueError("TRAINING_BOOTSTRAP_URI requis pour entraîner le modèle initial.")
    config = _configuration(settings.training_config)
    if config["experiment"] != settings.training_experiment:
        raise ValueError("TRAINING_EXPERIMENT ne correspond pas à la configuration du modèle.")
    train, validation, test, bootstrap_manifest = load_bootstrap(settings.training_bootstrap_uri)
    x_train, y_train = train[FEATURES], train[TARGET].astype(float)
    x_validation = validation[FEATURES]
    x_test = test[FEATURES]
    configure(settings.mlflow_tracking_uri)
    mlflow.set_experiment(config["experiment"])
    client = MlflowClient()
    with mlflow.start_run(
        run_name=config["run_name"],
        tags={
            "run_type": "training",
            "trigger": trigger,
            "job_id": str(job_id),
            "dataset_source": "historical_parquet",
            "promotion_metric": "test_macro_nmae_pct",
        },
    ) as run:
        mlflow.log_dict(
            {
                "bootstrap": bootstrap_manifest,
                "current_used": False,
                "train_rows": len(train),
                "validation_rows": len(validation),
                "test_rows": len(test),
                "promotion_dataset": "test.parquet",
            },
            "datasets.json",
        )
        mlflow.log_dict(config, "configuration.json")
        mlflow.log_params(
            {
                "features": ",".join(FEATURES),
                "train_rows": len(train),
                "validation_rows": len(validation),
                "test_rows": len(test),
                **config["parameters"],
            }
        )
        pipeline, _ = build_pipeline(config["model"], FEATURES, config["parameters"])
        pipeline.fit(x_train, y_train)
        train_prediction = pipeline.predict(x_train)
        validation_prediction = pipeline.predict(x_validation)
        challenger_prediction = pipeline.predict(x_test)
        train_report = evaluate(train, train_prediction)
        validation_report = evaluate(validation, validation_prediction)
        challenger_report = evaluate(test, challenger_prediction)
        challenger_score = challenger_report["global"]["macro_nmae_pct"]
        if challenger_score is None:
            raise ValueError("NMAE macro du test indéfinie : consommation moyenne nulle d'un site.")
        mlflow.log_metrics(
            {
                **flatten_metrics("train", train_report),
                **flatten_metrics("val", validation_report),
                **flatten_metrics("test", challenger_report),
            }
        )
        mlflow.log_dict(
            {"train": train_report, "validation": validation_report, "test": challenger_report},
            "metrics_by_site.json",
        )
        sample = x_train.head(min(7, len(x_train)))
        model_info = mlflow.sklearn.log_model(
            pipeline,
            name="model",
            serialization_format=mlflow.sklearn.SERIALIZATION_FORMAT_CLOUDPICKLE,
            signature=infer_signature(sample, pipeline.predict(sample)),
            input_example=sample,
        )
        restored = mlflow.sklearn.load_model(model_info.model_uri)
        np.testing.assert_allclose(
            restored.predict(x_test), challenger_prediction, rtol=0, atol=1e-10
        )
        model_version = mlflow.register_model(model_info.model_uri, settings.registered_model_name)
        version = str(model_version.version)
        champion = champion_version(client, settings.registered_model_name)
        champion_score = None
        if champion is not None:
            current_model = mlflow.sklearn.load_model(
                f"models:/{settings.registered_model_name}/{champion}"
            )
            champion_prediction = current_model.predict(x_test)
            champion_report = evaluate(test, champion_prediction)
            champion_score = champion_report["global"]["macro_nmae_pct"]
            if champion_score is None:
                raise ValueError("NMAE macro du champion sur le test indéfinie.")
            mlflow.log_metric("champion_test_macro_nmae_pct", champion_score)
            mlflow.log_dict(champion_report, "champion_test_metrics_by_site.json")
        promote = should_promote(champion_score, challenger_score)
        if promote:
            # Vérifie le modèle Registry dans le format réellement servi avant l'alias.
            prepare_version(settings.model_dir, settings.registered_model_name, version)
            client.set_registered_model_alias(settings.registered_model_name, "champion", version)
            try:
                activate_cached(settings.model_dir, version)
            except Exception:
                if champion is None:
                    client.delete_registered_model_alias(settings.registered_model_name, "champion")
                else:
                    client.set_registered_model_alias(
                        settings.registered_model_name, "champion", champion
                    )
                raise
        mlflow.set_tags(
            {
                "training_success": "true",
                "promoted": str(promote).lower(),
                "registered_model_version": version,
                "previous_champion_version": champion or "none",
            }
        )
        result = {
            "run_id": run.info.run_id,
            "version": version,
            "promoted": promote,
            "champion_score": champion_score,
            "challenger_score": challenger_score,
            "train_rows": len(train),
            "validation_rows": len(validation),
            "test_rows": len(test),
            "promotion_metric": "test_macro_nmae_pct",
        }
        logger.info("Entraînement terminé : %s", json.dumps(result))
        return result
