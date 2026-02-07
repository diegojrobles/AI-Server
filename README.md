# AI Server

A production-ready REST API server for running AI models.

## Features
- Sentiment analysis using transformers
- RESTful API with Flask
- API key authentication
- Environment-based configuration
- Easy model swapping

## Setup

1. Clone the repository:
```bash
   git clone https://github.com/YOUR-USERNAME/ai-server.git
   cd ai-server
```

2. Create virtual environment:
```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
```

3. Install dependencies:
```bash
   pip install -r requirements.txt
```

4. Create `.env` file:

HOST=0.0.0.0
PORT=5000
DEBUG=True
MODEL_NAME=distilbert-base-uncased-finetuned-sst-2-english
API_KEY=your-secret-key-here

5. Run the server:
```bash
   python run.py
```

## API Endpoints

### Health Check
```bash
GET /health
```

### Predict
```bash
POST /predict
Headers: X-API-Key: your-secret-key-here
Body: {"text": "Your text here"}
```

### List Models
```bash
GET /models
```

## Testing
```bash
python test_server.py
```

## License
MIT