from supabase import Client

from schema.orchestration import OrchestrationCreate, OrchestrationUpdate

# return all of the caller's orchestration runs
def get_user_orchestrations(db: Client) -> list[dict]:
   try:
      response = db.table("orchestration").select("*").execute()
      return response.data
   except Exception as e:
      raise RuntimeError(f"Database error: {str(e)}")

# return one orchestration run
def get_orchestration(db: Client, run_id: int):
   try:
      response = db.table("orchestration").select("*").eq("run_id", run_id).execute()
      return response.data[0] if response.data else None
   except Exception as e:
      raise RuntimeError(f"Database error: {str(e)}")

# return every orchestration run for a specific prompt
def get_prompt_orchestrations(db: Client, prompt_id: int) -> list[dict]:
   try:
      response = db.table("orchestration").select("*").eq("prompt_id", prompt_id).execute()
      return response.data
   except Exception as e:
      raise RuntimeError(f"Database error: {str(e)}")

# send an orchestration run to the db (status defaults to 'pending')
def create_orchestration(db: Client, orchestration: OrchestrationCreate) -> list[dict]:
   try:
      response = db.table("orchestration").insert(orchestration.model_dump(mode="json")).execute()
      return response.data
   except Exception as e:
      raise RuntimeError(f"Database error: {str(e)}")

def update_orchestration(db: Client, run_id: int, orchestration: OrchestrationUpdate) -> list[dict]:
   try:
      response = db.table("orchestration").update(orchestration).eq("run_id", run_id).execute()
      return response.data
   except Exception as e:
      raise RuntimeError(f"Database error: {str(e)}")

def update_orchestration_status(db: Client, run_id: int, status: str) -> list[dict]:
   # prob can put error handling to make sure the status is valid... although it would
   # automatically go to an error bc of the supabase constraint...

   try:
      response = db.table("orchestration").update({"status": status}).eq("run_id", run_id).execute()
      return response.data
   except Exception as e:
      raise RuntimeError(f"Database error: {str(e)}")