from supabase import Client

from schema.validation import ValidationCreate


# return the validations for a specific optimized prompt
def get_optimized_prompt_validations(db: Client, optimized_prompt_id: int) -> list[dict]:
   try:
      response = db.table("validation").select("*").eq("optimized_prompt_id", optimized_prompt_id).execute()
      return response.data
   except Exception as e:
      raise RuntimeError(f"Database error: {str(e)}")


# send a validation to the database (by_alias so "passed" is sent as "pass")
def create_validation(db: Client, validation: ValidationCreate) -> list[dict]:
   try:
      response = db.table("validation").insert(validation.model_dump(mode="json", by_alias=True)).execute()
      return response.data
   except Exception as e:
      raise RuntimeError(f"Database error: {str(e)}")
