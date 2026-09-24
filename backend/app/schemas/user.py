"""User Pydantic schemas — request/response validation."""

from __future__ import annotations

from datetime import date, datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field, field_validator


class UserRegister(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=8, max_length=128)
    name: str = Field(..., min_length=2, max_length=255)
    phone: Optional[str] = Field(None, pattern=r"^\+?[0-9\s\-]{6,20}$")
    region: str = Field(default="kerala", pattern="^(kerala|tamilnadu|karnataka|andhra)$")
    language: str = Field(default="en", pattern="^(en|ml|ta|kn|te)$")
    lmp_date: Optional[date] = None
    age: Optional[int] = Field(None, ge=14, le=55)
    height_cm: Optional[float] = Field(None, ge=100, le=250)
    pre_pregnancy_weight_kg: Optional[float] = Field(None, ge=30, le=200)

    @field_validator("email")
    @classmethod
    def lower_email(cls, v: str) -> str:
        return v.lower()


class UserLogin(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=1, max_length=128)

    @field_validator("email")
    @classmethod
    def lower_email(cls, v: str) -> str:
        return v.lower()


class UserUpdate(BaseModel):
    """PATCH semantics — only provided fields change. Email and password are
    NOT updatable here (separate verified flows)."""

    model_config = {"extra": "forbid"}

    name: Optional[str] = Field(None, min_length=2, max_length=255)
    phone: Optional[str] = Field(None, pattern=r"^\+?[0-9\s\-]{6,20}$")
    region: Optional[str] = Field(None, pattern="^(kerala|tamilnadu|karnataka|andhra)$")
    language: Optional[str] = Field(None, pattern="^(en|ml|ta|kn|te)$")
    lmp_date: Optional[date] = None
    age: Optional[int] = Field(None, ge=14, le=55)
    height_cm: Optional[float] = Field(None, ge=100, le=250)
    pre_pregnancy_weight_kg: Optional[float] = Field(None, ge=30, le=200)


class UserResponse(BaseModel):
    id: UUID
    email: str
    name: str
    phone: Optional[str] = None
    region: str
    language: str
    lmp_date: Optional[date] = None
    due_date: Optional[date] = None
    age: Optional[int] = None
    height_cm: Optional[float] = None
    pre_pregnancy_weight_kg: Optional[float] = None
    # Server-calculated — never client-supplied (display only).
    pre_pregnancy_bmi: Optional[float] = None
    gestational_week: Optional[int] = None
    trimester: Optional[int] = None
    profile_complete: bool = False
    created_at: datetime

    model_config = {"from_attributes": True}


class TokenPair(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int  # access token lifetime, seconds
    user: UserResponse


class RefreshRequest(BaseModel):
    refresh_token: str = Field(..., min_length=16, max_length=256)


class LogoutRequest(BaseModel):
    refresh_token: str = Field(..., min_length=16, max_length=256)
