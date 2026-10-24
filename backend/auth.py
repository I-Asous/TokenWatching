# verifies the clerk session token on every protected request

import os
from typing import Annotated

import jwt
from dotenv import load_dotenv
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from supabase import Client

from repository.client import get_user_supabase

load_dotenv()

# Allowed origins
EXTENSION_ORIGIN = "chrome-extension://imjnnfejbooilgjlllcnkghkckcbmgdn"
extra_origins = [o.strip() for o in os.getenv("CORS_ALLOWED_ORIGINS", "").split(",") if o.strip()]
ALLOWED_ORIGINS = [EXTENSION_ORIGIN, *extra_origins]

# clerk's public signing keys; cached, so verifying a token doesn't hit the network every request
CLERK_JWKS_URL = os.getenv("CLERK_JWKS_URL", "https://united-skylark-6420.clerk.accounts.dev/.well-known/jwks.json")
jwks_client = jwt.PyJWKClient(CLERK_JWKS_URL)

def current_user(creds: Annotated[HTTPAuthorizationCredentials, Depends(HTTPBearer())]) -> str:
    try:
        key = jwks_client.get_signing_key_from_jwt(creds.credentials).key
        payload = jwt.decode(creds.credentials, key, algorithms=["RS256"])
    except jwt.PyJWTError as exc:
        raise HTTPException(status_code=401, detail="Invalid or expired token") from exc
    if payload.get("azp") and payload["azp"] not in ALLOWED_ORIGINS:
        raise HTTPException(status_code=401, detail="Invalid token origin")
    return payload["sub"]

# this makes sure to make a supabase client ONLY with the user's token
# and it lets us inject it into the routes!
def user_db(creds: Annotated[HTTPAuthorizationCredentials, Depends(HTTPBearer())]) -> Client:
    return get_user_supabase(creds.credentials)

# this basically lets us inject it and only write userdb instead of everything else lol
UserDB = Annotated[Client, Depends(user_db)]
