from datetime import datetime

from pydantic import BaseModel, Field

class Prompt(BaseModel):
    prompt_id: int
    user_id: str
    txt_prompt: str
    inputted_at: datetime

class PromptCreate(BaseModel):
    user_id: str
    txt_prompt: str = Field(min_length=1)


class GuestPromptCreate(BaseModel):
    txt_prompt: str = Field(min_length=1)
