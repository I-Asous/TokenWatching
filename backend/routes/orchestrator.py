import asyncio
import logging
from contextlib import suppress
from typing import Annotated

from anyio import from_thread, to_thread
from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.encoders import jsonable_encoder
from pydantic import ValidationError

from agents.orchestrator import OrchestrationResult
from auth import ALLOWED_ORIGINS, current_user, verify_token
from schema.orchestration import OrchestrationRequest
from service.orchestrator import RunOrchestrator

logger = logging.getLogger(__name__)

router = APIRouter()
# websockets can't use the router's token header check, so this one checks the token itself
ws_router = APIRouter()

# how long a new connection gets to send its token and prompt
FIRST_MESSAGE_TIMEOUT = 10

# this is a route that should be able to call the orchestrator of the
# ai agents and be able to return the final result of the orchestrator,
# and any messages in between!
@router.post("", response_model=OrchestrationResult)
def orchestrator(body: OrchestrationRequest, user_id: Annotated[str, Depends(current_user)]):
    try:
        return RunOrchestrator(user_id=user_id, prompt=body.prompt, target=body.target, context=body.context).execute()
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=f"orchestrator: {e}") from e


# same as the route above, but sends {"stage": ...} each time the pipeline moves on,
# then {"stage": "done", "result": ...} or {"stage": "failed"}
@ws_router.websocket("/ws")
async def orchestrator_ws(websocket: WebSocket):
    # CORS doesn't cover websockets, so we check the origin ourselves
    if websocket.headers.get("origin") not in ALLOWED_ORIGINS:
        await websocket.close(code=1008)
        return
    await websocket.accept()

    # browsers can't send headers on a websocket, so the token comes in the first message
    # (not in the url, since urls end up in logs)
    try:
        message = await asyncio.wait_for(websocket.receive_json(), FIRST_MESSAGE_TIMEOUT)
        body = OrchestrationRequest.model_validate(message)
        user_id = verify_token(message.get("token", ""))
    except (TimeoutError, ValueError, ValidationError, HTTPException):
        await websocket.close(code=1008)
        return
    except WebSocketDisconnect:
        return

    # the pipeline is slow and blocking, so it runs in a worker thread
    # and hands each stage back to this connection
    def send_stage(stage: str):
        from_thread.run(websocket.send_json, {"stage": stage})

    run = RunOrchestrator(user_id=user_id, prompt=body.prompt, target=body.target,
                          context=body.context, on_stage=send_stage)
    try:
        result = await to_thread.run_sync(run.execute)
        reply = {"stage": "done", "result": jsonable_encoder(result)}
    except Exception:  # pylint: disable=broad-exception-caught
        # the details stay in our logs, the user just gets "failed"
        logger.exception("orchestrator websocket run failed")
        reply = {"stage": "failed"}

    # if the user closed the popup, the next stage update failed and stopped the pipeline
    # early (saving api credits), and there's no one left to reply to
    with suppress(RuntimeError, WebSocketDisconnect):
        await websocket.send_json(reply)
        await websocket.close()
