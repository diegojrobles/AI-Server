"""Tests for the HTTP contract models (ROADMAP item 10).

The point of these is not that Pydantic works -- it does -- but that the
schemas encode the contract the Flask app serves today, so the FastAPI port in
items 12-14 is provably a framework swap and not a behaviour change.
"""

import importlib
import warnings

import pytest
from pydantic import ValidationError

import app.schemas
from app.schemas import (
    ErrorResponse,
    HealthResponse,
    Prediction,
    PredictRequest,
    PredictResponse,
)


class TestPredictRequest:
    def test_accepts_ordinary_text(self):
        assert PredictRequest(text="hello").text == "hello"

    @pytest.mark.parametrize("blank", ["", " ", "\t", "\n", "   \n\t  "])
    def test_rejects_blank_text(self, blank):
        with pytest.raises(ValidationError):
            PredictRequest(text=blank)

    def test_preserves_surrounding_whitespace(self):
        """Validation must not mutate the value; the response echoes it back."""
        assert PredictRequest(text="  padded  ").text == "  padded  "

    def test_rejects_missing_text(self):
        with pytest.raises(ValidationError) as exc:
            PredictRequest()
        assert "text" in str(exc.value)

    def test_rejects_non_string_text(self):
        with pytest.raises(ValidationError):
            PredictRequest(text=123)

    def test_rejects_unknown_fields(self):
        """A typo'd key is a client bug and should be named, not ignored."""
        with pytest.raises(ValidationError) as exc:
            PredictRequest(text="hello", txt="hello")
        assert "txt" in str(exc.value)


class TestPrediction:
    def test_round_trips_pipeline_output(self):
        p = Prediction(label="POSITIVE", score=0.9998)
        assert p.model_dump() == {"label": "POSITIVE", "score": 0.9998}

    @pytest.mark.parametrize("bad_score", [-0.01, 1.01, 2.0])
    def test_rejects_out_of_range_score(self, bad_score):
        with pytest.raises(ValidationError):
            Prediction(label="POSITIVE", score=bad_score)

    @pytest.mark.parametrize("edge", [0.0, 1.0])
    def test_accepts_inclusive_bounds(self, edge):
        assert Prediction(label="NEGATIVE", score=edge).score == edge


class TestPredictResponse:
    def test_matches_current_flask_wire_shape(self):
        """The exact JSON app.server.predict returns today."""
        resp = PredictResponse(
            input="great service",
            prediction=[{"label": "POSITIVE", "score": 0.99}],
        )
        assert resp.model_dump() == {
            "input": "great service",
            "prediction": [{"label": "POSITIVE", "score": 0.99}],
        }

    def test_accepts_multiple_predictions(self):
        resp = PredictResponse(
            input="x",
            prediction=[
                {"label": "POSITIVE", "score": 0.6},
                {"label": "NEGATIVE", "score": 0.4},
            ],
        )
        assert len(resp.prediction) == 2

    def test_accepts_empty_prediction_list(self):
        assert PredictResponse(input="x", prediction=[]).prediction == []

    def test_rejects_malformed_prediction_entry(self):
        with pytest.raises(ValidationError):
            PredictResponse(input="x", prediction=[{"label": "POSITIVE"}])


class TestErrorResponse:
    def test_matches_current_flask_wire_shape(self):
        assert ErrorResponse(error="Missing text field").model_dump() == {
            "error": "Missing text field"
        }

    def test_requires_error_field(self):
        with pytest.raises(ValidationError):
            ErrorResponse()


class TestHealthResponse:
    def test_matches_current_flask_wire_shape(self):
        resp = HealthResponse(
            status="healthy",
            model="distilbert-base-uncased-finetuned-sst-2-english",
            model_loaded=False,
        )
        assert resp.model_dump() == {
            "status": "healthy",
            "model": "distilbert-base-uncased-finetuned-sst-2-english",
            "model_loaded": False,
        }

    def test_exposes_model_prefixed_fields(self):
        """`model` and `model_loaded` are part of the published API."""
        assert set(HealthResponse.model_fields) == {"status", "model", "model_loaded"}


class TestOpenAPISchema:
    """Item 24 generates docs from these; they are useless without examples."""

    @pytest.mark.parametrize(
        "model",
        [PredictRequest, Prediction, PredictResponse, ErrorResponse, HealthResponse],
    )
    def test_every_model_publishes_an_example(self, model):
        assert model.model_json_schema().get("examples")

    def test_request_schema_marks_text_required(self):
        assert PredictRequest.model_json_schema()["required"] == ["text"]


def test_module_imports_without_pydantic_warnings():
    """Guard against a future field name colliding with a protected namespace.

    Pydantic emits a UserWarning at class-definition time when a field shadows
    one of its reserved names (currently ``model_validate`` / ``model_dump``).
    Reloading the module with warnings promoted to errors means a field added
    later as, say, ``model_dump_url`` fails here rather than silently shadowing
    a BaseModel method at runtime.
    """
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        importlib.reload(app.schemas)
