from pydantic import BaseModel, EmailStr, Field


class RegisterRequest(BaseModel):
    email: str = Field(examples=["user@example.com"])
    password: str = Field(min_length=6, examples=["str0ng!Pass"])
    name: str = Field(min_length=1, examples=["John Doe"])


class LoginRequest(BaseModel):
    email: str = Field(examples=["user@example.com"])
    password: str = Field(examples=["str0ng!Pass"])


class RefreshRequest(BaseModel):
    refresh_token: str = Field(examples=["uuid-refresh-token"])


class UserResponse(BaseModel):
    id: str
    email: str
    name: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str
    user: UserResponse


class RefreshResponse(BaseModel):
    access_token: str
    token_type: str
