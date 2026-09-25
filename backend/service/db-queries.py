# i don't like this file name. lmk what we should change it to

# this is just a separate file to create functions that query/insert/delete from the database
# could i just do this in the api itself? why yes, but if we want this to scale and perhaps change it 
# to another database, then it be annoying to change every single place that calls supabase api
# so we have this solution to be able to change stuff. woohoo!

import os
from supabase import create_client, Client

url: str = os.environ.get("SUPABASE_URL")
key: str = os.environ.get("SUPABASE_KEY")
supabase: Client = create_client(url, key)

### GET METHODS
# we can change this into upsert

## this may seem redundant but i decided to implement all of them, but imo i think if we want to see a prompt, we will def want to see the optimized version alongside it as well :/
# return a specific users original prompts
def get_user_input_prompts(user_id):
   try:
      # query the database
      response = supabase.table("prompt").select("*").eq("user_id", user_id).execute()

      # if there is data, return it
      # need to figure what to do if there is no data... hmmhmmhmm
      return response.data[0]
      
   # double check this later to see if this exception is the correct one!
   except Exception as e:
      raise RuntimeError(f"Database error: {str(e)}")

# return a specific users optimized prompts
def get_user_optimized_prompts(user_id):
   try:
      # query the database
      response = supabase.table("optimized_prompts").select("*").eq("user_id", user_id).execute()

      # if there is data, return it
      # need to figure what to do if there is no data... hmmhmmhmm
      return response.data[0]
      
   # double check this later to see if this exception is the correct one!
   except Exception as e:
      raise RuntimeError(f"Database error: {str(e)}")

# return specific users org prompt+optimized prompt
def get_user_input_and_optimized_prompts(user_id):
   try:
      # query the database
      response = supabase.table("prompt").select("*, optimized_prompts(*)").eq("user_id", user_id).execute()

      # if there is data, return it
      # need to figure what to do if there is no data... hmmhmmhmm
      return response.data[0]
      
   # double check this later to see if this exception is the correct one!
   except Exception as e:
      raise RuntimeError(f"Database error: {str(e)}")
   
# return a specific users 1 prompt + optimized version of it
def get_user_prompt_w_optimized(user_id, prompt_id):
   try:
      # query the database
      response = supabase.table("prompt").select("*, optimized_prompts(*)").eq("user_id", user_id).eq("prompt_id", prompt_id).execute()

      # if there is data, return it
      # need to figure what to do if there is no data... hmmhmmhmm
      return response.data[0]
      
   # double check this later to see if this exception is the correct one!
   except Exception as e:
      raise RuntimeError(f"Database error: {str(e)}")


### POST METHODS

# send a prompt to the database :3
# prompt needs to be properly defined
def create_prompt(prompt):
   try:
      # insert into database
      response = (
         supabase.table("prompt")
         .insert(prompt)
         .execute()
      )
      # if there is data, return it
      # need to figure what to do if there is no data... hmmhmmhmm
      return response.data
      
   # double check this later to see if this exception is the correct one!
   except Exception as e:
      raise RuntimeError(f"Database error: {str(e)}")


# send an optimized prompt to the database :3
def create_optimized_prompt(prompt):
   try:
      # insert into database
      response = (
         supabase.table("optimized_prompts")
         .insert(prompt)
         .execute()
      )
      # if there is data, return it
      # need to figure what to do if there is no data... hmmhmmhmm
      return response.data
      
   # double check this later to see if this exception is the correct one!
   except Exception as e:
      raise RuntimeError(f"Database error: {str(e)}")

### DELETE METHODS
# delete user 
## since enzo is security guy, lets discuss how we should do this bc in a real app they have like secuirty measures to prevent accidental deletion
def delete_user(user_id):
   try:
      # insert into database
      response = (
         supabase.table("users")
         .delete()
         .eq("id", user_id)
         .execute()
      )
      # if there is data, return it
      # need to figure what to do if there is no data... hmmhmmhmm
      return response.data
      
   # double check this later to see if this exception is the correct one!
   except Exception as e:
      raise RuntimeError(f"Database error: {str(e)}")

# delete prompt (which also should delete the optimized prompt who is with me!)
def delete_prompt(prompt_id):
   try:
      # insert into database
      response = (
         supabase.table("users")
         .delete()
         .eq("id", prompt_id)
         .execute()
      )
      # if there is data, return it
      # need to figure what to do if there is no data... hmmhmmhmm
      return response.data
      
   # double check this later to see if this exception is the correct one!
   except Exception as e:
      raise RuntimeError(f"Database error: {str(e)}")

### UPDATE METHOD
# update user: self explanatory... but hoenslty might change this into an upsert
def update_user(user, user_id):
   try:
      # insert into database
      response = (
         supabase.table("users")
         .update(user)
         .eq("id", user_id)
         .execute()
      )
      # if there is data, return it
      # need to figure what to do if there is no data... hmmhmmhmm
      return response.data
      
   # double check this later to see if this exception is the correct one!
   except Exception as e:
      raise RuntimeError(f"Database error: {str(e)}")

# update prompt/optimized prompt: not sure as a now? i thikn if the user modifies the original prompt. but i think that should just not be able to go thru...
# this can just be an upsert
