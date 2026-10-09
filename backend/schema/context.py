from typing import Any

from pydantic import BaseModel


class Context(BaseModel):
    context_id: int
    user_id: str | None = None
    prompt_id: int | None = None
    type: str | None = None
    metadata: dict[str, Any] | None = None
    file_link: str | None = None
    context_tokens: int | None = None

class ContextCreate(BaseModel):
    user_id: str
    prompt_id: int
    type: str | None = None
    metadata: dict[str, Any] | None = None
    file_link: str | None = None
    context_tokens: int | None = None
