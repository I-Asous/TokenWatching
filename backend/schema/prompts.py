from datetime import datetime

from pydantic import BaseModel, Field

class Prompt(BaseModel):
    prompt_id: int
    user_id: str
    txt_prompt: str
    target: str
    inputted_at: datetime

class PromptCreate(BaseModel):
    txt_prompt: str = Field(min_length=1)
    target: str

class PromptInsert(PromptCreate):
    user_id: str
