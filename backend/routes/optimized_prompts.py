from fastapi import APIRouter, HTTPException

from auth import UserDB
from repository import optimized_prompts as optimized_prompt_repository
from schema.optimized_prompts import OptimizedPrompt, OptimizedPromptCreate

router = APIRouter()


# return a specific users optimized prompts
@router.get("", response_model=list[OptimizedPrompt])
def read_user_optimized_prompts(db: UserDB):
    try:
        return optimized_prompt_repository.get_user_optimized_prompts(db)
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

# return a specific users one specific optimized prompts
@router.get("/{optimized_prompt_id}", response_model=OptimizedPrompt)
def read_user_optimized_prompt(db: UserDB, optimized_prompt_id: int):
    try:
        return optimized_prompt_repository.get_user_optimized_prompt(db, optimized_prompt_id)
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


# optimized prompt from frontend gets send back to backend
# ensure if we need put keeping just in case
@router.post("", response_model=list[OptimizedPrompt], status_code=201)
def create_optimized_prompt(db: UserDB, prompt: OptimizedPromptCreate):
    try:
        return optimized_prompt_repository.create_optimized_prompt(db, prompt)
    except RuntimeError as exc:
        # 42501 is the postgres error an RLS policy violation raises
        if "42501" in str(exc):
            raise HTTPException(status_code=403, detail="Not your data") from exc
        raise HTTPException(status_code=500, detail=str(exc)) from exc
