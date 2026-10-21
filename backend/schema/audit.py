from datetime import datetime

from pydantic import BaseModel, Field

class Audit(BaseModel):
    audit_id: int
    user_id: str
    run_id: int
    llm_call_id: int | None = None
    token_count: int = Field(ge=0)
    estimated_cost: float = Field(ge=0)
    severity: str
    created_at: datetime

class AuditCreate(BaseModel):
    run_id: int
    llm_call_id: int | None = None
    token_count: int = Field(ge=0)
    estimated_cost: float = Field(ge=0)
    severity: str

class AuditInsert(AuditCreate):
    user_id: str
