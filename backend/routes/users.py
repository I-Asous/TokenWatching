from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException

from auth import current_user

from repository import users as user_repository
from schema.users import AuthUserResponse, CreateUser, UpdateUser

router = APIRouter()


# create a new user
# i genuinely dont know why i didn't have this before!
@router.post("", response_model=AuthUserResponse, status_code=201)
def create_user(user: CreateUser):
    try:
        return user_repository.create_user(user)
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


# delete a user
@router.delete("")
def delete_user(user_id: Annotated[str, Depends(current_user)]):
    try:
        return user_repository.delete_user(user_id)
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


# user updates information
@router.put("")
def update_user(user_id: Annotated[str, Depends(current_user)], user: UpdateUser):
    try:
        return user_repository.update_user(user, user_id)
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
