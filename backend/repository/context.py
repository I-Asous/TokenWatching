from schema.context import ContextCreate

from repository.client import supabase


# return all of a specific users context
def get_user_contexts(user_id: str) -> list[dict]:
   try:
      response = supabase.table("context").select("*").eq("user_id", str(user_id)).execute()
      return response.data
   except Exception as e:
      raise RuntimeError(f"Database error: {str(e)}")


# return the context attached to a specific users prompt
def get_user_prompt_contexts(user_id: str, prompt_id: int) -> list[dict]:
   try:
      response = supabase.table("context").select("*").eq("user_id", str(user_id)).eq("prompt_id", prompt_id).execute()
      return response.data
   except Exception as e:
      raise RuntimeError(f"Database error: {str(e)}")


# send context to the database
def create_context(context: ContextCreate) -> list[dict]:
   try:
      response = supabase.table("context").insert(context.model_dump(mode="json")).execute()
      return response.data
   except Exception as e:
      raise RuntimeError(f"Database error: {str(e)}")
