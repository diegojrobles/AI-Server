"""Typed, validated application configuration (ROADMAP item 11).

What this replaces: a plain ``class Config`` whose attributes were
``os.getenv`` calls evaluated at class-definition time, with ``int()`` casts
and a hand-rolled ``_flag`` helper for booleans. That worked, but it had three
properties worth losing before the FastAPI port in items 12-17 starts reading
config from more places:

* **Nothing was typed.** ``Config.PORT`` was an ``int`` only because someone
  remembered to wrap it; a new field added without the cast would silently be
  a string, and the failure would surface somewhere unrelated.
* **Nothing was validated.** ``PORT=0`` or ``PORT=99999`` was accepted and the
  bind failed later with an OS error. ``MAX_LENGTH=-5`` reached the tokenizer.
* **Bad booleans failed silently.** ``_flag`` treated anything outside its
  allow-list as false, so ``RATELIMIT_ENABLED=ture`` quietly disabled rate
  limiting in production. Pydantic rejects it at startup instead.

Precedence is unchanged: real environment variables win over ``.env``, which
wins over the defaults here. Field names are lower-case and matched
case-insensitively, so the existing ``HOST``/``PORT``/``MODEL_NAME`` names in
``.env.example`` keep working untouched.

``Settings`` is frozen. Configuration is read once at startup and treated as
immutable for the life of the process; item 53 ("config reload without
restart") is then a matter of building a *new* instance and swapping it in,
which is far easier to reason about than letting any caller mutate shared
state. Unknown environment variables are ignored rather than rejected, because
the process environment belongs to the host (``PATH``, ``PYTHONPATH``, CI
injections) and is not ours to police.

One field name deserves a note: ``model_name`` sits near Pydantic's protected
namespaces. Under the pinned 2.13.5 those are ``("model_validate",
"model_dump")`` rather than the bare ``model_`` prefix of earlier releases, so
there is no collision and no override is needed. That is a property of the pin,
not a promise, so ``tests/test_settings.py`` imports the module with warnings
promoted to errors rather than trusting it.
"""

import warnings

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

__all__ = ["Settings", "settings"]


class Settings(BaseSettings):
    """Process configuration, read from the environment and ``.env``."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
        frozen=True,
    )

    # --- Server ---
    host: str = Field(
        default="0.0.0.0",
        description="Interface to bind. 0.0.0.0 serves on every interface.",
    )
    port: int = Field(
        default=5000,
        ge=1,
        le=65535,
        description="TCP port to bind. Bounded to the valid port range.",
    )
    debug: bool = Field(
        default=False,
        description="Enable framework debug mode. Never true in production.",
    )

    # --- Model ---
    model_name: str = Field(
        default="distilbert-base-uncased-finetuned-sst-2-english",
        description="Hugging Face model identifier for the sentiment pipeline.",
    )
    max_length: int = Field(
        default=512,
        ge=1,
        description=(
            "Token limit passed to the pipeline alongside truncation=True. "
            "Deliberately has no upper bound here: the real ceiling is the "
            "tokenizer's model_max_length, which varies per model and is "
            "enforced by transformers, so inventing a number would be a "
            "second source of truth that could disagree with the first."
        ),
    )

    # --- API ---
    api_key: str | None = Field(
        default=None,
        description="Required in the X-API-Key header. Unset disables auth.",
    )

    # --- Rate limiting ---
    ratelimit_enabled: bool = Field(
        default=True,
        description="Disabled in tests so limits do not leak between cases.",
    )

    @field_validator("host", "model_name", mode="after")
    @classmethod
    def _require_non_blank(cls, value: str) -> str:
        """Reject blank values and trim surrounding whitespace.

        Unlike ``PredictRequest.text``, these are never echoed back to a
        caller, so trimming is safe -- and a trailing newline from a shell
        heredoc in a ``.env`` file is always a mistake, not intent.
        """
        trimmed = value.strip()
        if not trimmed:
            raise ValueError("must not be blank")
        return trimmed

    @field_validator("api_key", mode="before")
    @classmethod
    def _blank_api_key_means_unset(cls, value: object) -> object:
        """Treat ``API_KEY=`` as absent rather than as a one-character secret.

        ``.env`` files routinely carry a key with its value deleted. The old
        code happened to behave this way by accident, since the empty string is
        falsy and the guard was ``if Config.API_KEY``. Making it explicit means
        the auth dependency in item 15 can test ``is None`` and be right.
        """
        if isinstance(value, str) and not value.strip():
            return None
        return value.strip() if isinstance(value, str) else value

    @model_validator(mode="after")
    def _warn_on_public_debug(self) -> "Settings":
        """Warn when debug mode is paired with a publicly reachable bind.

        A warning rather than an error on purpose: ``HOST`` defaults to
        ``0.0.0.0`` (what the container needs), so raising here would make
        ``DEBUG=True`` unusable for local development, which is exactly when it
        is wanted. But the combination exposes the Werkzeug console -- remote
        code execution to anyone who can reach the port -- so it should never
        happen silently.
        """
        if self.debug and self.host in {"0.0.0.0", "::"}:
            warnings.warn(
                f"DEBUG is enabled while bound to {self.host}, which exposes the "
                "interactive debugger to every reachable network. Bind 127.0.0.1 "
                "instead, or disable DEBUG.",
                UserWarning,
                stacklevel=2,
            )
        return self


settings = Settings()
