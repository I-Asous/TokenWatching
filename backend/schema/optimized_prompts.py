# do we really need to import this 3 times in 3 separate file :/

from pydantic import BaseModel, Field
from datetime import datetime


class OptimizedPrompt(BaseModel):
    optimized_prompt_id: int
    user_id: str
    run_id: int
    llm_call_id: int | None = None
    feedback_validation_id: int | None = None
    txt_prompt: str
    tokens: int = Field(ge=0)
    tokens_saved: int = Field(ge=0)
    percent_saved: float = Field(ge=0, le=100)
    unchanged: bool
    changes: list[str]
    preserved_constraints: list[str]
    created_at: datetime

class OptimizedPromptCreate(BaseModel):
    run_id: int
    llm_call_id: int | None = None
    feedback_validation_id: int | None = None
    txt_prompt: str = Field(min_length=1)
    tokens: int = Field(ge=0)
    tokens_saved: int = Field(ge=0)
    percent_saved: float = Field(ge=0, le=100)
    unchanged: bool = False
    changes: list[str] = Field(default_factory=list)
    preserved_constraints: list[str] = Field(default_factory=list)

class OptimizedPromptInsert(OptimizedPromptCreate):
    user_id: str
