# this file is to instantiate the supabase client

import os
from functools import cache
from pathlib import Path

from dotenv import load_dotenv
from supabase import Client, ClientOptions, create_client

PROJECT_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(PROJECT_ROOT / ".env")


# created on first use, so the app can be imported without supabase config (e.g. in tests)
# this is not for actual users...
@cache
def get_supabase() -> Client:
    return create_client(os.environ.get("SUPABASE_URL"), os.environ.get("SUPABASE_KEY"))

@cache
def get_supabase_admin() -> Client:
    """Return a server-only client for backend operations that need to bypass RLS."""
    service_key = os.environ.get("SUPABASE_SECRET_KEY") or os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
    if not service_key:
        raise RuntimeError("Set SUPABASE_SECRET_KEY or SUPABASE_SERVICE_ROLE_KEY in the project-root .env for guest prompt inserts")
    return create_client(os.environ.get("SUPABASE_URL"), service_key)


## TODO: implement caching?
# this creates a client wiht the user token so we can make sure any action is based on what the user is allowed to do
def get_user_supabase(token: str) -> Client:
    return create_client(
        os.environ.get("SUPABASE_URL"),
        os.environ.get("SUPABASE_PUB_KEY"),
        options=ClientOptions(headers={"Authorization": f"Bearer {token}"}),
    )
