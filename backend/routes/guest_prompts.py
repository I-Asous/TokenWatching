from fastapi import APIRouter, HTTPException

from repository import prompts as prompt_repository
from schema.prompts import GuestPromptCreate, Prompt

router = APIRouter()


@router.post("/guest-prompt", response_model=list[Prompt], status_code=201)
def create_guest_prompt(prompt: GuestPromptCreate):
    try:
        return prompt_repository.create_guest_prompt(prompt.txt_prompt)
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
