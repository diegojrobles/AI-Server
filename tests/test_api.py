"""API tests.

These run against Flask's test client with a faked model. No live server, no
network, no model download. The previous ``test_server.py`` made real HTTP
calls to localhost:5000 and could never pass in CI.
"""

import pytest

from tests.conftest import FakeModelHandler


def test_health_is_public_and_reports_model(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["status"] == "healthy"
    assert body["model"]


def test_health_does_not_force_a_model_load(client):
    """Health must stay cheap: hitting it should not instantiate the model."""
    from app import server

    server.set_model_handler(None)
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.get_json()["model_loaded"] is False
    assert server._model_handler is None


def test_models_lists_available_models(client):
    resp = client.get("/models")
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["current_model"] in body["available_models"]


def test_predict_returns_prediction(client, auth, fake_model):
    resp = client.post("/predict", json={"text": "I love this"}, headers=auth)
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["input"] == "I love this"
    assert body["prediction"] == [{"label": "POSITIVE", "score": 0.99}]
    assert fake_model.calls == ["I love this"]


def test_predict_rejects_missing_api_key(client, fake_model):
    resp = client.post("/predict", json={"text": "hello"})
    assert resp.status_code == 401
    assert fake_model.calls == []


def test_predict_rejects_wrong_api_key(client, fake_model):
    resp = client.post("/predict", json={"text": "hello"}, headers={"X-API-Key": "nope"})
    assert resp.status_code == 401
    assert fake_model.calls == []


@pytest.mark.parametrize(
    "payload",
    [{}, {"txt": "wrong field"}, {"text": ""}, {"text": "   "}, {"text": 123}],
)
def test_predict_rejects_bad_payloads(client, auth, fake_model, payload):
    resp = client.post("/predict", json=payload, headers=auth)
    assert resp.status_code == 400
    assert fake_model.calls == []


def test_predict_rejects_non_json_body(client, auth, fake_model):
    resp = client.post("/predict", data="not json", headers=auth)
    assert resp.status_code == 400


def test_predict_returns_500_when_the_model_raises(client, auth):
    from app import server

    server.set_model_handler(FakeModelHandler(error=RuntimeError("model exploded")))
    resp = client.post("/predict", json={"text": "hello"}, headers=auth)
    assert resp.status_code == 500
    assert "model exploded" in resp.get_json()["error"]
    server.set_model_handler(None)
