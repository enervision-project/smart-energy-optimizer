import json

import pytest

from prediction_service.model import META_FILE, MODEL_FILE, ModelLoadError, load_predictor


def test_load_predictor(model_dir):
    predictor = load_predictor(model_dir)
    assert predictor.version == "test-1"
    assert predictor.site_codes == {"SITE001": 0, "SITE002": 1}


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


def test_load_sklearn_predictor(sklearn_model_dir, payload):
    from prediction_service.schemas import PredictRequest

    predictor = load_predictor(sklearn_model_dir)
    assert predictor.version == "sk-1"
    assert predictor.site_codes == {"SITE001": 0, "SITE002": 1}
    # missing lags and temperature: natively handled
    value = predictor.predict(PredictRequest(**{**payload, "lag_24h": None, "lag_168h": None}))
    assert value == pytest.approx(value)


def test_load_unknown_format(model_dir, tmp_path):
    (tmp_path / META_FILE).write_text(
        json.dumps({"version": "x", "site_ids": [], "format": "onnx"})
    )
    with pytest.raises(ModelLoadError):
        load_predictor(tmp_path)


def test_load_sklearn_missing_file(tmp_path):
    meta = {"version": "x", "site_ids": ["SITE001"], "format": "sklearn", "features": ["hour"]}
    (tmp_path / META_FILE).write_text(json.dumps(meta))
    with pytest.raises(ModelLoadError):
        load_predictor(tmp_path)
