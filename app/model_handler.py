from transformers import pipeline
from config.settings import Config
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class ModelHandler:
    """Handles AI model loading and inference"""
    
    def __init__(self):
        self.model = None
        self.load_model()
    
    def load_model(self):
        """Load the AI model into memory"""
        try:
            logger.info(f"Loading model: {Config.MODEL_NAME}")
            self.model = pipeline(
                "sentiment-analysis",
                model=Config.MODEL_NAME
            )
            logger.info("Model loaded successfully")
        except Exception as e:
            logger.error(f"Failed to load model: {str(e)}")
            raise
    
    def predict(self, text):
        """Run inference on input text"""
        if not self.model:
            raise RuntimeError("Model not loaded")
        
        try:
            result = self.model(text, max_length=Config.MAX_LENGTH, truncation=True)
            return result
        except Exception as e:
            logger.error(f"Prediction error: {str(e)}")
            raise