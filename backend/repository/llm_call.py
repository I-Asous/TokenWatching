from supabase import Client

from schema.llm_call import LlmCallCreate

# send an llm call to the database
def create_llm_call(db: Client, llm_call: LlmCallCreate) -> list[dict]:
   try:
      response = db.table("llm_call").insert(llm_call.model_dump(mode="json")).execute()
      return response.data
   except Exception as e:
      raise RuntimeError(f"Database error: {str(e)}")
