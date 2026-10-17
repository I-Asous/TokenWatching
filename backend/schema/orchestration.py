from datetime import datetime

from pydantic import BaseModel, Field

class Orchestration(BaseModel):
    run_id: int
    user_id: str
    prompt_id: int
    status: str
    rate_per_mtok: float = Field(ge=0)
    final_optimized_prompt_id: int | None = None
    error_stage: str | None = None
    error_message: str | None = None
    started_at: datetime
    finished_at: datetime | None = None
    updated_at: datetime

class OrchestrationCreate(BaseModel):
    prompt_id: int
    rate_per_mtok: float = Field(ge=0)

class OrchestrationUpdate(BaseModel):
    status: str
    final_optimized_prompt_id: int | None = None
    error_stage: str | None = None
    error_message: str | None = None
    finished_at: datetime | None = None
