"""Suivi explicite des essais, des données et des pipelines dans MLflow."""

from hashlib import sha256
from importlib.metadata import version
from pathlib import Path
import os

import mlflow
import mlflow.sklearn
import numpy as np
from mlflow.models import infer_signature

from .data import TARGET


def connect(uri: str, experiment: str) -> None:
    if not uri or not uri.startswith(("http://", "https://")):
        raise ValueError("Fournir une URI HTTP(S) du serveur MLflow.")
    mlflow.set_tracking_uri(uri)
    mlflow.tracking.MlflowClient().get_experiment_by_name(experiment)
    mlflow.set_experiment(experiment)


def provenance() -> dict:
    directory = Path(__file__).resolve().parent
    digest = sha256()
    for path in sorted(directory.glob("*.py")):
        digest.update(path.name.encode())
        digest.update(path.read_bytes())
    return {
        "git_revision": os.environ.get("TRAINING_GIT_REVISION", "unknown"),
        "git_dirty": os.environ.get("TRAINING_GIT_DIRTY", "unknown"),
        "training_code_sha256": digest.hexdigest(),
        "versions": {
            package: version(package) for package in
            ["mlflow", "scikit-learn", "pandas", "numpy", "pyarrow", "scipy", "cloudpickle", "PyYAML"]
        },
    }


def log_context(config: dict, config_path: Path, data, features: list[str], preprocessing: dict) -> None:
    context = provenance()
    mlflow.log_params({
        "model_family": config["model"], "features": ",".join(features),
        "feature_count": len(features), "target": TARGET,
        "train_rows": len(data.train), "validation_rows": len(data.validation),
        "train_sha256": data.manifest["train"]["sha256"],
        "validation_sha256": data.manifest["validation"]["sha256"],
        "validation_used_in_fit": False, "clipping": False,
        "serialization_format": "cloudpickle",
        **config["parameters"], **preprocessing,
    })
    mlflow.set_tags({
        "git_revision": context["git_revision"], "git_dirty": context["git_dirty"],
        "training_code_sha256": context["training_code_sha256"],
        "feature_set": ",".join(features),
    })
    mlflow.log_dict(config, "configuration.json")
    mlflow.log_dict(data.manifest, "datasets.json")
    mlflow.log_dict(context, "environment.json")
    mlflow.log_artifact(str(config_path), artifact_path="configuration")
    for name, frame in [("train", data.train), ("validation", data.validation)]:
        dataset = mlflow.data.from_pandas(
            frame, source=data.manifest[name]["path"], targets=TARGET, name=name,
        )
        mlflow.log_input(dataset, context="training" if name == "train" else "validation")


def log_pipeline(pipeline, sample, prediction: np.ndarray):
    requirements = Path(__file__).resolve().parents[1] / "requirements-training.txt"
    return mlflow.sklearn.log_model(
        pipeline, name="model",
        serialization_format=mlflow.sklearn.SERIALIZATION_FORMAT_CLOUDPICKLE,
        signature=infer_signature(sample, prediction), input_example=sample,
        pip_requirements=str(requirements),
    )
