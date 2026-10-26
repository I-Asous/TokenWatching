from fastapi import APIRouter, HTTPException

from auth import UserDB
from repository import context as context_repository
from schema.context import Context, ContextCreate

router = APIRouter()


# return all of a specific users context, or only the context attached to one prompt
@router.get("", response_model=list[Context])
def read_user_contexts(db: UserDB, prompt_id: int | None = None):
    try:
        if prompt_id is None:
            return context_repository.get_user_contexts(db)
        return context_repository.get_user_prompt_contexts(db, prompt_id)
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=f"read_user_contexts: {exc}") from exc


# save context
@router.post("", response_model=list[Context], status_code=201)
def create_context(db: UserDB, context: ContextCreate):
    try:
        return context_repository.create_context(db, context)
    except RuntimeError as exc:
        # 42501 is the postgres error an RLS policy violation raises
        if "42501" in str(exc):
            raise HTTPException(status_code=403, detail="create_context: Not your data") from exc
        raise HTTPException(status_code=500, detail=f"create_context: {exc}") from exc
