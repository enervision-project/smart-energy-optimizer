"""MLflow Model Registry et cache local versionné du champion."""

import json
import logging
import os
from pathlib import Path
from tempfile import TemporaryDirectory

import joblib
import mlflow
import mlflow.sklearn
from mlflow import MlflowClient
from mlflow.exceptions import MlflowException

from prediction_service.model import ModelLoadError, Predictor, load_predictor

logger = logging.getLogger(__name__)
CURRENT_FILE = "current.json"


def configure(tracking_uri: str) -> None:
    mlflow.set_tracking_uri(tracking_uri)


def champion_version(client: MlflowClient, model_name: str) -> str | None:
    try:
        return str(client.get_model_version_by_alias(model_name, "champion").version)
    except MlflowException as error:
        if getattr(error, "error_code", None) == "RESOURCE_DOES_NOT_EXIST":
            return None
        if (
            getattr(error, "error_code", None) == "INVALID_PARAMETER_VALUE"
            and "alias champion not found" in str(error).lower()
        ):
            return None
        raise


def _cache_dir(root: Path, version: str) -> Path:
    if not version.isdecimal():
        raise ValueError("Version Registry invalide.")
    return root / "versions" / version


def cached_predictor(root: Path) -> Predictor:
    marker = root / CURRENT_FILE
    if marker.is_file():
        version = str(json.loads(marker.read_text(encoding="utf-8"))["version"])
        return load_predictor(_cache_dir(root, version))
    return load_predictor(root)  # compatibilité avec les exports manuels existants


def prepare_version(root: Path, model_name: str, version: str) -> Predictor:
    """Télécharge et valide un modèle avant de modifier le pointeur actif."""
    target = _cache_dir(root, version)
    if target.is_dir():
        return load_predictor(target)
    root.joinpath("versions").mkdir(parents=True, exist_ok=True)
    pipeline = mlflow.sklearn.load_model(f"models:/{model_name}/{version}")
    features = (
        list(pipeline.feature_names_in_)
        if hasattr(pipeline, "feature_names_in_")
        else ["site_id", "hour", "day_of_week", "month", "is_working_hours"]
    )
    expected = ["site_id", "hour", "day_of_week", "month", "is_working_hours"]
    if features != expected:
        raise ModelLoadError(f"Signature du modèle incompatible : {features}")
    sites = pipeline.named_steps["preprocessing"].named_transformers_["site"].categories_[0]
    with TemporaryDirectory(prefix=".model-", dir=root / "versions") as temporary:
        staged = Path(temporary) / "model"
        staged.mkdir()
        joblib.dump(pipeline, staged / "model.joblib")
        (staged / "model_meta.json").write_text(
            json.dumps(
                {
                    "version": version,
                    "format": "sklearn",
                    "features": features,
                    "site_ids": [str(site) for site in sites],
                    "model_name": model_name,
                }
            ),
            encoding="utf-8",
        )
        predictor = load_predictor(staged)
        # Vérifie aussi l'inférence réelle avant de publier ce cache.
        from prediction_service.schemas import PredictRequest

        if len(sites) == 0:
            raise ModelLoadError("Le modèle ne connaît aucun site.")
        predictor.predict(
            PredictRequest(
                site_id=str(sites[0]), hour=12, day_of_week=0, month=1, is_working_hours=1
            )
        )
        staged.rename(target)
    return predictor


def activate_cached(root: Path, version: str) -> None:
    marker = root / CURRENT_FILE
    temporary = root / ".current.json.tmp"
    temporary.write_text(json.dumps({"version": version}), encoding="utf-8")
    os.replace(temporary, marker)


def refresh_champion(root: Path, tracking_uri: str, model_name: str) -> Predictor:
    configure(tracking_uri)
    client = MlflowClient()
    version = champion_version(client, model_name)
    if version is None:
        raise ModelLoadError("Aucun alias champion dans MLflow.")
    predictor = prepare_version(root, model_name, version)
    activate_cached(root, version)
    logger.info("Champion actif : %s version %s", model_name, version)
    return predictor


def changed_champion(
    root: Path, tracking_uri: str, model_name: str, current_version: str | None
) -> Predictor | None:
    configure(tracking_uri)
    version = champion_version(MlflowClient(), model_name)
    if version is None or version == current_version:
        return None
    predictor = prepare_version(root, model_name, version)
    activate_cached(root, version)
    return predictor


def available_predictor(root: Path, tracking_uri: str | None, model_name: str) -> Predictor:
    if tracking_uri:
        try:
            return refresh_champion(root, tracking_uri, model_name)
        except Exception:
            logger.exception("MLflow indisponible, repli sur le cache local")
    return cached_predictor(root)
