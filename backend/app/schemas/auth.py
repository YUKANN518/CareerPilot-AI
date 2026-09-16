from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.schemas.user import UserEmail, UserRead


class StrictSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")


class RegisterRequest(StrictSchema):
    email: EmailStr
    password: str = Field(min_length=10, max_length=128)
    display_name: str | None = Field(default=None, min_length=1, max_length=100)


class LoginRequest(StrictSchema):
    email: UserEmail
    password: str = Field(min_length=1, max_length=128)


class RefreshRequest(StrictSchema):
    refresh_token: str = Field(min_length=20)


class LogoutRequest(StrictSchema):
    refresh_token: str = Field(min_length=20)


class TokenPair(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int


class AuthSession(BaseModel):
    user: UserRead
    tokens: TokenPair
