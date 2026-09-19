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
