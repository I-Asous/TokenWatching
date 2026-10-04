from fastapi import FastAPI
from routes.endpoints import router

app = FastAPI()
app.include_router(router)

# making sure that the api is working :3
@app.get("/")
async def root():
   return {"message": "this is our epic app..."}

