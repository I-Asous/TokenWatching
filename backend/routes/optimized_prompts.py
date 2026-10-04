from fastapi import APIRouter, HTTPException
from pydantic import UUID4

from repository import optimized_prompts as optimized_prompt_repository
from schema.optimized_prompts import OptimizedPrompt, OptimizedPromptCreate

router = APIRouter()


# return a specific users optimized prompts
@router.get("/users/{user_id}/optimized-prompts", response_model=list[OptimizedPrompt])
def read_user_optimized_prompts(user_id: UUID4):
    try:
        return optimized_prompt_repository.get_user_optimized_prompts(user_id)
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

# return a specific users one specific optimized prompts
@router.get("/users/{user_id}/optimized-prompts/{optimized_prompt_id}", response_model=OptimizedPrompt)
def read_user_optimized_prompt(user_id: UUID4, optimized_prompt_id: int):
    try:
        return optimized_prompt_repository.get_user_optimized_prompt(user_id, optimized_prompt_id)
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


# optimized prompt from frontend gets send back to backend
# ensure if we need put keeping just in case
@router.post("/optimized-prompts", response_model=list[OptimizedPrompt], status_code=201)
def create_optimized_prompt(prompt: OptimizedPromptCreate):
    try:
        return optimized_prompt_repository.create_optimized_prompt(prompt)
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
