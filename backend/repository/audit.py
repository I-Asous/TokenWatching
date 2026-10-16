from supabase import Client

from schema.audit import AuditCreate


# return the audits for a specific prompt
def get_prompt_audits(db: Client, prompt_id: int) -> list[dict]:
   try:
      response = db.table("audit").select("*").eq("prompt_id", prompt_id).execute()
      return response.data
   except Exception as e:
      raise RuntimeError(f"Database error: {str(e)}")


# send an audit to the database
def create_audit(db: Client, audit: AuditCreate) -> list[dict]:
   try:
      response = db.table("audit").insert(audit.model_dump(mode="json")).execute()
      return response.data
   except Exception as e:
      raise RuntimeError(f"Database error: {str(e)}")
