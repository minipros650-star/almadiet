"""Health Pydantic schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field


class HealthRecordCreate(BaseModel):
    trimester: int = Field(..., ge=1, le=3)
    week_number: int = Field(..., ge=1, le=42)
    current_weight_kg: float = Field(..., ge=30, le=200)
    bmi: Optional[float] = Field(None, ge=10, le=60)
    blood_pressure_sys: Optional[float] = Field(None, ge=60, le=250)
    blood_pressure_dia: Optional[float] = Field(None, ge=40, le=150)
    hemoglobin: Optional[float] = Field(None, ge=3, le=20)
    blood_sugar_fasting: Optional[float] = Field(None, ge=20, le=600)
    # Free-text accepted; normalized to category codes server-side.
    allergies: Optional[list[str]] = []
    medical_conditions: Optional[list[str]] = []
    dietary_preference: str = Field(default="nonveg", pattern="^(veg|nonveg|eggetarian)$")
    notes: Optional[str] = Field(None, max_length=2000)


class HealthRecordResponse(BaseModel):
    id: UUID
    user_id: UUID
    trimester: int
    week_number: int
    current_weight_kg: float
    bmi: Optional[float] = None
    blood_pressure_sys: Optional[float] = None
    blood_pressure_dia: Optional[float] = None
    hemoglobin: Optional[float] = None
    blood_sugar_fasting: Optional[float] = None
    allergies: Optional[list[str]] = []
    medical_conditions: Optional[list[str]] = []
    is_vegetarian: bool
    dietary_preference: str
    notes: Optional[str] = None
    recorded_at: datetime

    model_config = {"from_attributes": True}


class DiscussionPointsResponse(BaseModel):
    """Informational only — no diagnosis, no corrections."""

    record_id: UUID
    suggestions: list[str]
    disclaimer: str = (
        "These are general reference-range notes, not an interpretation of "
        "your results. Please discuss them with your doctor or midwife."
    )
