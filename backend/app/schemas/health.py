"""
Health Pydantic Schemas — Monthly health data validation.
"""

from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime
from uuid import UUID


class HealthRecordCreate(BaseModel):
    trimester: int = Field(..., ge=1, le=3)
    week_number: int = Field(..., ge=1, le=42)
    current_weight_kg: float = Field(..., ge=30, le=200)
    bmi: Optional[float] = None
    blood_pressure_sys: Optional[float] = Field(None, ge=60, le=250)
    blood_pressure_dia: Optional[float] = Field(None, ge=40, le=150)
    hemoglobin: Optional[float] = Field(None, ge=3, le=20)
    blood_sugar_fasting: Optional[float] = Field(None, ge=30, le=500)
    allergies: Optional[list[str]] = []
    medical_conditions: Optional[list[str]] = []
    is_vegetarian: bool = False
    dietary_preference: str = Field(default="nonveg", pattern="^(veg|nonveg|eggetarian)$")
    notes: Optional[str] = None


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


class HealthAnalysis(BaseModel):
    """Analysis of user's health data with corrections/alerts."""
    bmi_status: str  # underweight | normal | overweight | obese
    bmi_message: str
    weight_gain_status: str  # low | normal | high
    weight_gain_message: str
    bp_status: str  # normal | elevated | high
    bp_message: str
    hemoglobin_status: str  # low | normal | high
    hemoglobin_message: str
    blood_sugar_status: str  # normal | high
    blood_sugar_message: str
    corrections: list[str]  # List of user mistakes to correct
    alerts: list[str]  # Dietary alerts
