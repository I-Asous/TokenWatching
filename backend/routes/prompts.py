from fastapi import APIRouter, HTTPException

from auth import UserDB
from repository import prompts as prompt_repository
from schema.prompts import Prompt, PromptCreate

router = APIRouter()


# return a specific users original prompts
@router.get("", response_model=list[Prompt])
def read_user_prompts(db: UserDB):
    try:
        return prompt_repository.get_user_input_prompts(db)
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=f"read_user_prompts: {exc}") from exc

# return a specific users 1 prompt
@router.get("/{prompt_id}")
def read_user_prompt_with_optimized(db: UserDB, prompt_id: int):
    try:
        result = prompt_repository.get_user_input_prompt(db, prompt_id)
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=f"read_user_prompt_with_optimized: {exc}") from exc
    if result is None:
        raise HTTPException(status_code=404, detail="read_user_prompt_with_optimized: Prompt not found")
    return result

# user submits a prompt
@router.post("", response_model=list[Prompt], status_code=201)
def create_prompt(db: UserDB, prompt: PromptCreate):
    try:
        return prompt_repository.create_prompt(db, prompt)
    except RuntimeError as exc:
        # 42501 is the postgres error an RLS policy violation raises
        if "42501" in str(exc):
            raise HTTPException(status_code=403, detail="create_prompt: Not your data") from exc
        raise HTTPException(status_code=500, detail=f"create_prompt: {exc}") from exc


# delete a prompt
@router.delete("/{prompt_id}")
def remove_prompt(db: UserDB, prompt_id: int):
    try:
        return prompt_repository.delete_prompt(db, prompt_id)
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=f"remove_prompt: {exc}") from exc
