import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    # Server settings
    HOST = os.getenv('HOST', '0.0.0.0')
    PORT = int(os.getenv('PORT', 5000))
    DEBUG = os.getenv('DEBUG', 'False').lower() == 'true'
    
    # Model settings
    MODEL_NAME = os.getenv('MODEL_NAME', 'distilbert-base-uncased-finetuned-sst-2-english')
    MAX_LENGTH = int(os.getenv('MAX_LENGTH', 512))
    
    # API settings
    API_KEY = os.getenv('API_KEY', None)