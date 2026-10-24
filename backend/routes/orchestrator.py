from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException

from agents.orchestrator import OrchestrationResult
from auth import current_user
from schema.orchestration import OrchestrationRequest
from service.orchestrator import RunOrchestrator

router = APIRouter()

# this is a route that should be able to call the orchestrator of the 
# ai agents and be able to return the final result of the orchestrator, 
# and any messages in between!
@router.post("", response_model=OrchestrationResult)
def orchestrator(body: OrchestrationRequest, user_id: Annotated[str, Depends(current_user)]):
    try:
        return RunOrchestrator(user_id=user_id, prompt=body.prompt, target=body.target).execute()
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e)) from e
