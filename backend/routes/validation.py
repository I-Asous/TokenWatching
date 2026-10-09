from fastapi import APIRouter, HTTPException

from repository import validation as validation_repository
from schema.validation import Validation, ValidationCreate

router = APIRouter()


# return the validations for a specific optimized prompt
@router.get("/optimized-prompts/{optimized_prompt_id}/validations", response_model=list[Validation])
def read_optimized_prompt_validations(optimized_prompt_id: int):
    try:
        return validation_repository.get_optimized_prompt_validations(optimized_prompt_id)
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


# save a validation
@router.post("/validations", response_model=list[Validation], status_code=201)
def create_validation(validation: ValidationCreate):
    try:
        return validation_repository.create_validation(validation)
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
