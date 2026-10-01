from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field, model_validator

class User(BaseModel):
    user_id: int
    username: str
    email: EmailStr
    hashed_password: str
    created_at: datetime
    updated_at: datetime


class UserCreate(BaseModel):
    username: str = Field(min_length=1, max_length=100)
    email: EmailStr
    hashed_password: str = Field(min_length=1)


class UserUpdate(BaseModel):
    username: str | None = Field(default=None, min_length=1, max_length=100)
    email: EmailStr | None = None
    hashed_password: str | None = Field(default=None, min_length=1)

    @model_validator(mode="after")
    def require_update_field(self):
        if not any(getattr(self, field) is not None for field in self.model_fields_set):
            raise ValueError("At least one user field must be provided")
        return self



