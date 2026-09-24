"""AlmaDiet — Content Governance Router (/api/v1/content-governance).

The reviewer-only surface for the meal content lifecycle:

    REVIEW_REQUIRED --REVIEWER--> REVIEWED --PUBLISHER--> PUBLISHED

Authority is a database grant (``content_role_grants``), resolved for the user
id of the validated session token. Request bodies carry a rationale only: the
models forbid extra fields, so a submitted email, user id or role is rejected
rather than trusted. Every transition is written to ``content_transitions``
with the actor, timestamp, previous and new state, source/version snapshot and
rationale. Seeding never calls these routes.
"""

from __future__ import annotations

import uuid
from typing import Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.content_authz import (
    ContentActor,
    require_meal_publisher,
    require_meal_reviewer,
    require_reviewer,
)
from app.database import get_db
from app.services import content_review_service

router = APIRouter(prefix="/api/v1/content-governance", tags=["Content Governance"])


class ContentActionRequest(BaseModel):
    """Body schema. Actor identity is NEVER taken from here.

    ``extra="forbid"`` makes the guarantee explicit and testable: a client that
    submits ``email``, ``user_id``, ``role`` or any other unexpected field gets
    a 422 instead of having the field silently ignored.
    """

    model_config = ConfigDict(extra="forbid")

    rationale: Optional[str] = Field(None, max_length=1000)


def _meal_payload(meal, **extra) -> dict:
    payload = {
        "meal_id": str(meal.id),
        "name": meal.name,
        "content_status": meal.content_status,
    }
    payload.update(extra)
    return payload


@router.post("/meals/{meal_id}/review", status_code=200)
async def review_meal(
    meal_id: str,
    data: ContentActionRequest,
    actor: ContentActor = Depends(require_meal_reviewer),
    db: AsyncSession = Depends(get_db),
):
    """REVIEW_REQUIRED -> REVIEWED. Requires the REVIEWER role."""
    meal = await content_review_service.review_meal(
        db,
        meal_id=meal_id,
        actor=actor.to_review_actor(),
        rationale=data.rationale,
    )
    return _meal_payload(
        meal,
        reviewed_by=meal.reviewer,
        reviewed_at=meal.reviewed_at.isoformat() if meal.reviewed_at else None,
    )


@router.post("/meals/{meal_id}/publish", status_code=200)
async def publish_meal(
    meal_id: str,
    data: ContentActionRequest,
    actor: ContentActor = Depends(require_meal_publisher),
    db: AsyncSession = Depends(get_db),
):
    """REVIEWED -> PUBLISHED. Requires the PUBLISHER role.

    Also enforces separation of duties: the publisher must not be the reviewer
    who passed the meal (see settings.CONTENT_REQUIRE_SEPARATION_OF_DUTIES).
    """
    meal = await content_review_service.publish_meal(
        db,
        meal_id=meal_id,
        actor=actor.to_review_actor(),
        rationale=data.rationale,
    )
    return _meal_payload(
        meal,
        approved_by=meal.approved_by,
        approved_at=meal.approved_at.isoformat() if meal.approved_at else None,
    )


@router.post("/meals/{meal_id}/retire", status_code=200)
async def retire_meal(
    meal_id: str,
    data: ContentActionRequest,
    actor: ContentActor = Depends(require_reviewer),
    db: AsyncSession = Depends(get_db),
):
    """Withdraw a meal from recommendation (any -> RETIRED)."""
    meal = await content_review_service.retire_meal(
        db,
        meal_id=meal_id,
        actor=actor.to_review_actor(),
        rationale=data.rationale,
    )
    return _meal_payload(meal, retired_at=meal.retired_at.isoformat() if meal.retired_at else None)


@router.get("/meals/pending", status_code=200)
async def list_pending(
    limit: int = Query(50, ge=1, le=200),
    actor: ContentActor = Depends(require_reviewer),
    db: AsyncSession = Depends(get_db),
):
    """Queue of meals awaiting reviewer action (REVIEW_REQUIRED or REVIEWED).

    Restricted to content staff: unreviewed content must not be enumerable by
    ordinary accounts.
    """
    meals = await content_review_service.pending_meals(db, limit=limit)
    return {
        "count": len(meals),
        "meals": [
            {
                "id": str(m.id),
                "name": m.name,
                "content_status": m.content_status,
                "source_url": m.source_url,
                "evidence_version": m.evidence_version,
            }
            for m in meals
        ],
    }


@router.get("/meals/{meal_id}/history", status_code=200)
async def meal_history(
    meal_id: uuid.UUID,
    actor: ContentActor = Depends(require_reviewer),
    db: AsyncSession = Depends(get_db),
):
    """The full decision ledger for one meal: who changed it, when, and why."""
    records = await content_review_service.transitions_for_meal(db, meal_id)
    return {
        "meal_id": str(meal_id),
        "count": len(records),
        "transitions": [
            {
                "actor_id": str(r.actor_id) if r.actor_id else None,
                "actor_label": r.actor_label,
                "actor_role": r.actor_role,
                "from_status": r.from_status,
                "to_status": r.to_status,
                "source_snapshot": r.source_snapshot,
                "evidence_version": r.evidence_version,
                "rationale": r.rationale,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in records
        ],
    }
