"""Pydantic models for the HTTP contract.

These are the request and response shapes the FastAPI port (ROADMAP items
12-14) serves. They are defined ahead of the port, and deliberately mirror the
JSON the Flask app emits today, so that swapping the framework underneath does
not change a single byte on the wire for existing clients.

Two decisions worth stating, because both are visible to callers:

* Requests set ``extra="forbid"``. The Flask handlers silently ignored unknown
  keys, so a client that sent ``{"txt": ...}`` got a confusing "Missing text
  field" instead of being told about the typo. Rejecting unknown fields turns
  a silent contract drift into a 422 that names the offending key.
* Responses do not forbid extras, because adding a field to a response is a
  backwards-compatible change and should not require a schema revision.

``HealthResponse`` carries ``model`` and ``model_loaded`` fields. Under
Pydantic 2.13 the protected namespaces are ``("model_validate", "model_dump")``
rather than the bare ``model_`` prefix of earlier versions, so neither field
collides and no config override is needed. That is a property of the pinned
version, not a guarantee, which is why ``test_schemas`` asserts the module
imports warning-free instead of leaving it to chance.
"""

from pydantic import BaseModel, ConfigDict, Field, field_validator

__all__ = [
    "ErrorResponse",
    "HealthResponse",
    "Prediction",
    "PredictRequest",
    "PredictResponse",
]


class PredictRequest(BaseModel):
    """Body of ``POST /predict``."""

    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={"examples": [{"text": "This gateway is a joy to operate."}]},
    )

    text: str = Field(
        ...,
        min_length=1,
        description="Text to run sentiment inference over. Must not be blank.",
    )

    @field_validator("text")
    @classmethod
    def _reject_blank(cls, value: str) -> str:
        """Reject whitespace-only input without altering what was sent.

        The value is intentionally returned unmodified rather than stripped:
        ``PredictResponse.input`` echoes the caller's text back verbatim, and
        quietly trimming it would make the echo a lie.
        """
        if not value.strip():
            raise ValueError("must not be blank")
        return value


class Prediction(BaseModel):
    """A single label/score pair as returned by the transformers pipeline."""

    model_config = ConfigDict(
        json_schema_extra={"examples": [{"label": "POSITIVE", "score": 0.9998}]},
    )

    label: str = Field(..., description="Predicted class label, e.g. POSITIVE.")
    score: float = Field(..., ge=0.0, le=1.0, description="Confidence in [0, 1].")


class PredictResponse(BaseModel):
    """Body of a successful ``POST /predict``."""

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "input": "This gateway is a joy to operate.",
                    "prediction": [{"label": "POSITIVE", "score": 0.9998}],
                }
            ]
        },
    )

    input: str = Field(..., description="The text exactly as the caller sent it.")
    prediction: list[Prediction] = Field(
        ...,
        description="Pipeline output. A list because the pipeline is batch-shaped.",
    )


class ErrorResponse(BaseModel):
    """Uniform error envelope.

    Kept to the single ``error`` key the Flask handlers already return. Item 16
    extends this with a request ID once the exception handlers exist; until
    then, widening it would break clients for no benefit.
    """

    model_config = ConfigDict(
        json_schema_extra={"examples": [{"error": "Invalid API key"}]},
    )

    error: str = Field(..., description="Human-readable description of what went wrong.")


class HealthResponse(BaseModel):
    """Body of ``GET /health``."""

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "status": "healthy",
                    "model": "distilbert-base-uncased-finetuned-sst-2-english",
                    "model_loaded": False,
                }
            ]
        },
    )

    status: str = Field(..., description="Liveness indicator.")
    model: str = Field(..., description="Configured model name.")
    model_loaded: bool = Field(
        ...,
        description="Whether the model is actually resident and ready to serve.",
    )
