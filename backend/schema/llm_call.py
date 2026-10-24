from datetime import datetime

from pydantic import BaseModel, Field


class LlmCall(BaseModel):
    call_id: int
    user_id: str
    run_id: int
    agent: str
    model: str
    input_tokens: int | None = None
    output_tokens: int | None = None
    cost: float | None = None
    latency_ms: int | None = None
    succeeded: bool
    error_message: str | None = None
    created_at: datetime

class LlmCallCreate(BaseModel):
    run_id: int
    agent: str
    model: str
    input_tokens: int | None = Field(default=None, ge=0)
    output_tokens: int | None = Field(default=None, ge=0)
    cost: float | None = Field(default=None, ge=0)
    latency_ms: int | None = Field(default=None, ge=0)
    succeeded: bool
    error_message: str | None = None
