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

# an answer to a clarifying question (from result.questions or result.vagueness.questions)
class ClarifyingAnswer(BaseModel):
    question: str = Field(min_length=1, max_length=500)
    answer: str = Field(max_length=2000)

class OrchestrationRequest(BaseModel):
    prompt: str = Field(min_length=1)
    target: str
    # send the same prompt again with every answer so far to have them worked into the rewrite
    answers: list[ClarifyingAnswer] = Field(default_factory=list, max_length=10)
