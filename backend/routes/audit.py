from fastapi import APIRouter, HTTPException

from auth import UserDB
from repository import audit as audit_repository
from schema.audit import Audit, AuditCreate

router = APIRouter()


# return the audits for a specific prompt
@router.get("", response_model=list[Audit])
def read_prompt_audits(db: UserDB, prompt_id: int):
    try:
        return audit_repository.get_prompt_audits(db, prompt_id)
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


# save an audit
@router.post("", response_model=list[Audit], status_code=201)
def create_audit(db: UserDB, audit: AuditCreate):
    try:
        return audit_repository.create_audit(db, audit)
    except RuntimeError as exc:
        # 42501 is the postgres error an RLS policy violation raises
        if "42501" in str(exc):
            raise HTTPException(status_code=403, detail="Not your data") from exc
        raise HTTPException(status_code=500, detail=str(exc)) from exc
