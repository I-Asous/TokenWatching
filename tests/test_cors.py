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


def preflight(client, origin, method="POST", headers="authorization, content-type"):
    return client.options("/prompts/prompt", headers={
        "Origin": origin,
        "Access-Control-Request-Method": method,
        "Access-Control-Request-Headers": headers,
    })


#Browser preflight from the extension is allowed, including the Authorization header
def test_preflight_allows_extension(client):
    response = preflight(client, EXTENSION_ORIGIN)
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == EXTENSION_ORIGIN
    assert "authorization" in response.headers["access-control-allow-headers"].lower()


#Preflight from an unknown site is refused
def test_preflight_rejects_unknown_origin(client):
    response = preflight(client, "https://evil.example.com")
    assert response.status_code == 400
    assert "access-control-allow-origin" not in response.headers


#Even the extension can't use headers or methods we didn't allow
@pytest.mark.parametrize("method,headers", [("POST", "x-evil"), ("TRACE", "authorization")])
def test_preflight_rejects_unlisted_header_or_method(client, method, headers):
    assert preflight(client, EXTENSION_ORIGIN, method, headers).status_code == 400


#Cookies are never shared cross-origin, and the origin is never a wildcard
def test_no_credentials_and_no_wildcard(client):
    for response in (client.get("/", headers={"Origin": EXTENSION_ORIGIN}), preflight(client, EXTENSION_ORIGIN)):
        assert "access-control-allow-credentials" not in response.headers
        assert response.headers["access-control-allow-origin"] != "*"


#Origins that look close to ours must not match
@pytest.mark.parametrize("origin", [
    "null",
    "http://localhost",
    "chrome-extension://aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
    EXTENSION_ORIGIN + "x",
    "https://chrome-extension.evil.com",
])
def test_cors_rejects_lookalike_origins(client, origin):
    response = client.get("/", headers={"Origin": origin})
    assert "access-control-allow-origin" not in response.headers


#A 401 still carries CORS headers, so the extension can read the error
def test_cors_headers_on_unauthorized_response(client):
    response = client.get("/prompts/users/x/prompts", headers={"Origin": EXTENSION_ORIGIN})
    assert response.status_code == 401
    assert response.headers["access-control-allow-origin"] == EXTENSION_ORIGIN


#Extra origins from CORS_ALLOWED_ORIGINS are trimmed and blanks ignored
def test_extra_origins_parsed_from_env(monkeypatch):
    import importlib  # pylint: disable=import-outside-toplevel
    import auth  # pylint: disable=import-outside-toplevel
    monkeypatch.setenv("CORS_ALLOWED_ORIGINS", " https://a.com, ,https://b.com ")
    try:
        importlib.reload(auth)
        assert auth.ALLOWED_ORIGINS == [EXTENSION_ORIGIN, "https://a.com", "https://b.com"]
    finally:
        monkeypatch.undo()
        importlib.reload(auth)
