from flask import Flask, request, jsonify
from flask_cors import CORS
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from app.model_handler import ModelHandler
from config.settings import Config
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
CORS(app)  # Enable cross-origin requests

# Initialize rate limiter
limiter = Limiter(
    app=app,
    key_func=get_remote_address,
    default_limits=["100 per hour"]
)

# Initialize model
model_handler = ModelHandler()

def require_api_key(f):
    """Decorator to protect endpoints with API key"""
    def decorated_function(*args, **kwargs):
        if Config.API_KEY:
            api_key = request.headers.get('X-API-Key')
            if api_key != Config.API_KEY:
                return jsonify({'error': 'Invalid API key'}), 401
        return f(*args, **kwargs)
    decorated_function.__name__ = f.__name__
    return decorated_function

@app.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    return jsonify({
        'status': 'healthy',
        'model': Config.MODEL_NAME
    }), 200

@app.route('/predict', methods=['POST'])
@limiter.limit("10 per minute")
@require_api_key
def predict():
    """Main prediction endpoint"""
    try:
        # Validate request
        data = request.get_json()
        if not data or 'text' not in data:
            return jsonify({'error': 'Missing text field'}), 400
        
        text = data['text']
        
        # Run prediction
        result = model_handler.predict(text)
        
        return jsonify({
            'input': text,
            'prediction': result
        }), 200
        
    except Exception as e:
        logger.error(f"Prediction endpoint error: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/models', methods=['GET'])
def list_models():
    """List available models"""
    return jsonify({
        'current_model': Config.MODEL_NAME,
        'available_models': [
            'distilbert-base-uncased-finetuned-sst-2-english',
            'bert-base-uncased',
            'roberta-base'
        ]
    }), 200

if __name__ == '__main__':
    logger.info(f"Starting server on {Config.HOST}:{Config.PORT}")
    app.run(
        host=Config.HOST,
        port=Config.PORT,
        debug=Config.DEBUG
    )