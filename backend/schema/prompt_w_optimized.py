from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class PromptWithOptimized(BaseModel):
    org_prompt_id: int
    optimized_prompt_id: int
    user_id: str
    org_prompt_txt: str
    optimized_prompt_txt: str
    org_prompt_tokens: int = Field(ge=0)
    optimized_prompt_tokens: int = Field(ge=0)
    org_prompt_input_time: datetime
    optimized_prompt_creation_time: datetime
    context: list[Any] | None
