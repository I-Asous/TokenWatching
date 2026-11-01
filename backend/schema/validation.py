from datetime import datetime

from pydantic import BaseModel, Field


class Validation(BaseModel):
    validation_id: int
    user_id: str
    optimized_prompt_id: int
    llm_call_id: int | None = None
    score: int = Field(ge=0, le=10)
    passed: bool
    reasoning: str
    react_trace: str
    created_at: datetime

class ValidationCreate(BaseModel):
    optimized_prompt_id: int
    llm_call_id: int | None = None
    score: int = Field(ge=0, le=10)
    passed: bool
    reasoning: str
    react_trace: str = ""

class ValidationInsert(ValidationCreate):
    user_id: str
