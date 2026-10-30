from supabase import Client

CONTEXT_BUCKET = "context_bucket"

# creates a signed url for the frontend to send the context to
def create_context_upload_url(db: Client, path: str) -> dict:
   try:
      return db.storage.from_(CONTEXT_BUCKET).create_signed_upload_url(path)
   except Exception as e:
      raise RuntimeError(f"Storage error: {str(e)}")

# checks that the file exists
def context_file_exists(db: Client, path: str) -> bool:
   try:
      return db.storage.from_(CONTEXT_BUCKET).exists(path)
   except Exception as e:
      raise RuntimeError(f"Storage error: {str(e)}")
