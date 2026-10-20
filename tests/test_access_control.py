"""
Tests that a logged-in user can only reach their own data - URL user ids must
match the token, and request bodies or errors must not open other doors.
"""
import pytest

from repository import prompts
from conftest import api_routes, bearer, make_token

# pylint: disable=redefined-outer-name  # pytest fixtures


def user_routes(user_id):
    """Every (method, path) whose path has {user_id}, filled with the given id."""
    return [(method, filled) for method, path, filled in api_routes(user_id) if "{user_id}" in path]


def test_user_routes_were_found():
    # guard so the parametrized tests below can't silently test nothing
    assert len(user_routes("x")) >= 8


@pytest.mark.parametrize("method,path", list(user_routes("user_other")))
def test_other_users_data_forbidden(client, db, method, path):
    assert client.request(method, path, headers=bearer(make_token())).status_code == 403
    assert not db.calls


@pytest.mark.parametrize("method,path", list(user_routes("user_me")))
def test_own_data_not_forbidden(client, db, method, path):  # pylint: disable=unused-argument
    assert client.request(method, path, headers=bearer(make_token())).status_code != 403


# --- known holes: these assert the secure behaviour and fail until the routes are fixed ---

@pytest.mark.parametrize("path,body", [
    ("/prompts/prompt", {"user_id": "user_other", "txt_prompt": "hi", "tokens": 1}),
    ("/optimized-prompts/optimized-prompts",
     {"user_id": "user_other", "org_prompt_id": 1, "txt_prompt": "hi", "tokens": 1}),
])
def test_cannot_create_rows_as_another_user(client, db, path, body):
    response = client.post(path, json=body, headers=bearer(make_token()))
    assert response.status_code == 403, "body user_id is trusted instead of the token"
    assert not db.calls


def test_delete_is_scoped_to_the_caller(client, db):
    client.delete("/prompts/prompts/1", headers=bearer(make_token()))
    assert db.calls, "delete was never attempted"
    assert "user_me" in db.calls[0][1], "delete_prompt deletes by id alone, so anyone's prompt can be deleted"


def test_database_errors_are_not_leaked(client, db, monkeypatch):  # pylint: disable=unused-argument
    def broken(*_args):
        raise RuntimeError("Database error: secret internal detail")
    monkeypatch.setattr(prompts, "get_user_input_prompts", broken)
    response = client.get("/prompts/users/user_me/prompts", headers=bearer(make_token()))
    assert response.status_code == 500
    assert "secret internal detail" not in response.text
