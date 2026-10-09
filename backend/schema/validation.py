from datetime import datetime

from pydantic import BaseModel, Field


# "pass" is a python keyword, so the field is named passed and aliased to the column
class Validation(BaseModel):
    validation_id: int
    created_at: datetime
    optimized_prompt_id: int | None = None
    score: float | None = None
    passed: bool | None = Field(default=None, alias="pass")
    agent_tokens_used: int | None = None
    reasoning: str | None = None
    react_trace: str | None = None

class ValidationCreate(BaseModel):
    optimized_prompt_id: int
    score: float | None = None
    passed: bool | None = Field(default=None, alias="pass")
    agent_tokens_used: int | None = None
    reasoning: str | None = None
    react_trace: str | None = None
