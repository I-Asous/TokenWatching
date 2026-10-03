from pydantic import UUID4

from repository.client import supabase

# return specific users org prompt+optimized prompt
def get_user_input_and_optimized_prompts(user_id: UUID4) -> list[dict]:
   try:
      response = supabase.table("prompt_with_optimized").select("*").eq("user_id", str(user_id)).execute()
      # if there is data, return it
      # need to figure what to do if there is no data... hmmhmmhmm
      return response.data
   # double check this later to see if this exception is the correct one!
   except Exception as e:
      raise RuntimeError(f"Database error: {str(e)}")


# return a specific users 1 prompt + optimized version of it
def get_user_prompt_w_optimized(user_id: UUID4, prompt_id: int):
   try:
      response = supabase.table("prompt_with_optimized").select("*").eq("user_id", str(user_id)).eq("org_prompt_id", prompt_id).execute()
      print(response.data)

      # if there is data, return it
      # need to figure what to do if there is no data... hmmhmmhmm
      return response.data
   # double check this later to see if this exception is the correct one!
   except Exception as e:
      raise RuntimeError(f"Database error: {str(e)}")