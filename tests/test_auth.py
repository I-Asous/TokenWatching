"""
Tests for Clerk token verification (backend/auth.py) - every API route needs a
token, and the routes the backend verifies itself (/users, /orchestrator) reject
every kind of bad token before the database is touched.
"""
import base64
import hashlib
import hmac
import json
import time

import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from jwt.exceptions import PyJWKClientConnectionError

import auth
from conftest import EXTENSION_ORIGIN, KEY, OTHER_KEY, api_routes, bearer, make_token

# pylint: disable=redefined-outer-name,unused-argument  # pytest fixtures

# a backend-verified route that is cheap to call: the repository is faked by `db`
VERIFIED = ("DELETE", "/users")


def b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def tampered_token():
    # keep the real signature but swap the payload to another user
    header, _payload, signature = make_token().split(".")
    payload = b64(json.dumps({"sub": "user_other", "exp": int(time.time()) + 60}).encode())
    return f"{header}.{payload}.{signature}"


def hs256_key_confusion_token():
    # classic attack: sign with HS256 using the server's RSA *public* key as the secret
    public_pem = KEY.public_key().public_bytes(
        serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo)
    header = b64(json.dumps({"alg": "HS256", "typ": "JWT"}).encode())
    payload = b64(json.dumps({"sub": "user_me", "exp": int(time.time()) + 60}).encode())
    signature = hmac.new(public_pem, f"{header}.{payload}".encode(), hashlib.sha256).digest()
    return f"{header}.{payload}.{b64(signature)}"


def unsigned_token():
    return jwt.encode({"sub": "user_me", "exp": int(time.time()) + 60}, None, algorithm="none")


def call_verified(client, token=None, headers=None):
    method, path = VERIFIED
    return client.request(method, path, headers=headers if headers is not None else bearer(token))


def test_health_check_is_public(client):
    assert client.get("/").status_code == 200


def test_api_routes_were_found():
    # guard so the parametrized test below can't silently test nothing
    assert len(list(api_routes())) >= 12


@pytest.mark.parametrize("method,path", [(m, f) for m, p, f in api_routes() if p != "/"])
def test_every_api_route_requires_a_token(client, db, user_clients, method, path):
    assert client.request(method, path).status_code == 401
    assert not db.calls
    assert not user_clients


@pytest.mark.parametrize("headers", [
    {},
    {"Authorization": "Basic abc"},
    {"Authorization": "Bearer"},
    {"Authorization": "Bearer "},
])
def test_missing_or_malformed_header_rejected(client, db, headers):
    assert call_verified(client, headers=headers).status_code == 401
    assert not db.calls


@pytest.mark.parametrize("token", [
    pytest.param("not-a-jwt", id="garbage"),
    pytest.param(make_token(exp=int(time.time()) - 10), id="expired"),
    pytest.param(make_token(nbf=int(time.time()) + 60), id="nbf-in-future"),
    pytest.param(make_token(iat=int(time.time()) + 60), id="iat-in-future"),
    pytest.param(make_token(key=OTHER_KEY), id="wrong-key"),
    pytest.param(tampered_token(), id="tampered-payload"),
    pytest.param(unsigned_token(), id="alg-none"),
    pytest.param(hs256_key_confusion_token(), id="hs256-key-confusion"),
])
def test_bad_token_rejected_without_leaking_details(client, db, token):
    response = call_verified(client, token)
    assert response.status_code == 401
    assert response.json() == {"detail": "Invalid or expired token"}
    assert not db.calls


def test_unreachable_key_server_is_401_not_500(client, db, monkeypatch):
    def unreachable(_token):
        raise PyJWKClientConnectionError("Clerk is down")
    monkeypatch.setattr(auth.jwks_client, "get_signing_key_from_jwt", unreachable)
    assert call_verified(client, make_token()).status_code == 401
    assert not db.calls


def test_token_for_another_origin_rejected(client, db):
    response = call_verified(client, make_token(azp="https://evil.example.com"))
    assert response.status_code == 401
    assert response.json() == {"detail": "Invalid token origin"}
    assert not db.calls


@pytest.mark.parametrize("token", [
    pytest.param(make_token(azp=EXTENSION_ORIGIN), id="azp-extension"),
    pytest.param(make_token(drop=("azp",)), id="azp-missing"),
])
def test_valid_token_accepted_with_token_identity(client, db, token):
    # the user being acted on comes from the token, never from the request
    assert call_verified(client, token).status_code == 200
    assert db.calls == [("delete_user", ("user_me",))]


def test_orchestrator_rejects_bad_token(client, db, monkeypatch):
    # the pipeline costs API credits, so a bad token must stop it before it runs
    import routes.orchestrator  # pylint: disable=import-outside-toplevel
    def must_not_run(**_kwargs):
        raise AssertionError("pipeline ran with a bad token")
    monkeypatch.setattr(routes.orchestrator, "RunOrchestrator", must_not_run, raising=False)
    response = client.post("/orchestrator", json={"prompt": "hi", "target": "chatgpt"},
                           headers=bearer(make_token(exp=int(time.time()) - 10)))
    assert response.status_code == 401
    assert not db.calls


# --- known holes: these assert the secure behaviour and fail until auth.py is fixed ---
# strict xfail keeps CI green while documenting them; once a hole is fixed the test
# "unexpectedly passes" and fails CI, as a reminder to delete its xfail marker

@pytest.mark.xfail(strict=True, reason="known hole: jwt.decode doesn't require exp")
def test_token_without_expiry_rejected(client, db):
    # PyJWT only checks exp when it is present, so a token without one never expires
    assert call_verified(client, make_token(drop=("exp",))).status_code == 401
    assert not db.calls


@pytest.mark.xfail(strict=True, reason="known hole: a token without sub crashes with KeyError (500)")
def test_token_without_subject_rejected(client, db):
    # payload["sub"] raises KeyError, which surfaces as a 500
    assert call_verified(client, make_token(drop=("sub",))).status_code == 401
    assert not db.calls
