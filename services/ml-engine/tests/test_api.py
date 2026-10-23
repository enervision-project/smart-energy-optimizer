import pytest


def test_health_with_model(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "model_loaded": True, "model_version": "test-1"}


def test_health_without_model(client_without_model):
    response = client_without_model.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "degraded", "model_loaded": False, "model_version": None}


def test_predict(client, payload):
    response = client.post("/predict", json=payload)
    assert response.status_code == 200
    body = response.json()
    assert isinstance(body["prediction"], float)
    assert body["model_version"] == "test-1"


def test_predict_is_deterministic(client, payload):
    first = client.post("/predict", json=payload).json()["prediction"]
    assert client.post("/predict", json=payload).json()["prediction"] == first


def test_predict_without_temperature(client, payload):
    del payload["temperature_celsius"]
    assert client.post("/predict", json=payload).status_code == 200


def test_predict_null_temperature(client, payload):
    payload["temperature_celsius"] = None
    assert client.post("/predict", json=payload).status_code == 200


@pytest.mark.parametrize("field", ["lag_24h", "lag_168h"])
def test_predict_lag_optional(client, payload, field):
    payload[field] = None
    assert client.post("/predict", json=payload).status_code == 200
    del payload[field]
    assert client.post("/predict", json=payload).status_code == 200


def test_predict_all_optional_missing(client, payload):
    for field in ("lag_24h", "lag_168h", "temperature_celsius"):
        payload[field] = None
    assert client.post("/predict", json=payload).status_code == 200


def test_predict_unknown_site(client, payload):
    payload["site_id"] = "SITE_999"
    response = client.post("/predict", json=payload)
    assert response.status_code == 422
    assert "SITE_999" in response.json()["detail"]


def test_predict_without_model(client_without_model, payload):
    response = client_without_model.post("/predict", json=payload)
    assert response.status_code == 503


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("hour", 24),
        ("hour", -1),
        ("day_of_week", 7),
        ("month", 0),
        ("month", 13),
        ("lag_24h", -1),
        ("lag_168h", "abc"),
        ("is_working_hours", 2),
        ("temperature_celsius", 100),
        ("site_id", ""),
        ("site_id", "site-a"),
    ],
)
def test_predict_rejects_invalid_values(client, payload, field, value):
    payload[field] = value
    assert client.post("/predict", json=payload).status_code == 422


@pytest.mark.parametrize("field", ["site_id", "hour", "day_of_week", "month", "is_working_hours"])
def test_predict_requires_field(client, payload, field):
    del payload[field]
    assert client.post("/predict", json=payload).status_code == 422


def test_predict_rejects_unknown_field(client, payload):
    payload["extra"] = 1
    assert client.post("/predict", json=payload).status_code == 422


def test_docs_can_be_disabled(monkeypatch, model_dir):
    from ml_engine.settings import get_settings
    from tests.conftest import _client

    with _client(monkeypatch, model_dir, ENABLE_DOCS="false") as c:
        assert c.get("/docs").status_code == 404
        assert c.get("/openapi.json").status_code == 404
    get_settings.cache_clear()
