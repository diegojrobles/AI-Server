import os

# Must be set before config.settings is imported, since Config reads the
# environment at class-definition time.
os.environ.setdefault("API_KEY", "test-key")
os.environ.setdefault("RATELIMIT_ENABLED", "False")
os.environ.setdefault("DEBUG", "False")

import pytest  # noqa: E402

from app import server  # noqa: E402


class FakeModelHandler:
    """Stand-in for ModelHandler. Deterministic, offline, no torch."""

    def __init__(self, result=None, error: Exception | None = None):
        self._result = result if result is not None else [{"label": "POSITIVE", "score": 0.99}]
        self._error = error
        self.calls: list[str] = []

    @property
    def is_ready(self) -> bool:
        return True

    def predict(self, text: str):
        self.calls.append(text)
        if self._error:
            raise self._error
        return self._result


@pytest.fixture
def fake_model():
    handler = FakeModelHandler()
    server.set_model_handler(handler)
    yield handler
    server.set_model_handler(None)


@pytest.fixture
def client():
    server.app.config.update(TESTING=True)
    with server.app.test_client() as c:
        yield c


@pytest.fixture
def auth():
    return {"X-API-Key": os.environ["API_KEY"]}
