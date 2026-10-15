# this file is to instantiate the supabase client

import os
from functools import cache

from dotenv import load_dotenv
from supabase import Client, create_client

load_dotenv()


# created on first use, so the app can be imported without supabase config (e.g. in tests)
@cache
def get_supabase() -> Client:
    return create_client(os.environ.get("SUPABASE_URL"), os.environ.get("SUPABASE_KEY"))
