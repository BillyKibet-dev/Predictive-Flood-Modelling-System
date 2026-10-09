"""Pydantic request/response schemas for the NairobiFloodWatch API."""
from datetime import datetime

from pydantic import BaseModel, ConfigDict

# ---------------------------------------------------------------- Auth ----

class LoginRequest(BaseModel):
    email: str
    password: str


class UserResponse(BaseModel):
    id: int
    name: str
    email: str
    role: str
    status: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str
    user: UserResponse
