import json
from pathlib import Path

import numpy as np
import pytest
import xgboost as xgb
from fastapi.testclient import TestClient

from ml_engine.main import create_app
from ml_engine.model import FEATURES, META_FILE, MODEL_FILE
from ml_engine.settings import get_settings

SITE_IDS = ["SITE_001", "SITE_002"]


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
        "site_id": "SITE_001",
        "hour": 14,
        "day_of_week": 2,
        "month": 10,
        "lag_24h": 12.5,
        "lag_168h": 11.0,
        "temperature_celsius": 18.2,
        "is_working_hours": 1,
    }
