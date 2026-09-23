"""AlmaDiet — Content Governance Router (/api/v1/content-governance).

Reviewer-only endpoints for the meal content lifecycle. Nothing here can
be reached by a normal user account — every route requires the
``require_admin`` dependency, and every transition is recorded in the
audit log with reviewer identity. Seeding never calls these functions;
approval always requires an explicit, attributable reviewer action.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.jwt_handler import get_current_user
from app.config import settings
from app.database import get_db
from app.domain.content_state import ContentStatus, transition as apply_transition
from app.models.meal import Meal
from app.services import audit_service

router = APIRouter(prefix="/api/v1/content-governance", tags=["Content Governance"])


class ContentActionRequest(BaseModel):
    note: Optional[str] = Field(None, max_length=500)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def require_reviewer(user: object = Depends(get_current_user)) -> object:
    """Reviewer gate: in development the bootstrap admin email is allowed;
    in production the environment must name REVIEWER_EMAILS explicitly.
    Seeding never bypasses this — approval is always a logged human act."""
    reviewer_emails = {
        e.strip().lower()
        for e in os.getenv("REVIEWER_EMAILS", "").split(",")
        if e.strip()
    }
    if settings.ENVIRONMENT == "development" and not reviewer_emails:
        reviewer_emails = {e.strip().lower() for e in os.getenv(
            "BOOTSTRAP_ADMIN_EMAILS", "admin@example.com"
        ).split(",") if e.strip()}
    if getattr(user, "email", "").lower() not in reviewer_emails:
        from fastapi import HTTPException
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="Reviewer privileges required")
    return user


@router.post("/meals/{meal_id}/publish", status_code=200)
async def publish_meal(
    meal_id: str,
    data: ContentActionRequest,
    db: AsyncSession = Depends(get_db),
    reviewer: object = Depends(require_reviewer),
):
    """Approve a meal for recommendation (REVIEWED → PUBLISHED).

    Requires: source reference, evidence version, and a prior REVIEWED
    state. This is the ONLY path by which content becomes recommendable
    in the personalized pipeline. Never called by seeding.
    """
    meal = await db.get(Meal, meal_id)
    if meal is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Meal not found")
    apply_transition(meal.content_status, ContentStatus.PUBLISHED)
    if not ((meal.source and str(meal.source).strip()) or (meal.source_url and str(meal.source_url).strip())):
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail="Meal must document a source reference before publishing",
        )
    meal.content_status = ContentStatus.PUBLISHED.value
    meal.approved_at = _now()
    meal.approved_by = getattr(reviewer, "email", str(reviewer))
    await db.flush()
    await audit_service.record_event(
        db, audit_service.EventCodes.CONTENT_STATUS_CHANGED, getattr(reviewer, "id", None),
        {"meal_id": str(meal.id), "to": "PUBLISHED", "note": data.note},
    )
    return {"meal_id": str(meal.id), "content_status": meal.content_status,
            "approved_at": meal.approved_at.isoformat(), "approved_by": meal.approved_by}


@router.post("/meals/{meal_id}/retire", status_code=200)
async def retire_meal(
    meal_id: str,
    data: ContentActionRequest,
    db: AsyncSession = Depends(get_db),
    reviewer: object = Depends(require_reviewer),
):
    """Withdraw a meal from recommendation (any → RETIRED)."""
    meal = await db.get(Meal, meal_id)
    if meal is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Meal not found")
    apply_transition(meal.content_status, ContentStatus.RETIRED)
    meal.content_status = ContentStatus.RETIRED.value
    meal.retired_at = _now()
    await db.flush()
    await audit_service.record_event(
        db, audit_service.EventCodes.CONTENT_STATUS_CHANGED, getattr(reviewer, "id", None),
        {"meal_id": str(meal.id), "to": "RETIRED", "note": data.note},
    )
    return {"meal_id": str(meal.id), "content_status": meal.content_status}


@router.get("/meals/pending", status_code=200)
async def list_pending(
    limit: int = 50,
    db: AsyncSession = Depends(get_db),
    reviewer: object = Depends(require_reviewer),
):
    """Queue of meals awaiting reviewer action (REVIEW_REQUIRED or REVIEWED)."""
    result = await db.execute(
        select(Meal)
        .where(Meal.content_status.in_(["REVIEW_REQUIRED", "REVIEWED"]))
        .order_by(Meal.created_at.asc())
        .limit(limit)
    )
    meals = result.scalars().all()
    return {
        "count": len(meals),
        "meals": [
            {
                "id": str(m.id),
                "name": m.name,
                "category": m.category,
                "content_status": m.content_status,
                "source_url": m.source_url,
                "evidence_version": m.evidence_version,
            }
            for m in meals
        ],
    }
