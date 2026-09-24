"""Diet Pydantic schemas — plan (7-day) and meal responses."""

from __future__ import annotations

from datetime import date, datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field


class IngredientItem(BaseModel):
    name: str
    quantity: Optional[str] = None


class MealResponse(BaseModel):
    id: UUID
    dataset_id: Optional[str] = None
    name: str
    name_tamil: Optional[str] = None
    name_malayalam: Optional[str] = None
    name_kannada: Optional[str] = None
    name_telugu: Optional[str] = None
    region: str
    meal_type: str
    cuisine: Optional[str] = None
    trimester_suitability: Optional[list[str]] = []
    calories: float
    protein_g: float
    carbs_g: float
    fat_g: float
    fiber_g: float
    iron_mg: float
    calcium_mg: float
    folate_mcg: float
    vitamin_c_mg: float = 0
    sodium_mg: float = 0
    sugar_g: float = 0
    ingredients: Optional[list[IngredientItem]] = None
    serving_size: Optional[str] = None
    serving_basis: Optional[str] = None
    preparation_time_minutes: Optional[int] = None
    benefits: Optional[list[str]] = None
    cautions: Optional[str] = None
    food_safety_notes: Optional[str] = None
    substitutions: Optional[list] = None
    best_time_to_eat: Optional[str] = None
    allergens: Optional[list[str]] = []
    image_url: Optional[str] = None
    is_vegetarian: bool
    # Governance provenance (replaces clinically_approved)
    source: Optional[str] = None
    source_url: Optional[str] = None
    evidence_version: Optional[str] = None
    content_status: Optional[str] = None

    model_config = {"from_attributes": True}


class PlanMealCard(BaseModel):
    """Meal card stored inside a plan day (JSONB snapshot)."""

    model_config = {"extra": "allow"}

    id: str
    name: str
    meal_type: Optional[str] = None
    calories: float = 0
    protein_g: float = 0
    allergens: list[str] = []
    why_suggested: list[str] = []
    cross_contact_warning: list[str] = []
    source: Optional[str] = None
    evidence_version: Optional[str] = None
    content_status: Optional[str] = None


class PlanDay(BaseModel):
    day_index: int = Field(..., ge=1, le=7)
    meals: dict[str, list] = {}


class DietPlanResponse(BaseModel):
    id: UUID
    user_id: UUID
    health_record_id: Optional[UUID] = None
    trimester: int
    week_number: int
    days: list[PlanDay] = []
    target_calories: float
    target_protein: float
    target_iron: float
    target_calcium: float
    dietary_alerts: list[str] = []
    exclusions_applied: dict = {}
    user_corrections: list[dict] = []
    plan_start: date
    plan_end: date
    created_at: datetime

    model_config = {"from_attributes": True}
