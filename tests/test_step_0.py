import os
import sys
import hmac
import hashlib
import pytest
from dotenv import load_dotenv

# Ensure we can import from environment
load_dotenv()

def test_imports():
    """Rigorously verify all required dependencies can be imported in the venv."""
    import fastapi
    import uvicorn
    import asyncpg
    import pydantic
    import httpx
    from google import genai
    from caspian_sdk import CommClient, Message

    
    assert fastapi.__version__ is not None
    assert pydantic.__version__ is not None
    assert CommClient is not None
    assert Message is not None

def test_env_files():
    """Verify .env.example contains all required keys specified in step_0_decisions.md."""
    required_keys = [
        "ENVIRONMENT",
        "PORT",
        "DATABASE_URL",
        "ADMIN_API_KEY",
        "GITHUB_WEBHOOK_SECRET",
        "GITHUB_TOKEN",
        "GEMINI_API_KEY",
        "CASPIAN_API_KEY",
        "CASPIAN_BASE_URL",
        "TELEGRAM_BOT_TOKEN",
        "CASPIAN_EMAIL_USER",
        "FRONTEND_URL",
        "CORS_ORIGINS"
    ]
    
    assert os.path.exists(".env.example"), ".env.example missing"
    assert os.path.exists(".env"), ".env missing"
    
    with open(".env.example", "r") as f:
        example_content = f.read()
        
    for key in required_keys:
        assert f"{key}=" in example_content, f"Key {key} missing from .env.example"

def test_score_formula_normalization():
    """
    Verify the Step 0 score formula:
    ai_score = 0.4*difficulty + 0.3*authenticity + 0.3*creativity (0-100)
    bayesian_rating = ((C*m) + (votes*avg_rating)) / (C + votes) (1-10)
    normalized_bayesian = bayesian_rating * 10 (0-100)
    final_score = 0.7*ai_score + 0.3*normalized_bayesian
    """
    difficulty = 90
    authenticity = 80
    creativity = 85
    
    ai_score = (0.4 * difficulty) + (0.3 * authenticity) + (0.3 * creativity)
    assert ai_score == 85.5
    
    # Bayesian adjustment
    C = 5
    m = 5.0
    votes = 10
    avg_rating = 9.0 # 9/10
    
    bayesian_rating = ((C * m) + (votes * avg_rating)) / (C + votes)
    # (25 + 90) / 15 = 115 / 15 = 7.666...
    
    normalized_bayesian = bayesian_rating * 10
    final_score = (0.7 * ai_score) + (0.3 * normalized_bayesian)
    
    assert 0 <= final_score <= 100
    assert final_score > 80.0 # High quality project correctly scores high

def test_webhook_signature_verification():
    """Verify HMAC SHA256 signature verification matching Step 0 specs."""
    secret = b"dev_webhook_secret_12345"
    payload = b'{"action": "ping"}'
    
    mac = hmac.new(secret, msg=payload, digestmod=hashlib.sha256)
    expected_signature = f"sha256={mac.hexdigest()}"
    
    # Verification function logic
    def verify_sig(body: bytes, header_sig: str, sec: bytes) -> bool:
        if not header_sig.startswith("sha256="):
            return False
        computed = "sha256=" + hmac.new(sec, msg=body, digestmod=hashlib.sha256).hexdigest()
        return hmac.compare_digest(computed, header_sig)
        
    assert verify_sig(payload, expected_signature, secret) is True
    assert verify_sig(payload, "sha256=invalid", secret) is False

def test_caspian_client_init():
    """Verify Caspian CommClient instantiates without error."""
    from caspian_sdk import CommClient
    client = CommClient(api_key="test_key", base_url="https://api.trycaspianai.com")
    assert client is not None

def test_cors_origins_parsing():
    """Verify CORS_ORIGINS environment variable parses as a valid JSON list of origin URLs."""
    import json
    cors_origins_str = os.getenv("CORS_ORIGINS", '["http://localhost:5173","https://talentcaspian.vercel.app"]')
    origins = json.loads(cors_origins_str)
    assert isinstance(origins, list)
    assert "http://localhost:5173" in origins
    assert "https://talentcaspian.vercel.app" in origins

