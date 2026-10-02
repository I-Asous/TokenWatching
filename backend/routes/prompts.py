from fastapi import APIRouter, HTTPException
from pydantic import UUID4

from repository import prompts as prompt_repository
from schema.prompts import Prompt, PromptCreate

router = APIRouter()


# return a specific users original prompts
@router.get("/users/{user_id}/prompts", response_model=list[Prompt])
def read_user_prompts(user_id: UUID4):
    try:
        return prompt_repository.get_user_input_prompts(user_id)
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

# return a specific users 1 prompt
@router.get("/users/{user_id}/prompt/{prompt_id}")
def read_user_prompt_with_optimized(user_id: UUID4, prompt_id: int):
    try:
        result = prompt_repository.get_user_input_prompt(user_id, prompt_id)
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    if result is None:
        raise HTTPException(status_code=404, detail="Prompt not found")
    return result

### TODO: MAKE A VIEW IN SUPABASE 
# return specific users org prompt+optimized prompt
@router.get("/users/{user_id}/prompts-with-optimized")
def read_user_prompts_with_optimized(user_id: UUID4):
    try:
        return prompt_repository.get_user_input_and_optimized_prompts(user_id)
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


### TODO: MAKE A VIEW IN SUPABASE 
# return a specific users 1 prompt + optimized version of it
@router.get("/users/{user_id}/prompts-with-optimized/{prompt_id}")
def read_user_prompt_with_optimized(user_id: UUID4, prompt_id: int):
    try:
        result = prompt_repository.get_user_prompt_w_optimized(user_id, prompt_id)
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    if result is None:
        raise HTTPException(status_code=404, detail="Prompt not found")
    return result


# user submits a prompt
@router.post("/prompt", response_model=list[Prompt], status_code=201)
def create_prompt(prompt: PromptCreate):
    try:
        return prompt_repository.create_prompt(prompt)
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


# delete a prompt
@router.delete("/prompts/{prompt_id}")
def remove_prompt(prompt_id: int):
    try:
        return prompt_repository.delete_prompt(prompt_id)
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
