# this file is to instantiate the supabase client

import os
from functools import cache

from dotenv import load_dotenv
from supabase import Client, ClientOptions, create_client

load_dotenv()


# created on first use, so the app can be imported without supabase config (e.g. in tests)
# this is not for actual users...
@cache
def get_supabase() -> Client:
    return create_client(os.environ.get("SUPABASE_URL"), os.environ.get("SUPABASE_KEY"))

## TODO: implement caching?
# this creates a client wiht the user token so we can make sure any action is based on what the user is allowed to do
def get_user_supabase(token: str) -> Client:
    return create_client(
        os.environ.get("SUPABASE_URL"),
        os.environ.get("SUPABASE_PUB_KEY"),
        options=ClientOptions(headers={"Authorization": f"Bearer {token}"}),
    )
