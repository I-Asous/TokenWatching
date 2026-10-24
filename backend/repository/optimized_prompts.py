from supabase import Client

from schema.optimized_prompts import OptimizedPromptCreate


# return a specific users optimized prompts
def get_user_optimized_prompts(db: Client) -> list[dict]:
   try:
      response = db.table("optimized_prompts").select("*").execute()
      # if there is data, return it
      # need to figure what to do if there is no data... hmmhmmhmm
      return response.data
   # double check this later to see if this exception is the correct one!
   except Exception as e:
      raise RuntimeError(f"Database error: {str(e)}")

# return a specific users 1 optimized prompt
def get_user_optimized_prompt(db: Client, optimized_prompt_id: int) -> list[dict]:
   try:
      response = db.table("optimized_prompts").select("*").eq("optimized_prompt_id", optimized_prompt_id).execute()
      # if there is data, return it
      # need to figure what to do if there is no data... hmmhmmhmm
      return response.data
   # double check this later to see if this exception is the correct one!
   except Exception as e:
      raise RuntimeError(f"Database error: {str(e)}")


# send an optimized prompt to the database :3
def create_optimized_prompt(db: Client, prompt: OptimizedPromptCreate) -> list[dict]:
   try:
      response = db.table("optimized_prompts").insert(prompt.model_dump(mode="json")).execute()
      # if there is data, return it
      # need to figure what to do if there is no data... hmmhmmhmm
      return response.data
   # double check this later to see if this exception is the correct one!
   except Exception as e:
      raise RuntimeError(f"Database error: {str(e)}")
