from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


# optimized_* columns are null when no rewrite passed or no run has finished yet
class PromptWithOptimized(BaseModel):
    org_prompt_id: int
    optimized_prompt_id: int | None
    user_id: str
    org_prompt_txt: str
    optimized_prompt_txt: str | None
    org_prompt_tokens: int | None = Field(ge=0)
    optimized_prompt_tokens: int | None = Field(ge=0)
    org_prompt_input_time: datetime
    optimized_prompt_creation_time: datetime | None
    tokens_saved: int | None
    percent_saved: float | None
    severity: str | None
    target: str
    context: list[Any] | None
