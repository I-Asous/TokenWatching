from fastapi import FastAPI

app = FastAPI()

# making sure that the api is working :3
@app.get("/")
async def root():
   return {"message": "this is our epic app..."}