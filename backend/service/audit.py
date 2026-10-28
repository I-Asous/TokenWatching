from supabase import Client

from agents.auditor import AuditResult
from repository.audit import create_audit
from repository.audit_issue import create_audit_issues
from schema.audit_issue import AuditIssueInsert
from service.structure_response import structure_response

# service to save an audit and also save the issues that comes with an audit
def save_audit(db: Client, user_id: str, run_id: int, audit: AuditResult) -> dict:
    # we create an audit...
    auditted = create_audit(db, structure_response(audit, user_id, run_id=run_id))[0]

    # if the audit has issues, we just put them into a list...
    # TODO: it feels weird having to pack and unpack these values (here and in repository), am i doing validation wrong?
    if audit.issues:
        issue_list = []
        for issue in audit.issues:
            issue_list.append(AuditIssueInsert(user_id=user_id, audit_id=auditted["audit_id"], issue_type=issue))
        create_audit_issues(db, issue_list)
    return auditted
