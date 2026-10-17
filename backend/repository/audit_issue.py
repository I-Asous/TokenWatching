from supabase import Client

from schema.audit_issue import AuditIssueCreate

# return the issues found by a specific audit
def get_audit_issues(db: Client, audit_id: int) -> list[dict]:
   try:
      response = db.table("audit_issue").select("*").eq("audit_id", audit_id).execute()
      return response.data
   except Exception as e:
      raise RuntimeError(f"Database error: {str(e)}")

# send an audit issue to the database
def create_audit_issue(db: Client, audit_issue: AuditIssueCreate) -> list[dict]:
   try:
      response = db.table("audit_issue").insert(audit_issue.model_dump(mode="json")).execute()
      return response.data
   except Exception as e:
      raise RuntimeError(f"Database error: {str(e)}")
