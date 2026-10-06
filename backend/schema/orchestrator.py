from pydantic import BaseModel, Field

# let's keep this for now but we can change it in the future to be in it's own files and not in agents
from agents.auditor import AuditResult
from agents.validator import ValidationResult

class OrchestrationResult(BaseModel):
    originalPrompt: str
    finalPrompt: str
    wasOptimized: bool
    auditResult: AuditResult
    attempts: list[ValidationResult] = Field(default_factory=list)
    tokensSaved: int = 0
    percentSaved: float = 0.0
    changes: list[str] = Field(default_factory=list)