from fastapi import APIRouter, HTTPException

from repository import users as user_repository
from schema.users import AuthUserResponse, CreateUser, UpdateUser

router = APIRouter()


# create a new user
# i genuinely dont know why i didn't have this before!
@router.post("/users", response_model=AuthUserResponse, status_code=201)
def create_user(user: CreateUser):
    try:
        return user_repository.create_user(user)
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


# delete a user
@router.delete("/users/{user_id}")
def delete_user(user_id: str):
    try:
        return user_repository.delete_user(user_id)
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


# user updates information
@router.put("/users/{user_id}")
def update_user(user_id: str, user: UpdateUser):
    try:
        return user_repository.update_user(user, user_id)
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
