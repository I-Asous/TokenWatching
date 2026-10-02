from typing import Any
from datetime import datetime

from pydantic import UUID4, BaseModel, ConfigDict, Field

class Prompt(BaseModel):
    prompt_id: int
    user_id: UUID4
    txt_prompt: str
    tokens: int = Field(ge=0)
    inputted_at: datetime
    # see how to make this more specific
    context: list[Any] = Field(default_factory=list)

class PromptCreate(BaseModel):
    user_id: UUID4
    txt_prompt: str
    tokens: int = Field(ge=0)
    context: list[Any] = Field(default_factory=list)
