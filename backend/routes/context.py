import os
from typing import Annotated
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException

from auth import UserDB, current_user
from repository import context as context_repository
from repository.client import get_supabase
from repository.storage import create_context_upload_url
from schema.context import Context, ContextCreate, UploadUrlRequest, UploadUrlResponse, UploadUrlsRequest

router = APIRouter()

# can't be more than 10 mb! but it can change
# 10 for 10mb, 1 kb is 2^10 bytes, and 1 mb is 2^10 kb, so 1024 * 1024
MAX_CONTEXT_BYTES = 10 * 1024 * 1024

# return all of a specific users context, or only the context attached to one prompt
@router.get("", response_model=list[Context])
def read_user_contexts(db: UserDB, prompt_id: int | None = None):
    try:
        if prompt_id is None:
            return context_repository.get_user_contexts(db)
        return context_repository.get_user_prompt_contexts(db, prompt_id)
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=f"read_user_contexts: {exc}") from exc


# save context
@router.post("", response_model=list[Context], status_code=201)
def create_context(db: UserDB, context: ContextCreate):
    try:
        return context_repository.create_context(db, context)
    except RuntimeError as exc:
        # 42501 is the postgres error an RLS policy violation raises
        if "42501" in str(exc):
            raise HTTPException(status_code=403, detail="create_context: Not your data") from exc
        raise HTTPException(status_code=500, detail=f"create_context: {exc}") from exc

# TODO: add a rate limit to this
# TODO: add logging to this...
# checks to make sure a file a user wants to upload is valid and creates a signed url for it
@router.post("/upload-urls", response_model=list[UploadUrlResponse])
def create_upload_urls(body: UploadUrlsRequest, user_id: Annotated[str, Depends(current_user)]):
    files_looked_at = []

    for file in body.files:
        # check to make sure that the file is not bigger than it's supposed to be
        if file.size > MAX_CONTEXT_BYTES:
            files_looked_at.append(UploadUrlResponse(filename=file.filename, error="the file is bigger than the max amount of bytes!"))
            continue

        # the filename the user inserts should be in a filename format, so we can just split it!
        root, ext = os.path.splitext(file.filename) 

        # we create the path that the frontend can upload to!
        # users folder, with a random generated id and the extension at the end
        path = f"{user_id}/{uuid4()}{ext}"

        try:
            response = create_context_upload_url(get_supabase(), path)
            files_looked_at.append(UploadUrlResponse(filename=file.filename, path=response["path"], signed_url=response["signed_url"]))

        except RuntimeError as exc:
            files_looked_at.append(UploadUrlResponse(filename=file.filename, error="something went wrong with trying to upload your file, try again."))

    return files_looked_at
