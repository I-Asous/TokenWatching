from fastapi import APIRouter, HTTPException
from pydantic import UUID4

from repository import prompt_w_optimized as prompt_w_optimized_repository
from schema.prompt_w_optimized import PromptWithOptimized

router = APIRouter()

# return specific users org prompt+optimized prompt
@router.get("/users/{user_id}/prompts-with-optimized", response_model=list[PromptWithOptimized])
def read_user_prompts_with_optimized(user_id: UUID4):
    try:
        return prompt_w_optimized_repository.get_user_input_and_optimized_prompts(user_id)
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

# return a specific users 1 prompt + optimized version of it
@router.get("/users/{user_id}/prompts-with-optimized/{prompt_id}", response_model=list[PromptWithOptimized])
def read_user_prompt_with_optimized(user_id: UUID4, prompt_id: int):
    try:
        result = prompt_w_optimized_repository.get_user_prompt_w_optimized(user_id, prompt_id)
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    if result is None:
        raise HTTPException(status_code=404, detail="Prompt not found")
    return result