"""
Shared fixtures for the backend security tests: signed Clerk-style tokens,
a test client that never calls Clerk, and a fake database that records calls.
"""
import inspect
import re
import sys
import time
from pathlib import Path

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient

BACKEND_DIR = Path(__file__).resolve().parent.parent / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import auth  # noqa: E402  pylint: disable=wrong-import-position
import main as backend_main  # noqa: E402  pylint: disable=wrong-import-position
from repository import optimized_prompts, prompt_w_optimized, prompts, users  # noqa: E402  pylint: disable=wrong-import-position

EXTENSION_ORIGIN = "chrome-extension://imjnnfejbooilgjlllcnkghkckcbmgdn"
KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
OTHER_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)


def make_token(key=KEY, headers=None, drop=(), **claims):
    """Signs an RS256 token like Clerk's; `drop` removes default claims."""
    now = int(time.time())
    payload = {"sub": "user_me", "azp": EXTENSION_ORIGIN, "iat": now, "exp": now + 60, **claims}
    for claim in drop:
        payload.pop(claim)
    return jwt.encode(payload, key, algorithm="RS256", headers=headers)


def api_routes(user_id="user_me"):
    """Every (method, path) in the app's API schema, with path params filled in.
    Uses the OpenAPI schema because newer FastAPI nests included routers in app.routes."""
    for path, operations in backend_main.app.openapi()["paths"].items():
        filled = re.sub(r"\{(\w+)\}", lambda m: user_id if m.group(1) == "user_id" else "1", path)
        for method in operations:
            yield method.upper(), path, filled


def bearer(token):
    return {"Authorization": f"Bearer {token}"}


class FakeSigningKey:  # pylint: disable=too-few-public-methods
    key = KEY.public_key()


@pytest.fixture
def client(monkeypatch):
    # pretend Clerk's public key is ours, so no network calls are made
    monkeypatch.setattr(auth.jwks_client, "get_signing_key_from_jwt", lambda _token: FakeSigningKey())
    # crashes come back as 500 responses instead of failing the test outright
    return TestClient(backend_main.app, raise_server_exceptions=False)


class FakeDb:  # pylint: disable=too-few-public-methods
    """Records every repository call as (function name, args)."""

    def __init__(self):
        self.calls = []

    def recorder(self, name):
        def record(*args, **kwargs):
            self.calls.append((name, args + tuple(kwargs.values())))
            return []
        return record


@pytest.fixture
def db(monkeypatch):
    fake = FakeDb()
    for module in (prompts, optimized_prompts, prompt_w_optimized, users):
        for name, fn in inspect.getmembers(module, inspect.isfunction):
            if fn.__module__ == module.__name__:
                monkeypatch.setattr(module, name, fake.recorder(name))
    return fake
