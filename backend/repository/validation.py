from schema.validation import ValidationCreate

from repository.client import supabase


# return the validations for a specific optimized prompt
def get_optimized_prompt_validations(optimized_prompt_id: int) -> list[dict]:
   try:
      response = supabase.table("validation").select("*").eq("optimized_prompt_id", optimized_prompt_id).execute()
      return response.data
   except Exception as e:
      raise RuntimeError(f"Database error: {str(e)}")


# send a validation to the database (by_alias so "passed" is sent as "pass")
def create_validation(validation: ValidationCreate) -> list[dict]:
   try:
      response = supabase.table("validation").insert(validation.model_dump(mode="json", by_alias=True)).execute()
      return response.data
   except Exception as e:
      raise RuntimeError(f"Database error: {str(e)}")
