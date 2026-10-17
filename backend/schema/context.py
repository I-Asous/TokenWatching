from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class Context(BaseModel):
    context_id: int
    user_id: str
    prompt_id: int
    type: str
    metadata: dict[str, Any] | None = None
    file_link: str | None = None
    context_tokens: int | None = None
    created_at: datetime

class ContextCreate(BaseModel):
    prompt_id: int
    type: str
    metadata: dict[str, Any] | None = None
    file_link: str | None = None
    context_tokens: int | None = Field(default=None, ge=0)
