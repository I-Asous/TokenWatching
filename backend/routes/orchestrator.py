from fastapi import APIRouter, HTTPException

# from schema.orchestration import OrchestrationResult
# from service.orchestrator import orchestrator as orchestrator_service

router = APIRouter()

# this is a route that should be able to call the orchestrator of the 
# ai agents and be able to return the final result of the orchestrator, 
# and any messages in between!
# @router.post("", response_model=OrchestrationResult)
@router.post("")
def orchestrator(prompt: str, target: str): # idk what target is!
    pass
    # try:
    #     return orchestrator_service(prompt, target)
    # except RuntimeError as exc:
    #     raise HTTPException(status_code=500, detail=str(exc)) from exc
    
        
