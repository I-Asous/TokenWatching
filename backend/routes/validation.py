from fastapi import APIRouter, HTTPException

from auth import UserDB
from repository import validation as validation_repository
from schema.validation import Validation, ValidationCreate

router = APIRouter()


# return the validations for a specific optimized prompt
@router.get("", response_model=list[Validation])
def read_optimized_prompt_validations(db: UserDB, optimized_prompt_id: int):
    try:
        return validation_repository.get_optimized_prompt_validations(db, optimized_prompt_id)
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


# save a validation
@router.post("", response_model=list[Validation], status_code=201)
def create_validation(db: UserDB, validation: ValidationCreate):
    try:
        return validation_repository.create_validation(db, validation)
    except RuntimeError as exc:
        # 42501 is the postgres error an RLS policy violation raises
        if "42501" in str(exc):
            raise HTTPException(status_code=403, detail="Not your data") from exc
        raise HTTPException(status_code=500, detail=str(exc)) from exc
