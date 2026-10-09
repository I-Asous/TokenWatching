from datetime import datetime

from pydantic import BaseModel


class Audit(BaseModel):
    audit_id: int
    created_at: datetime
    prompt_id: int | None = None
    estimated_tokens_used: int | None = None
    issues: list[str] | None = None
    severity: str | None = None

class AuditCreate(BaseModel):
    prompt_id: int
    estimated_tokens_used: int | None = None
    issues: list[str] | None = None
    severity: str | None = None
