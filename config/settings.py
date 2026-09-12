import os

from dotenv import load_dotenv

load_dotenv()


def _flag(name: str, default: str = "False") -> bool:
    return os.getenv(name, default).strip().lower() in {"1", "true", "yes", "on"}


class Config:
    # Server settings
    HOST = os.getenv("HOST", "0.0.0.0")
    PORT = int(os.getenv("PORT", 5000))
    DEBUG = _flag("DEBUG")

    # Model settings
    MODEL_NAME = os.getenv("MODEL_NAME", "distilbert-base-uncased-finetuned-sst-2-english")
    MAX_LENGTH = int(os.getenv("MAX_LENGTH", 512))

    # API settings
    API_KEY = os.getenv("API_KEY", None)

    # Rate limiting. Disabled in tests so limits do not leak between cases.
    RATELIMIT_ENABLED = _flag("RATELIMIT_ENABLED", "True")
