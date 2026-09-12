import logging
from functools import wraps

from flask import Flask, jsonify, request
from flask_cors import CORS
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

from app.model_handler import ModelHandler
from config.settings import Config

logger = logging.getLogger(__name__)

app = Flask(__name__)
CORS(app)

limiter = Limiter(
    get_remote_address,
    app=app,
    default_limits=["100 per hour"],
    enabled=Config.RATELIMIT_ENABLED,
)

# The model is loaded on first use rather than at import time. Importing
# app.server used to download a model, which made the test suite and CI
# impossible to run offline.
_model_handler: ModelHandler | None = None


def get_model_handler() -> ModelHandler:
    global _model_handler
    if _model_handler is None:
        _model_handler = ModelHandler()
    return _model_handler


def set_model_handler(handler) -> None:
    """Inject a handler. Used by tests to avoid loading a real model."""
    global _model_handler
    _model_handler = handler


def require_api_key(f):
    """Decorator to protect endpoints with an API key."""

    @wraps(f)
    def decorated_function(*args, **kwargs):
        if Config.API_KEY:
            if request.headers.get("X-API-Key") != Config.API_KEY:
                return jsonify({"error": "Invalid API key"}), 401
        return f(*args, **kwargs)

    return decorated_function


@app.route("/health", methods=["GET"])
def health_check():
    """Health check. Reports readiness without forcing a model load."""
    return jsonify(
        {
            "status": "healthy",
            "model": Config.MODEL_NAME,
            "model_loaded": _model_handler is not None and _model_handler.is_ready,
        }
    ), 200


@app.route("/predict", methods=["POST"])
@limiter.limit("10 per minute")
@require_api_key
def predict():
    """Main prediction endpoint."""
    data = request.get_json(silent=True)
    if not data or "text" not in data:
        return jsonify({"error": "Missing text field"}), 400

    text = data["text"]
    if not isinstance(text, str) or not text.strip():
        return jsonify({"error": "Field 'text' must be a non-empty string"}), 400

    try:
        result = get_model_handler().predict(text)
    except Exception as exc:
        logger.exception("Prediction endpoint error")
        return jsonify({"error": str(exc)}), 500

    return jsonify({"input": text, "prediction": result}), 200


@app.route("/models", methods=["GET"])
def list_models():
    """List available models."""
    return jsonify(
        {
            "current_model": Config.MODEL_NAME,
            "available_models": [
                "distilbert-base-uncased-finetuned-sst-2-english",
                "bert-base-uncased",
                "roberta-base",
            ],
        }
    ), 200


if __name__ == "__main__":
    logger.info("Starting server on %s:%s", Config.HOST, Config.PORT)
    app.run(host=Config.HOST, port=Config.PORT, debug=Config.DEBUG)
