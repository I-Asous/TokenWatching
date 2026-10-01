# do we really need to import this 3 times in 3 separate file :/
from pydantic import BaseModel, Field
from datetime import datetime


class OptimizedPrompt(BaseModel):
    optimized_prompt_id: int
    user_id: int # see if there is a way to make this validate
    org_prompt_id: int
    txt_prompt: str
    tokens: int = Field(ge=0)
    inputted_at: datetime

class OptimizedPromptCreate(BaseModel):
    user_id: int
    org_prompt_id: int
    txt_prompt: str # = Field(min_length=1)
    tokens: int = Field(ge=0)

