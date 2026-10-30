"""Run one trial: python -m training.train --config configs/ridge.yaml"""

import argparse
from pathlib import Path
from tempfile import TemporaryDirectory
from time import perf_counter
import json
import os
import uuid

import mlflow
import mlflow.sklearn
import numpy as np
import yaml

from .data import FEATURES, TARGET, load_data
from .metrics import evaluate, flatten_metrics
from .models import build_pipeline
from .tracking import connect, log_context, log_pipeline


def read_config(path: Path) -> dict:
    config = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(config, dict):
        raise ValueError("La configuration doit être un objet YAML.")
    for key in ("model", "experiment", "run_name", "features", "parameters"):
        if key not in config:
            raise ValueError(f"Clé de configuration manquante : {key}")
    features = config["features"]
    if (not isinstance(features, list) or not features or len(features) != len(set(features))
            or not set(features).issubset(FEATURES)):
        raise ValueError(f"Les features doivent être uniques et choisies parmi {FEATURES}.")
    if not isinstance(config["parameters"], dict):
        raise ValueError("parameters doit contenir les paramètres d'un seul essai.")
    return config


def run(config_path: Path, data_directory: Path, tracking_uri: str, campaign_id: str) -> dict:
    config = read_config(config_path)
    data = load_data(data_directory)
    features = config["features"]
    pipeline, preprocessing = build_pipeline(config["model"], features, config["parameters"])
    x_train, y_train = data.train[features], data.train[TARGET]
    x_validation = data.validation[features]
    connect(tracking_uri, config["experiment"])

    with mlflow.start_run(run_name=config["run_name"], tags={
        "model_family": config["model"], "campaign_id": campaign_id,
        **config.get("tags", {}),
    }) as active:
        log_context(config, config_path, data, features, preprocessing)
        started = perf_counter()
        pipeline.fit(x_train, y_train)
        fit_seconds = perf_counter() - started
        started = perf_counter()
        train_prediction = pipeline.predict(x_train)
        validation_prediction = pipeline.predict(x_validation)
        predict_seconds = perf_counter() - started
        train_report = evaluate(data.train, train_prediction)
        validation_report = evaluate(data.validation, validation_prediction)
        metrics = {
            **flatten_metrics("train", train_report),
            **flatten_metrics("val", validation_report),
            "fit_seconds": fit_seconds, "predict_seconds": predict_seconds,
        }
        if all(report["global"]["macro_nmae_pct"] is not None for report in [train_report, validation_report]):
            metrics["generalization_gap_nmae_pct"] = (
                validation_report["global"]["macro_nmae_pct"] - train_report["global"]["macro_nmae_pct"]
            )
        mlflow.log_metrics(metrics)
        mlflow.log_dict({"train": train_report, "validation": validation_report}, "metrics_by_site.json")
        with TemporaryDirectory(prefix="ml-training-") as temporary:
            path = Path(temporary) / "validation_predictions.parquet"
            prediction_frame = data.validation[["timestamp", "site_id", TARGET]].copy()
            prediction_frame["prediction_kwh"] = validation_prediction
            prediction_frame.to_parquet(path, index=False)
            mlflow.log_artifact(str(path), artifact_path="predictions")
        sample = x_train.head(7)
        model_info = log_pipeline(pipeline, sample, train_prediction[:len(sample)])
        restored = mlflow.sklearn.load_model(model_info.model_uri)
        restored_prediction = restored.predict(x_validation)
        np.testing.assert_allclose(restored_prediction, validation_prediction, rtol=0, atol=1e-10)
        mlflow.set_tag("model_reload_verified", "true")
        result = {
            "model": config["model"], "run_id": active.info.run_id,
            "model_uri": model_info.model_uri, "experiment": config["experiment"],
            "campaign_id": campaign_id, "features": features,
            "train_rows": len(data.train), "validation_rows": len(data.validation),
            "train": train_report["global"], "validation": validation_report["global"],
            "validation_by_site": validation_report["by_site"],
        }
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="Un essai supervisé sur train et validation, suivi dans MLflow.")
    parser.add_argument("--config", required=True, type=Path, help="Configuration YAML d'un seul modèle.")
    parser.add_argument("--data-dir", type=Path, default=Path(os.environ.get("TRAINING_DATA_DIR", ".data/ml/splits")))
    parser.add_argument("--tracking-uri", default=os.environ.get("MLFLOW_TRACKING_URI"))
    parser.add_argument("--campaign-id", default=None, help="Identifiant commun pour comparer plusieurs essais.")
    args = parser.parse_args()
    result = run(args.config, args.data_dir, args.tracking_uri, args.campaign_id or uuid.uuid4().hex)
    print(json.dumps(result, ensure_ascii=False, allow_nan=False))


if __name__ == "__main__":
    main()
