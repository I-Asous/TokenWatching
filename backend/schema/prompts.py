from typing import Any
from datetime import datetime

from pydantic import BaseModel, Field

class Prompt(BaseModel):
    prompt_id: int
    user_id: str
    txt_prompt: str
    inputted_at: datetime

class PromptCreate(BaseModel):
    txt_prompt: str
    context: list[Any] = Field(default_factory=list)
