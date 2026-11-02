"""
Tests for the orchestrator websocket (/orchestrator/ws): only the extension can open it,
the token in the first message is verified before the pipeline runs, and the user
only sees stage names and the final result - never error details.
"""
import time

import pytest
from starlette.websockets import WebSocketDisconnect

import routes.orchestrator
from conftest import EXTENSION_ORIGIN, make_token

# pylint: disable=redefined-outer-name,unused-argument  # pytest fixtures

URL = "/orchestrator/ws"
ORIGIN = {"origin": EXTENSION_ORIGIN}
PROMPT = {"prompt": "hi", "target": "chatgpt"}


class FakeRun:  # pylint: disable=too-few-public-methods
    """Stands in for RunOrchestrator: walks two stages without calling claude or the db."""
    runs = []
    fail = False

    def __init__(self, user_id, prompt, target, context, on_stage):
        self.user_id, self.on_stage = user_id, on_stage
        FakeRun.runs.append(self)

    def execute(self):
        self.on_stage("auditing")
        self.on_stage("optimizing")
        if FakeRun.fail:
            raise RuntimeError("Orchestration error: secret internal detail")
        return {"finalPrompt": "hi!"}


@pytest.fixture
def fake_run(monkeypatch):
    FakeRun.runs, FakeRun.fail = [], False
    monkeypatch.setattr(routes.orchestrator, "RunOrchestrator", FakeRun)
    return FakeRun


def closed_with_policy_violation(client, first_message, headers=None):
    headers = ORIGIN if headers is None else headers
    with pytest.raises(WebSocketDisconnect) as closed:
        with client.websocket_connect(URL, headers=headers) as ws:
            ws.send_json(first_message)
            ws.receive_json()
    return closed.value.code == 1008


def test_streams_stages_then_result_then_closes(client, fake_run):
    with client.websocket_connect(URL, headers=ORIGIN) as ws:
        ws.send_json({"token": make_token(), **PROMPT})
        assert ws.receive_json() == {"stage": "auditing"}
        assert ws.receive_json() == {"stage": "optimizing"}
        assert ws.receive_json() == {"stage": "done", "result": {"finalPrompt": "hi!"}}
        # the server closes the connection once the result is sent
        with pytest.raises(WebSocketDisconnect):
            ws.receive_json()
    # the user comes from the token
    assert [run.user_id for run in fake_run.runs] == ["user_me"]


def test_failure_does_not_leak_details(client, fake_run):
    fake_run.fail = True
    with client.websocket_connect(URL, headers=ORIGIN) as ws:
        ws.send_json({"token": make_token(), **PROMPT})
        messages = [ws.receive_json() for _ in range(3)]
    assert messages[-1] == {"stage": "failed"}
    assert "secret" not in str(messages)


@pytest.mark.parametrize("headers", [{}, {"origin": "https://evil.example.com"}])
def test_other_origins_rejected(client, fake_run, headers):
    assert closed_with_policy_violation(client, {"token": make_token(), **PROMPT}, headers)
    assert not fake_run.runs


@pytest.mark.parametrize("message", [
    pytest.param(PROMPT, id="no-token"),
    pytest.param({"token": "not-a-jwt", **PROMPT}, id="garbage-token"),
    pytest.param({"token": make_token(exp=int(time.time()) - 10), **PROMPT}, id="expired"),
    pytest.param({"token": make_token(drop=("exp",)), **PROMPT}, id="no-expiry"),
    pytest.param({"token": make_token(azp="https://evil.example.com"), **PROMPT}, id="other-azp"),
    pytest.param({"token": 123, **PROMPT}, id="token-not-a-string"),
    pytest.param({"token": make_token(), "prompt": "", "target": "chatgpt"}, id="empty-prompt"),
    pytest.param({"token": make_token()}, id="no-prompt"),
    pytest.param(["not", "an", "object"], id="not-an-object"),
])
def test_bad_first_message_rejected_before_pipeline_runs(client, fake_run, message):
    assert closed_with_policy_violation(client, message)
    assert not fake_run.runs


def test_silent_connection_times_out(client, fake_run, monkeypatch):
    monkeypatch.setattr(routes.orchestrator, "FIRST_MESSAGE_TIMEOUT", 0.1)
    with pytest.raises(WebSocketDisconnect) as closed:
        with client.websocket_connect(URL, headers=ORIGIN) as ws:
            ws.receive_json()
    assert closed.value.code == 1008
    assert not fake_run.runs
