from datetime import datetime

from pydantic import BaseModel, Field

class Orchestration(BaseModel):
    run_id: int
    user_id: str
    prompt_id: int
    status: str
    final_optimized_prompt_id: int | None = None
    error_stage: str | None = None
    error_message: str | None = None
    started_at: datetime
    finished_at: datetime | None = None
    updated_at: datetime

class OrchestrationCreate(BaseModel):
    prompt_id: int

class OrchestrationUpdate(BaseModel):
    status: str
    final_optimized_prompt_id: int | None = None
    error_stage: str | None = None
    error_message: str | None = None
    finished_at: datetime | None = None

class OrchestrationInsert(OrchestrationCreate):
    user_id: str

class OrchestrationRequest(BaseModel):
    prompt: str = Field(min_length=1)
    target: str
