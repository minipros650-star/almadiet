"""
Emergency Pydantic Schemas — Emergency reporting and response.
"""

from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime
from uuid import UUID


class EmergencyCreate(BaseModel):
    emergency_type: str = Field(
        ...,
        description="Type: GDM, preeclampsia, anemia, bleeding, hyperemesis, infection, preterm_risk"
    )
    description: Optional[str] = None


class EmergencyResponse(BaseModel):
    id: UUID
    user_id: UUID
    emergency_type: str
    description: Optional[str] = None
    modified_diet_restrictions: Optional[dict] = None
    emergency_meals: Optional[dict] = None
    is_active: bool
    created_at: datetime
    resolved_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class EmergencyResolve(BaseModel):
    emergency_id: UUID
