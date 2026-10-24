"""
Tests that a logged-in user can only reach their own data. Data routes query
supabase *as the caller* (a client built from their Clerk token), so supabase RLS
decides which rows they see - these tests check the backend wires that up correctly.
"""
import time

import pytest

from conftest import bearer, data_routes, make_token

# pylint: disable=redefined-outer-name,unused-argument  # pytest fixtures

RLS_DENIED = "Database error: {'code': '42501', 'message': 'new row violates row-level security policy'}"


def test_data_routes_were_found():
    # guard so the parametrized tests below can't silently test nothing
    assert len(data_routes()) >= 10


@pytest.mark.parametrize("method,path", data_routes())
def test_data_routes_query_as_the_caller(client, db, user_clients, method, path):
    # each request gets a supabase client built from *this* caller's token, so RLS
    # applies to them - never the secret-key client that bypasses RLS
    token = make_token()
    client.request(method, path, headers=bearer(token))
    assert user_clients == [token]


@pytest.mark.parametrize("path,body", [
    ("/prompts", {"txt_prompt": "hi", "target": "chatgpt"}),
    ("/optimized-prompts", {"txt_prompt": "hi", "tokens": 1, "tokens_saved": 0, "percent_saved": 0}),
])
def test_request_body_cannot_choose_the_user(client, db, path, body):
    # a user_id sent by the client is dropped; the database fills it from the token
    client.post(path, json={**body, "user_id": "user_other"}, headers=bearer(make_token()))
    assert db.calls, "the insert was never attempted"
    saved = db.calls[0][1][-1]
    assert "user_id" not in saved.model_dump()


@pytest.mark.parametrize("path,body", [
    ("/prompts", {"txt_prompt": "hi", "target": "chatgpt"}),
    ("/optimized-prompts", {"txt_prompt": "hi", "tokens": 1, "tokens_saved": 0, "percent_saved": 0}),
])
def test_rls_rejection_is_403(client, db, path, body):
    db.fail_with(RLS_DENIED)
    response = client.post(path, json=body, headers=bearer(make_token()))
    assert response.status_code == 403
    assert response.json() == {"detail": "Not your data"}


# --- known holes: these assert the secure behaviour and fail until the backend is fixed ---

@pytest.mark.parametrize("token", [
    pytest.param(make_token(exp=int(time.time()) - 10), id="expired"),
    pytest.param(make_token(azp="https://evil.example.com"), id="other-origin"),
])
def test_data_routes_reject_bad_tokens_themselves(client, db, token):
    # data routes forward any bearer token to supabase without checking it; supabase
    # rejects bad ones, but the caller gets a 500 (with the db error) instead of a 401,
    # and the token's origin (azp) is never checked at all
    assert client.get("/prompts", headers=bearer(token)).status_code == 401
    assert not db.calls


def test_database_errors_are_not_leaked(client, db):
    db.fail_with("Database error: secret internal detail")
    response = client.get("/prompts", headers=bearer(make_token()))
    assert response.status_code == 500
    assert "secret internal detail" not in response.text
