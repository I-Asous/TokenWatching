from pydantic import BaseModel, Field

class AuditIssue(BaseModel):
    issue_id: int
    user_id: str
    audit_id: int
    issue_type: str

class AuditIssueCreate(BaseModel):
    audit_id: int
    issue_type: str = Field(min_length=1)

class AuditIssueInsert(AuditIssueCreate):
    user_id: str
