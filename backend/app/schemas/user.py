"""
User Pydantic Schemas — Request/Response validation.
"""

from pydantic import BaseModel, EmailStr, Field
from typing import Optional
from datetime import date, datetime
from uuid import UUID


class UserRegister(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=6, max_length=100)
    name: str = Field(..., min_length=2, max_length=255)
    phone: Optional[str] = None
    region: str = Field(default="kerala", pattern="^(kerala|tamilnadu|karnataka|andhra)$")
    language: str = Field(default="en", pattern="^(en|ml|ta|kn|te)$")
    lmp_date: Optional[date] = None
    age: Optional[int] = Field(None, ge=14, le=55)
    height_cm: Optional[float] = Field(None, ge=100, le=250)
    pre_pregnancy_weight_kg: Optional[float] = Field(None, ge=30, le=200)


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class UserUpdate(BaseModel):
    name: Optional[str] = None
    phone: Optional[str] = None
    region: Optional[str] = None
    language: Optional[str] = None
    lmp_date: Optional[date] = None
    age: Optional[int] = None
    height_cm: Optional[float] = None
    pre_pregnancy_weight_kg: Optional[float] = None


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
    created_at: datetime

    model_config = {"from_attributes": True}


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserResponse
