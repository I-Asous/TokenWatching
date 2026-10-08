from datetime import datetime

from pydantic import BaseModel, EmailStr, Field, model_validator

class User(BaseModel):
    user_id: str
    username: str
    email: EmailStr
    hashed_password: str
    created_at: datetime
    updated_at: datetime

class AuthUserResponse(BaseModel):
    id: str
    email: EmailStr
    created_at: datetime
    updated_at: datetime
    user_metadata: dict = Field(default_factory=dict)

class CreateUser(BaseModel):
    username: str = Field(min_length=1, max_length=100)
    email: EmailStr
    # min length can change later o_o
    password: str = Field(min_length=7)


class UpdateUser(BaseModel):
    username: str | None = Field(default=None, min_length=1, max_length=100)
    email: EmailStr | None = None
    password: str | None = Field(default=None, min_length=7)

    @model_validator(mode="after")
    def require_update_field(self):
        if not any(getattr(self, field) is not None for field in self.model_fields_set):
            raise ValueError("At least one user field must be provided")
        return self