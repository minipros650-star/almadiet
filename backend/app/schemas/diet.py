"""
Diet Pydantic Schemas — Diet plan and meal data.
Aligned with meals_dataset.json structure.
"""

from pydantic import BaseModel, Field
from typing import Optional
from datetime import date, datetime
from uuid import UUID


class IngredientItem(BaseModel):
    name: str
    quantity: str


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
    trimester_suitability: Optional[list[str]] = []
    # Nutrition
    calories: float
    protein_g: float
    carbs_g: float
    fat_g: float
    fiber_g: float
    iron_mg: float
    calcium_mg: float
    folate_mcg: float
    vitamin_c_mg: float = 0
    # Ingredients & prep
    ingredients: Optional[list[IngredientItem]] = None
    serving_size: Optional[str] = None
    preparation_time_minutes: Optional[int] = None
    # Clinical
    benefits: Optional[list[str]] = None
    who_alignment: Optional[str] = None
    cautions: Optional[str] = None
    best_time_to_eat: Optional[str] = None
    # Metadata
    allergens: Optional[list[str]] = None
    image_url: Optional[str] = None
    is_vegetarian: bool
    clinically_approved: bool

    model_config = {"from_attributes": True}


class DietPlanResponse(BaseModel):
    id: UUID
    user_id: UUID
    trimester: int
    week_number: int
    breakfast_meals: list[dict] = []
    lunch_meals: list[dict] = []
    dinner_meals: list[dict] = []
    snack_meals: list[dict] = []
    target_calories: float
    target_protein: float
    target_iron: float
    target_calcium: float
    dietary_alerts: list[str] = []
    user_corrections: list[dict] = []
    is_emergency_plan: bool
    plan_start: date
    plan_end: date
    created_at: datetime

    model_config = {"from_attributes": True}


class DietPlanGenerate(BaseModel):
    health_record_id: UUID


class FeedbackSubmit(BaseModel):
    diet_plan_id: UUID
    feedback: str = Field(..., min_length=5, max_length=1000)
    rating: int = Field(..., ge=1, le=5)
