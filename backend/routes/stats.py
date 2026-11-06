
from fastapi import APIRouter, HTTPException

from auth import UserDB

router = APIRouter()

@router.get("/stats")
def get_stats(db: UserDB, timeframe: str): # import user db to just get the users stuff...
    try:
        return db.rpc("get_user_stats", {"timeframe": timeframe}).execute().data
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")

    


