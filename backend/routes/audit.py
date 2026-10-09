from fastapi import APIRouter, HTTPException

from repository import audit as audit_repository
from schema.audit import Audit, AuditCreate

router = APIRouter()


# return the audits for a specific prompt
@router.get("/prompts/{prompt_id}/audits", response_model=list[Audit])
def read_prompt_audits(prompt_id: int):
    try:
        return audit_repository.get_prompt_audits(prompt_id)
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


# save an audit
@router.post("/audits", response_model=list[Audit], status_code=201)
def create_audit(audit: AuditCreate):
    try:
        return audit_repository.create_audit(audit)
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
