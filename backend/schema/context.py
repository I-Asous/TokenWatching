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
    type: str
    file_link: str
    metadata: dict[str, Any] | None = None
    context_tokens: int | None = Field(default=None, ge=0)

class ContextInsert(ContextCreate):
    user_id: str
    prompt_id: int

## this is for when we check that the request is valid... should it be in
## its own file? perhaps... or perhaps not
class UploadUrlRequest(BaseModel):
    filename: str = Field(min_length=1, max_length=255)
    mime: str = Field(min_length=1)
    size: int = Field(gt=0)

class UploadUrlResponse(BaseModel):
    path: str
    signed_url: str
