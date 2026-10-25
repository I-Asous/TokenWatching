import os
from supabase import Client

from schema.prompts import PromptCreate

from repository.client import get_supabase_admin


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


def create_guest_prompt(txt_prompt: str) -> list[dict]:
   """Save a guest prompt under the shared Supabase guest account."""
   guest_user_id = os.environ.get("GUEST_SUPABASE_USER_ID", "00e5e341-5160-4908-9648-802a17def3ce")
   try:
      response = get_supabase_admin().table("prompt").insert({
         "user_id": guest_user_id,
         "txt_prompt": txt_prompt,
         # The extension currently captures prompts from ChatGPT.
         "target": "chatgpt",
      }).execute()
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


