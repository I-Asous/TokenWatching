from supabase import Client

from schema.prompts import PromptCreate


### GET METHODS

# return a specific users original prompts
def get_user_input_prompts(db: Client) -> list[dict]:
   try:
      response = db.table("prompt").select("*").execute()
      # if there is data, return it
      # need to figure what to do if there is no data... hmmhmmhmm
      # AND HANDLE ONLY 1 PROMPT VS MULTIPLE
      return response.data
   except Exception as e:
      raise RuntimeError(f"Database error: {str(e)}")

# return a specific users 1 prompt
def get_user_input_prompt(db: Client, prompt_id: int):
   try:
      response = db.table("prompt").select("*").eq("prompt_id", prompt_id).execute()
      # if there is data, return it
      # need to figure what to do if there is no data... hmmhmmhmm
      return response.data[0] if response.data else None
   except Exception as e:
      raise RuntimeError(f"Database error: {str(e)}")


### POST METHODS

# send a prompt to the database :3
# prompt needs to be properly defined
def create_prompt(db: Client, prompt: PromptCreate) -> list[dict]:
   try:
      response = db.table("prompt").insert(prompt.model_dump(mode="json")).execute()
      # if there is data, return it
      # need to figure what to do if there is no data... hmmhmmhmm
      return response.data
   except Exception as e:
      raise RuntimeError(f"Database error: {str(e)}")


# delete prompt (which also should delete the optimized prompt who is with me!)
def delete_prompt(db: Client, prompt_id: int):
   try:
      response = db.table("prompt").delete().eq("prompt_id", prompt_id).execute()
      # if there is data, return it
      # need to figure what to do if there is no data... hmmhmmhmm
      return response.data
   except Exception as e:
      raise RuntimeError(f"Database error: {str(e)}")


