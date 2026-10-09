from fastapi import APIRouter, HTTPException

from repository import context as context_repository
from schema.context import Context, ContextCreate

router = APIRouter()


# return all of a specific users context
@router.get("/users/{user_id}/contexts", response_model=list[Context])
def read_user_contexts(user_id: str):
    try:
        return context_repository.get_user_contexts(user_id)
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

# return the context attached to a specific users prompt
@router.get("/users/{user_id}/prompts/{prompt_id}/contexts", response_model=list[Context])
def read_user_prompt_contexts(user_id: str, prompt_id: int):
    try:
        return context_repository.get_user_prompt_contexts(user_id, prompt_id)
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


# save context
@router.post("/contexts", response_model=list[Context], status_code=201)
def create_context(context: ContextCreate):
    try:
        return context_repository.create_context(context)
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
