import json

import pytest

from ml_engine.model import META_FILE, MODEL_FILE, ModelLoadError, load_predictor


def test_load_predictor(model_dir):
    predictor = load_predictor(model_dir)
    assert predictor.version == "test-1"
    assert predictor.site_codes == {"SITE_001": 0, "SITE_002": 1}


def test_load_missing_files(tmp_path):
    with pytest.raises(ModelLoadError):
        load_predictor(tmp_path)


def test_load_invalid_meta(model_dir, tmp_path):
    (tmp_path / MODEL_FILE).write_bytes((model_dir / MODEL_FILE).read_bytes())
    (tmp_path / META_FILE).write_text(json.dumps({"version": "x"}))
    with pytest.raises(ModelLoadError):
        load_predictor(tmp_path)


def test_load_corrupted_model(model_dir, tmp_path):
    (tmp_path / MODEL_FILE).write_text("pas un modèle")
    (tmp_path / META_FILE).write_bytes((model_dir / META_FILE).read_bytes())
    with pytest.raises(ModelLoadError):
        load_predictor(tmp_path)
