import os

### FOR DEVELOPMENT PURPOSES ONLY
import sys
from pathlib import Path
# basically this lets me import from the agents folder outside this folder...
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
### END DEVELOPMENT PURPOSES

import asyncio
import logging

from fastapi import FastAPI, WebSocket
from fastapi.exception_handlers import http_exception_handler
from fastapi.middleware.cors import CORSMiddleware
from starlette.exceptions import HTTPException as StarletteHTTPException
from auth import ALLOWED_ORIGINS
from routes.endpoints import router

logger = logging.getLogger(__name__)

app = FastAPI()


# routes put raw database errors in their 500 details; log those here instead of sending them to the client
@app.exception_handler(StarletteHTTPException)
async def hide_server_error_details(request, exc):
    if exc.status_code >= 500:
        logger.error("%s %s failed: %s", request.method, request.url.path, exc.detail)
        exc = StarletteHTTPException(status_code=exc.status_code, detail="Internal server error")
    return await http_exception_handler(request, exc)


app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
    allow_headers=["Authorization", "Content-Type"],
    allow_credentials=False,
)
app.include_router(router)

# making sure that the api is working :3
@app.get("/")
async def root():
   return {"message": "this is our epic app..."}

# Mock Websockets
@app.websocket("/ws")
async def progress(websocket: WebSocket):
    # CORS
    if websocket.headers.get("origin") not in ALLOWED_ORIGINS:
        await websocket.close(code=1008)
        return
    await websocket.accept()
    for stage in ("auditing", "optimizing", "validating", "done"):
        await websocket.send_json({"stage": stage})
        await asyncio.sleep(1)
    await websocket.close()
