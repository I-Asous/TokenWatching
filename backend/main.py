from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from auth import ALLOWED_ORIGINS
from routes.endpoints import router

app = FastAPI()
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
