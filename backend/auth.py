# verifies the clerk session token on every protected request

import os
from typing import Annotated

import jwt
from dotenv import load_dotenv
from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

load_dotenv()

# Allowed origins
EXTENSION_ORIGIN = "chrome-extension://imjnnfejbooilgjlllcnkghkckcbmgdn"
extra_origins = [o.strip() for o in os.getenv("CORS_ALLOWED_ORIGINS", "").split(",") if o.strip()]
ALLOWED_ORIGINS = [EXTENSION_ORIGIN, *extra_origins]

# clerk's public signing keys; cached, so verifying a token doesn't hit the network every request
CLERK_JWKS_URL = os.getenv("CLERK_JWKS_URL", "https://united-skylark-6420.clerk.accounts.dev/.well-known/jwks.json")
jwks_client = jwt.PyJWKClient(CLERK_JWKS_URL)


def current_user(request: Request, creds: Annotated[HTTPAuthorizationCredentials, Depends(HTTPBearer())]) -> str:
    try:
        key = jwks_client.get_signing_key_from_jwt(creds.credentials).key
        payload = jwt.decode(creds.credentials, key, algorithms=["RS256"])
    except jwt.PyJWTError as exc:
        raise HTTPException(status_code=401, detail="Invalid or expired token") from exc
    if payload.get("azp") and payload["azp"] not in ALLOWED_ORIGINS:
        raise HTTPException(status_code=401, detail="Invalid token origin")
    # a user can only access routes for their own user_id
    if request.path_params.get("user_id", payload["sub"]) != payload["sub"]:
        raise HTTPException(status_code=403, detail="Not your data")
    return payload["sub"]
