from supabase import Client

from schema.context import ContextCreate, ContextInsert

# return all of the caller's context (RLS limits rows to the token's user)
def get_user_contexts(db: Client) -> list[dict]:
   try:
      response = db.table("context").select("*").execute()
      return response.data
   except Exception as e:
      raise RuntimeError(f"Database error: {str(e)}")

# return the context attached to one of the caller's prompts
def get_user_prompt_contexts(db: Client, prompt_id: int) -> list[dict]:
   try:
      response = db.table("context").select("*").eq("prompt_id", prompt_id).execute()
      return response.data
   except Exception as e:
      raise RuntimeError(f"Database error: {str(e)}")

# send context to the database
def create_context(db: Client, context: ContextCreate) -> list[dict]:
   try:
      response = db.table("context").insert(context.model_dump(mode="json")).execute()
      return response.data
   except Exception as e:
      raise RuntimeError(f"Database error: {str(e)}")

# batch a list of contexts to the database!
def create_contexts(db: Client, contexts: list[ContextInsert]) -> list[dict]:
   try:
      response = db.table("context").insert([c.model_dump(mode="json") for c in contexts]).execute()
      return response.data
   except Exception as e:
      raise RuntimeError(f"Database error: {str(e)}")
