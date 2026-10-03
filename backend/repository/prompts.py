from pydantic import UUID4

from schema.prompts import PromptCreate

from repository.client import supabase


### GET METHODS
# we can change this into upsert

## this may seem redundant but i decided to implement all of them, but imo i think if we want to see a prompt, we will def want to see the optimized version alongside it as well :/
# return a specific users original prompts
def get_user_input_prompts(user_id: UUID4) -> list[dict]:
   try:
      response = supabase.table("prompt").select("*").eq("user_id", str(user_id)).execute()
      # if there is data, return it
      # need to figure what to do if there is no data... hmmhmmhmm
      # AND HANDLE ONLY 1 PROMPT VS MULTIPLE
      return response.data
   # double check this later to see if this exception is the correct one!
   except Exception as e:
      raise RuntimeError(f"Database error: {str(e)}")

# return a specific users 1 prompt
def get_user_input_prompt(user_id: UUID4, prompt_id: int):
   try:
      response = supabase.table("prompt").select("*").eq("user_id", str(user_id)).eq("prompt_id", prompt_id).execute()
      # if there is data, return it
      # need to figure what to do if there is no data... hmmhmmhmm
      return response.data[0] if response.data else None
   # double check this later to see if this exception is the correct one!
   except Exception as e:
      raise RuntimeError(f"Database error: {str(e)}")


### POST METHODS

# send a prompt to the database :3
# prompt needs to be properly defined
def create_prompt(prompt: PromptCreate) -> list[dict]:
   try:
      response = supabase.table("prompt").insert(prompt.model_dump(mode="json")).execute()
      # if there is data, return it
      # need to figure what to do if there is no data... hmmhmmhmm
      return response.data
   # double check this later to see if this exception is the correct one!
   except Exception as e:
      raise RuntimeError(f"Database error: {str(e)}")


# delete prompt (which also should delete the optimized prompt who is with me!)
def delete_prompt(prompt_id: int):
   try:
      response = supabase.table("prompt").delete().eq("id", prompt_id).execute()
      # if there is data, return it
      # need to figure what to do if there is no data... hmmhmmhmm
      return response.data
   # double check this later to see if this exception is the correct one!
   except Exception as e:
      raise RuntimeError(f"Database error: {str(e)}")

# update prompt/optimized prompt: not sure as a now? i thikn if the user modifies the original prompt. but i think that should just not be able to go thru...
# this can just be an upsert
