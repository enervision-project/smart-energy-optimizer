"""Chargement et inférence du modèle XGBoost.

Le répertoire du modèle contient :
- model.json       : booster XGBoost (Booster.save_model)
- model_meta.json  : {"version": "...", "site_ids": ["SITE001", "SITE002"]}
                     site_ids = liste ordonnée utilisée à l'entraînement ; la position
                     d'un site dans la liste est la valeur numérique de la feature site_id.
"""

import json
import logging
import math
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import xgboost as xgb

from prediction_service.schemas import PredictRequest

logger = logging.getLogger(__name__)

MODEL_FILE = "model.json"
META_FILE = "model_meta.json"

# ordre des colonnes attendu par le modèle
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
    # XGBoost traite NaN comme une valeur manquante
    return math.nan if value is None else value


@dataclass(frozen=True)
class Predictor:
    booster: xgb.Booster
    version: str
    site_codes: dict[str, int]

    def predict(self, request: PredictRequest) -> float:
        code = self.site_codes.get(request.site_id)
        if code is None:
            raise UnknownSiteError(request.site_id)
        row = [
            code,
            request.hour,
            request.day_of_week,
            request.month,
            _or_nan(request.lag_24h),
            _or_nan(request.lag_168h),
            _or_nan(request.temperature_celsius),
            request.is_working_hours,
        ]
        matrix = xgb.DMatrix(np.array([row], dtype=np.float32), feature_names=FEATURES)
        return float(self.booster.predict(matrix)[0])


def load_predictor(model_dir: Path) -> Predictor:
    model_path, meta_path = model_dir / MODEL_FILE, model_dir / META_FILE
    if not model_path.is_file() or not meta_path.is_file():
        raise ModelLoadError(f"{MODEL_FILE} et {META_FILE} requis dans {model_dir}")
    try:
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        site_ids = [str(s) for s in meta["site_ids"]]
        version = str(meta["version"])
        booster = xgb.Booster()
        booster.load_model(model_path)
    except (OSError, ValueError, KeyError, TypeError, xgb.core.XGBoostError) as exc:
        raise ModelLoadError(f"modèle illisible dans {model_dir} : {exc}") from exc
    # un seul thread : l'instance est partagée avec la base et le reste de la stack
    booster.set_param({"nthread": 1})
    logger.info("modèle %s chargé (%d sites)", version, len(site_ids))
    return Predictor(booster, version, {site: i for i, site in enumerate(site_ids)})
