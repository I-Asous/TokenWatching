"""
Tests for the backend's CORS configuration (backend/main.py) - confirming only
the trusted Chrome extension origin is granted cross-origin access.
"""
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

BACKEND_DIR = Path(__file__).resolve().parent.parent / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import main as backend_main  # noqa: E402

EXTENSION_ORIGIN = "chrome-extension://imjnnfejbooilgjlllcnkghkckcbmgdn"


@pytest.fixture
def client():
    return TestClient(backend_main.app)


#Should be allowed
def test_cors_allows_extension_origin(client):
    response = client.get("/", headers={"Origin": EXTENSION_ORIGIN})
    assert response.headers["access-control-allow-origin"] == EXTENSION_ORIGIN


#Evil.example.com, should get rejected
def test_cors_rejects_unknown_origin(client):
    response = client.get("/", headers={"Origin": "https://evil.example.com"})
    assert "access-control-allow-origin" not in response.headers
