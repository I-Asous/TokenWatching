"""
Shared fixtures for the backend security tests: signed Clerk-style tokens,
a test client that never calls Clerk or Supabase, and a fake database that records calls.
"""
import importlib
import inspect
import pkgutil
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
import repository  # noqa: E402  pylint: disable=wrong-import-position

EXTENSION_ORIGIN = "chrome-extension://imjnnfejbooilgjlllcnkghkckcbmgdn"
KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
OTHER_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)

# these routers verify the token in the backend (Depends(current_user));
# every other API route queries supabase as the caller and relies on RLS
VERIFIED_PREFIXES = ("/users", "/orchestrator")


def make_token(key=KEY, headers=None, drop=(), **claims):
    """Signs an RS256 token like Clerk's; `drop` removes default claims."""
    now = int(time.time())
    payload = {"sub": "user_me", "azp": EXTENSION_ORIGIN, "iat": now, "exp": now + 60, **claims}
    for claim in drop:
        payload.pop(claim)
    return jwt.encode(payload, key, algorithm="RS256", headers=headers)


def api_routes():
    """Every (method, path) in the app's API schema, with path params filled in.
    Uses the OpenAPI schema because newer FastAPI nests included routers in app.routes."""
    for path, operations in backend_main.app.openapi()["paths"].items():
        filled = re.sub(r"\{\w+\}", "1", path)
        for method in operations:
            yield method.upper(), path, filled


def data_routes():
    """API routes that query supabase as the caller (everything but "/" and the verified routers)."""
    return [(method, filled) for method, path, filled in api_routes()
            if path != "/" and not path.startswith(VERIFIED_PREFIXES)]


def bearer(token):
    return {"Authorization": f"Bearer {token}"}


class FakeSigningKey:  # pylint: disable=too-few-public-methods
    key = KEY.public_key()


class FakeUserClient:  # pylint: disable=too-few-public-methods
    """Stands in for the per-request supabase client built from the caller's token."""

    def __init__(self, token):
        self.token = token


@pytest.fixture
def user_clients(monkeypatch):
    """Tokens used to build per-request supabase clients (no real client is created)."""
    tokens = []
    if hasattr(auth, "get_user_supabase"):
        monkeypatch.setattr(auth, "get_user_supabase", lambda token: tokens.append(token) or FakeUserClient(token))
    return tokens


@pytest.fixture
def client(monkeypatch, user_clients):  # pylint: disable=unused-argument,redefined-outer-name
    # pretend Clerk's public key is ours, so no network calls are made
    monkeypatch.setattr(auth.jwks_client, "get_signing_key_from_jwt", lambda _token: FakeSigningKey())
    # crashes come back as 500 responses instead of failing the test outright
    return TestClient(backend_main.app, raise_server_exceptions=False)


class FakeDb:
    """Records every repository call as (function name, args)."""

    def __init__(self):
        self.calls = []
        self.error = None

    def recorder(self, name):
        def record(*args, **kwargs):
            self.calls.append((name, args + tuple(kwargs.values())))
            if self.error:
                raise self.error
            return []
        return record

    def fail_with(self, message):
        """Makes every repository call raise like the real ones do on a database error."""
        self.error = RuntimeError(message)


@pytest.fixture
def db(monkeypatch):
    fake = FakeDb()
    # discovered, so new repository modules are covered automatically
    for info in pkgutil.iter_modules(repository.__path__):
        if info.name == "client":
            continue
        module = importlib.import_module(f"repository.{info.name}")
        for name, fn in inspect.getmembers(module, inspect.isfunction):
            if fn.__module__ == module.__name__:
                monkeypatch.setattr(module, name, fake.recorder(name))
    return fake
