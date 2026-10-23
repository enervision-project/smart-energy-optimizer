"""Chargement et inférence du modèle (XGBoost ou scikit-learn).

Le répertoire du modèle contient model_meta.json et le fichier du modèle, selon `format` :
- "xgboost" (défaut) : model.json, booster XGBoost (Booster.save_model), colonnes dans l'ordre
  de FEATURES ; la position d'un site dans `site_ids` est la valeur numérique de site_id.
- "sklearn" : model.joblib, pipeline scikit-learn complet (prétraitements inclus) qui reçoit
  un DataFrame des colonnes listées dans `features` (site_id en texte).

model_meta.json : {"version": "...", "format": "xgboost|sklearn", "site_ids": ["SITE001", ...],
"features": [...]}. `features` n'est lu que pour sklearn.
Pour changer de moteur, il suffit de déposer d'autres fichiers : le code de l'API ne change pas.
"""

import json
import logging
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

import numpy as np

from prediction_service.schemas import PredictRequest

logger = logging.getLogger(__name__)

MODEL_FILE = "model.json"
SKLEARN_MODEL_FILE = "model.joblib"
META_FILE = "model_meta.json"
DEFAULT_FORMAT = "xgboost"

# ordre des colonnes attendu par le modèle XGBoost
FEATURES = [
    "site_id",
    "hour",
    "day_of_week",
    "month",
    "lag_24h",
    "lag_168h",
    "temperature_celsius",
    "is_working_hours",
]


class UnknownSiteError(ValueError):
    """Le site n'existait pas dans les données d'entraînement."""


class ModelLoadError(RuntimeError):
    """Les fichiers du modèle sont absents ou invalides."""


def _or_nan(value: float | None) -> float:
    # XGBoost et scikit-learn (HistGradientBoosting) traitent NaN comme une valeur manquante
    return math.nan if value is None else value


class Backend(Protocol):
    """Moteur d'inférence : reçoit le site (texte et code) et les features numériques."""

    def predict(self, site_id: str, site_code: int, values: dict[str, float]) -> float: ...


class XGBoostBackend:
    def __init__(self, booster) -> None:
        self._booster = booster

    def predict(self, site_id: str, site_code: int, values: dict[str, float]) -> float:
        import xgboost as xgb

        row = [site_code, *(values[name] for name in FEATURES[1:])]
        matrix = xgb.DMatrix(np.array([row], dtype=np.float32), feature_names=FEATURES)
        return float(self._booster.predict(matrix)[0])


class SklearnBackend:
    def __init__(self, pipeline, features: list[str]) -> None:
        self._pipeline = pipeline
        self._features = features

    def predict(self, site_id: str, site_code: int, values: dict[str, float]) -> float:
        import pandas as pd

        row = {"site_id": site_id, **values}
        frame = pd.DataFrame([row], columns=self._features)
        return float(self._pipeline.predict(frame)[0])


@dataclass(frozen=True)
class Predictor:
    backend: Backend
    version: str
    site_codes: dict[str, int]

    def predict(self, request: PredictRequest) -> float:
        code = self.site_codes.get(request.site_id)
        if code is None:
            raise UnknownSiteError(request.site_id)
        values = {
            "hour": request.hour,
            "day_of_week": request.day_of_week,
            "month": request.month,
            "lag_24h": _or_nan(request.lag_24h),
            "lag_168h": _or_nan(request.lag_168h),
            "temperature_celsius": _or_nan(request.temperature_celsius),
            "is_working_hours": request.is_working_hours,
        }
        return self.backend.predict(request.site_id, code, values)


def _load_xgboost(model_dir: Path) -> Backend:
    import xgboost as xgb

    booster = xgb.Booster()
    booster.load_model(model_dir / MODEL_FILE)
    # un seul thread : l'instance est partagée avec la base et le reste de la stack
    booster.set_param({"nthread": 1})
    return XGBoostBackend(booster)


def _load_sklearn(model_dir: Path, meta: dict) -> Backend:
    import joblib

    features = [str(name) for name in meta["features"]]
    unknown = set(features) - set(FEATURES)
    if unknown:
        raise ValueError(f"features inconnues : {sorted(unknown)}")
    # fichier déposé par l'équipe dans le volume du modèle : source de confiance
    pipeline = joblib.load(model_dir / SKLEARN_MODEL_FILE)
    if hasattr(pipeline, "n_jobs"):
        pipeline.set_params(n_jobs=1)
    return SklearnBackend(pipeline, features)


def load_predictor(model_dir: Path) -> Predictor:
    meta_path = model_dir / META_FILE
    if not meta_path.is_file():
        raise ModelLoadError(f"{META_FILE} requis dans {model_dir}")
    try:
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        site_ids = [str(s) for s in meta["site_ids"]]
        version = str(meta["version"])
        model_format = str(meta.get("format", DEFAULT_FORMAT))
        model_file = {"xgboost": MODEL_FILE, "sklearn": SKLEARN_MODEL_FILE}.get(model_format)
        if model_file is None:
            raise ValueError(f"format inconnu : {model_format}")
        if not (model_dir / model_file).is_file():
            raise ModelLoadError(f"{model_file} requis dans {model_dir}")
        backend = (
            _load_xgboost(model_dir)
            if model_format == "xgboost"
            else _load_sklearn(model_dir, meta)
        )
    except ModelLoadError:
        raise
    except Exception as exc:  # xgboost, joblib et sklearn lèvent des types variés
        raise ModelLoadError(f"modèle illisible dans {model_dir} : {exc}") from exc
    logger.info("modèle %s (%s) chargé (%d sites)", version, model_format, len(site_ids))
    return Predictor(backend, version, {site: i for i, site in enumerate(site_ids)})
