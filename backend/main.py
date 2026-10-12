from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from routes.endpoints import router

app = FastAPI()


app.add_middleware(
   CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "chrome-extension://imjnnfejbooilgjlllcnkghkckcbmgdn",
    ],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)

# making sure that the api is working :3
@app.get("/")
async def root():
   return {"message": "this is our epic app..."}
