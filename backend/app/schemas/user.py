from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.models.enums import UserRole

UserEmail = EmailStr | Literal["admin@careerpilot.local"]


class UserProfileRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    display_name: str | None
    location: str | None
    headline: str | None
    bio: str | None
    target_roles: list[str]
    preferences: dict[str, Any]


class UserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: UserEmail
    role: UserRole
    is_active: bool
    created_at: datetime
    profile: UserProfileRead | None


class UserUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    display_name: str | None = Field(default=None, min_length=1, max_length=100)
    location: str | None = Field(default=None, max_length=120)
    headline: str | None = Field(default=None, max_length=240)
    bio: str | None = Field(default=None, max_length=2000)
    target_roles: list[str] | None = Field(default=None, max_length=20)
    preferences: dict[str, Any] | None = None
