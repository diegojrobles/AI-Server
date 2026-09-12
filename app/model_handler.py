import logging

from config.settings import Config

logger = logging.getLogger(__name__)


class ModelHandler:
    """Handles AI model loading and inference.

    The heavy ``transformers`` import is deferred to :meth:`load_model` so that
    importing this module does not pull in torch. Tests substitute a fake
    handler and never touch the real stack.
    """

    def __init__(self, load: bool = True):
        self.model = None
        if load:
            self.load_model()

    def load_model(self):
        """Load the AI model into memory."""
        from transformers import pipeline  # deferred: keeps import cost off the web path

        try:
            logger.info("Loading model: %s", Config.MODEL_NAME)
            self.model = pipeline("sentiment-analysis", model=Config.MODEL_NAME)
            logger.info("Model loaded successfully")
        except Exception:
            logger.exception("Failed to load model")
            raise

    @property
    def is_ready(self) -> bool:
        return self.model is not None

    def predict(self, text: str):
        """Run inference on input text."""
        if not self.model:
            raise RuntimeError("Model not loaded")

        try:
            return self.model(text, max_length=Config.MAX_LENGTH, truncation=True)
        except Exception:
            logger.exception("Prediction error")
            raise
