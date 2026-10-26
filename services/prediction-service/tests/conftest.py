import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import pytest
import xgboost as xgb
from fastapi.testclient import TestClient
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OrdinalEncoder

from prediction_service.main import create_app
from prediction_service.model import FEATURES, META_FILE, MODEL_FILE, SKLEARN_MODEL_FILE
from prediction_service.settings import get_settings

SITE_IDS = ["SITE001", "SITE002"]


@pytest.fixture(scope="session")
def model_dir(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Petit modèle réel, entraîné sur des données aléatoires."""
    rng = np.random.default_rng(0)
    features = rng.random((200, len(FEATURES)))
    target = features[:, 4] + features[:, 5]
    booster = xgb.train(
        {"max_depth": 2, "nthread": 1},
        xgb.DMatrix(features, label=target, feature_names=FEATURES),
        num_boost_round=5,
    )
    directory = tmp_path_factory.mktemp("model")
    booster.save_model(directory / MODEL_FILE)
    (directory / META_FILE).write_text(json.dumps({"version": "test-1", "site_ids": SITE_IDS}))
    return directory


@pytest.fixture(scope="session")
def sklearn_model_dir(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Pipeline scikit-learn réel (sans lags), même forme que celui de l'entraînement."""
    rng = np.random.default_rng(0)
    features = [
        "site_id",
        "hour",
        "day_of_week",
        "month",
        "is_working_hours",
    ]
    frame = pd.DataFrame(
        {
            "site_id": rng.choice(SITE_IDS, 200),
            "hour": rng.integers(0, 24, 200),
            "day_of_week": rng.integers(0, 7, 200),
            "month": rng.integers(1, 13, 200),
            "is_working_hours": rng.integers(0, 2, 200),
        }
    )
    preprocessing = ColumnTransformer(
        [
            (
                "site",
                OrdinalEncoder(handle_unknown="use_encoded_value", unknown_value=-1),
                ["site_id"],
            ),
            ("numeric", "passthrough", features[1:]),
        ],
        sparse_threshold=0,
    )
    pipeline = Pipeline(
        [
            ("preprocessing", preprocessing),
            ("model", HistGradientBoostingRegressor(max_iter=5, categorical_features=[0])),
        ]
    )
    pipeline.fit(frame[features], frame["hour"] * 1.0)
    directory = tmp_path_factory.mktemp("sklearn_model")
    joblib.dump(pipeline, directory / SKLEARN_MODEL_FILE)
    meta = {"version": "sk-1", "format": "sklearn", "features": features, "site_ids": SITE_IDS}
    (directory / META_FILE).write_text(json.dumps(meta))
    return directory


def _client(monkeypatch: pytest.MonkeyPatch, model_dir: Path, **env: str):
    monkeypatch.setenv("MODEL_DIR", str(model_dir))
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    get_settings.cache_clear()
    return TestClient(create_app())


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch, model_dir: Path):
    with _client(monkeypatch, model_dir) as c:
        yield c
    get_settings.cache_clear()


@pytest.fixture
def client_without_model(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    with _client(monkeypatch, tmp_path) as c:
        yield c
    get_settings.cache_clear()


@pytest.fixture
def payload() -> dict:
    return {
        "site_id": "SITE001",
        "hour": 14,
        "day_of_week": 2,
        "month": 10,
        "lag_24h": 12.5,
        "lag_168h": 11.0,
        "is_working_hours": 1,
    }
