from pydantic import UUID4

from schema.users import AuthUserResponse, CreateUser, UpdateUser

from repository.client import supabase


# create a new user
def create_user(user: CreateUser) -> AuthUserResponse:
   try:
      # NEED TO INCLUDE OTHER INFO (username) LATER!
      response = supabase.auth.sign_up({
         "email": user.email,
         "password": user.hashed_password,
         "options": {"data": {"username": user.username}}
      })
      # if there is data, return it
      # need to figure what to do if there is no data... hmmhmmhmm
      return response.user
   # double check this later to see if this exception is the correct one!
   except Exception as e:
      raise RuntimeError(f"Database error: {str(e)}")


# delete user
## since enzo is security guy, lets discuss how we should do this bc in a real app they have like secuirty measures to prevent accidental deletion
def delete_user(user_id: UUID4):
   try:
      response = supabase.auth.admin.delete_user(str(user_id))
      # if there is data, return it
      # need to figure what to do if there is no data... hmmhmmhmm
      return response
   # double check this later to see if this exception is the correct one!
   except Exception as e:
      raise RuntimeError(f"Database error: {str(e)}")


### UPDATE METHOD
# update user: self explanatory... but hoenslty might change this into an upsert
def update_user(user: UpdateUser, user_id: UUID4):
   try:
      
      response = supabase.auth.admin.update_user_by_id(str(user_id), user.model_dump(exclude_unset=True, exclude_none=True, mode="json"))
      print(response)
      # if there is data, return it
      # need to figure what to do if there is no data... hmmhmmhmm
      return response
   # double check this later to see if this exception is the correct one!
   except Exception as e:
      raise RuntimeError(f"Database error: {str(e)}")


