"""
AlmaDiet — Emergency Service
Handles emergency case reporting, modified diets, and resolution.
"""

import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.emergency import EmergencyRecord
from app.schemas.emergency import EmergencyCreate


# ── Emergency diet restriction mappings ──────────────────────────
EMERGENCY_DIET_MAPS = {
    "GDM": {
        "restrictions": {
            "avoid": ["white rice", "white bread", "maida", "sugary drinks", "sweets", "jaggery excess"],
            "limit": ["potato", "banana", "mango", "white pasta"],
            "prefer": ["brown rice", "ragi", "oats", "millets", "green vegetables", "dal"],
        },
        "calorie_adjustment": -200,
        "notes": "Gestational Diabetes: Split meals into 6 small portions. Monitor blood sugar after each meal.",
    },
    "preeclampsia": {
        "restrictions": {
            "avoid": ["pickles", "pappadam", "salted snacks", "processed food", "canned food"],
            "limit": ["salt", "soy sauce", "cheese"],
            "prefer": ["banana", "coconut water", "spinach", "beetroot", "garlic"],
        },
        "calorie_adjustment": 0,
        "notes": "Preeclampsia: Reduce sodium to <2g/day. Increase potassium-rich foods. Monitor BP daily.",
    },
    "anemia": {
        "restrictions": {
            "avoid": ["tea with meals", "coffee with meals", "calcium supplements with iron"],
            "limit": ["dairy during iron-rich meals"],
            "prefer": ["beetroot", "spinach", "moringa", "dates", "jaggery", "liver", "ragi", "vitamin C foods"],
        },
        "calorie_adjustment": 100,
        "notes": "Anemia: Take iron supplements on empty stomach with vitamin C. Avoid tea/coffee 1hr before/after meals.",
    },
    "hyperemesis": {
        "restrictions": {
            "avoid": ["spicy food", "oily food", "strong-smelling food"],
            "limit": ["large meals"],
            "prefer": ["ginger tea", "crackers", "cold foods", "lemon water", "small frequent meals", "coconut water"],
        },
        "calorie_adjustment": -100,
        "notes": "Severe nausea/vomiting: Eat before feeling hungry. Cold meals tolerated better. Stay hydrated.",
    },
    "bleeding": {
        "restrictions": {
            "avoid": ["heavy exercise", "lifting", "papaya", "pineapple"],
            "limit": ["spicy food"],
            "prefer": ["iron-rich foods", "rest", "hydration", "vitamin C fruits"],
        },
        "calorie_adjustment": 0,
        "notes": "Bleeding: Strict bed rest recommended. Consult doctor IMMEDIATELY. Maintain iron-rich diet.",
    },
    "preterm_risk": {
        "restrictions": {
            "avoid": ["papaya", "pineapple", "excess caffeine", "raw sprouts"],
            "limit": ["physical strain", "standing for long"],
            "prefer": ["omega-3 foods", "calcium-rich foods", "adequate hydration", "protein-rich meals"],
        },
        "calorie_adjustment": 100,
        "notes": "Preterm risk: Adequate rest essential. Increase protein and DHA intake. Hydrate well.",
    },
}


async def report_emergency(
    db: AsyncSession, user_id: uuid.UUID, data: EmergencyCreate
) -> EmergencyRecord:
    """Report an emergency and auto-generate modified diet restrictions."""
    emergency_type = data.emergency_type.upper() if data.emergency_type else ""
    diet_map = EMERGENCY_DIET_MAPS.get(
        data.emergency_type, EMERGENCY_DIET_MAPS.get(emergency_type, {})
    )

    record = EmergencyRecord(
        user_id=user_id,
        emergency_type=data.emergency_type,
        description=data.description,
        modified_diet_restrictions=diet_map.get("restrictions"),
        emergency_meals=diet_map,
        is_active=True,
    )
    db.add(record)
    await db.flush()
    await db.refresh(record)
    return record


async def get_emergencies(
    db: AsyncSession, user_id: uuid.UUID, active_only: bool = False
) -> list[EmergencyRecord]:
    """Get all emergencies for a user."""
    query = select(EmergencyRecord).where(
        EmergencyRecord.user_id == user_id
    )
    if active_only:
        query = query.where(EmergencyRecord.is_active == True)
    query = query.order_by(EmergencyRecord.created_at.desc())
    result = await db.execute(query)
    return list(result.scalars().all())


async def resolve_emergency(
    db: AsyncSession, user_id: uuid.UUID, emergency_id: uuid.UUID
) -> Optional[EmergencyRecord]:
    """Mark an emergency as resolved."""
    result = await db.execute(
        select(EmergencyRecord).where(
            EmergencyRecord.id == emergency_id,
            EmergencyRecord.user_id == user_id,
        )
    )
    record = result.scalar_one_or_none()
    if record is None:
        return None

    record.is_active = False
    record.resolved_at = datetime.now(timezone.utc)
    await db.flush()
    await db.refresh(record)
    return record
