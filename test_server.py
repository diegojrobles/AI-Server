import requests
import json

BASE_URL = "http://localhost:5000"
API_KEY = "your-secret-key-here"  # Match your .env file

def test_health():
    """Test health check endpoint"""
    response = requests.get(f"{BASE_URL}/health")
    print(f"Health Check: {response.status_code}")
    print(json.dumps(response.json(), indent=2))
    print()

def test_predict():
    """Test prediction endpoint"""
    headers = {"X-API-Key": API_KEY}
    data = {"text": "I love this product! It's amazing!"}
    
    response = requests.post(
        f"{BASE_URL}/predict",
        headers=headers,
        json=data
    )
    print(f"Prediction: {response.status_code}")
    print(json.dumps(response.json(), indent=2))
    print()

def test_models():
    """Test models listing endpoint"""
    response = requests.get(f"{BASE_URL}/models")
    print(f"Models: {response.status_code}")
    print(json.dumps(response.json(), indent=2))

if __name__ == "__main__":
    print("Testing AI Server...\n")
    test_health()
    test_predict()
    test_models()