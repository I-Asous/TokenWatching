from schema.audit import AuditCreate

from repository.client import get_supabase


# return the audits for a specific prompt
def get_prompt_audits(prompt_id: int) -> list[dict]:
   try:
      response = get_supabase().table("audit").select("*").eq("prompt_id", prompt_id).execute()
      return response.data
   except Exception as e:
      raise RuntimeError(f"Database error: {str(e)}")


# send an audit to the database
def create_audit(audit: AuditCreate) -> list[dict]:
   try:
      response = get_supabase().table("audit").insert(audit.model_dump(mode="json")).execute()
      return response.data
   except Exception as e:
      raise RuntimeError(f"Database error: {str(e)}")
