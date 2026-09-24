"""AlmaDiet — content review & publication workflow.

This module is the ONLY path by which a meal can become recommendable:

    REVIEW_REQUIRED --REVIEWER--> REVIEWED --PUBLISHER--> PUBLISHED

Rules enforced here (see docs/CONTENT_GOVERNANCE.md):

* Authorisation is data. A role comes from ``content_role_grants``, read for
  the user id derived from the validated session token. Nothing in a request
  body and no environment variable can grant review or publication authority.
* Both gates run the same content blockers (allergen-link completeness,
  nutrition, evidence, clinical claims), so incomplete or unsafe content
  cannot advance. Falling short leaves the meal in the review queue, which is
  the fail-closed direction.
* Every transition is written to ``content_transitions`` with the actor id,
  timestamp, previous state, new state, source/version snapshot and rationale.
* Separation of duties: the publisher must not be the reviewer who passed the
  meal. Production cannot relax this (see settings).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.domain.allergens import allergens_for_ingredients
from app.domain.clinical_claims import find_claim_violations
from app.domain.content_roles import ContentRole, is_content_role
from app.domain.content_state import ContentStatus, transition
from app.models.allergen import Allergen, MealAllergen
from app.models.content_role import ContentRoleGrant
from app.models.content_transition import ContentTransition
from app.models.content_version import ContentVersion
from app.models.meal import Meal
from app.schemas.errors import ErrorCode, envelope
from app.services import audit_service


class Blocker:
    """Machine-readable reasons a content gate refused to advance."""

    ROLE_REQUIRED = "ROLE_REQUIRED"
    INVALID_TRANSITION = "INVALID_TRANSITION"
    CONTENT_NOT_PUBLISHABLE = "CONTENT_NOT_PUBLISHABLE"
    SELF_APPROVAL_FORBIDDEN = "SELF_APPROVAL_FORBIDDEN"
    MISSING_INGREDIENTS = "MISSING_INGREDIENTS"
    MISSING_NUTRITION_DATA = "MISSING_NUTRITION_DATA"
    MISSING_EVIDENCE = "MISSING_EVIDENCE"
    MISSING_ALLERGEN_LINKS = "MISSING_ALLERGEN_LINKS"
    UNSOURCED_CLINICAL_CLAIM = "UNSOURCED_CLINICAL_CLAIM"


@dataclass(frozen=True)
class ReviewActor:
    """An actor whose role has already been verified against the database."""

    user_id: uuid.UUID
    label: str
    role: ContentRole


# ── Error helpers (canonical envelope; detail dicts pass through main.py) ──


def _http(status_code: int, code: str, message: str, details: dict | None = None) -> HTTPException:
    return HTTPException(status_code=status_code, detail=envelope(code, message, details or {}))


def _conflict(blocking_code: str, message: str, **extra) -> HTTPException:
    return _http(
        status.HTTP_409_CONFLICT,
        ErrorCode.CONFLICT,
        message,
        {"blocking_code": blocking_code, **extra},
    )


def _unprocessable(blocking_code: str, message: str, **extra) -> HTTPException:
    return _http(
        status.HTTP_422_UNPROCESSABLE_ENTITY,
        ErrorCode.INVALID_INPUT,
        message,
        {"blocking_code": blocking_code, **extra},
    )


# ── Roles ─────────────────────────────────────────────────────────────────


async def active_roles(db: AsyncSession, user_id: uuid.UUID) -> set[str]:
    """Roles currently granted to a user (revoked grants excluded)."""
    rows = (
        await db.execute(
            select(ContentRoleGrant.role).where(
                ContentRoleGrant.user_id == user_id,
                ContentRoleGrant.revoked_at.is_(None),
            )
        )
    ).scalars().all()
    return set(rows)


async def has_role(db: AsyncSession, user_id: uuid.UUID, role: ContentRole) -> bool:
    return role.value in await active_roles(db, user_id)


async def grant_role(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    role: ContentRole | str,
    granted_by_id: uuid.UUID | None = None,
    granted_by_label: str | None = None,
    note: str | None = None,
) -> ContentRoleGrant:
    """Grant (or re-activate) a content role. Bootstrap/operator use only."""
    role_value = role.value if isinstance(role, ContentRole) else str(role)
    if not is_content_role(role_value):
        raise ValueError(f"Unknown content role: {role_value}")

    existing = (
        await db.execute(
            select(ContentRoleGrant).where(
                ContentRoleGrant.user_id == user_id,
                ContentRoleGrant.role == role_value,
            )
        )
    ).scalar_one_or_none()

    if existing is not None:
        existing.revoked_at = None
        existing.granted_at = datetime.now(timezone.utc)
        existing.granted_by_id = granted_by_id or existing.granted_by_id
        existing.granted_by_label = granted_by_label or existing.granted_by_label
        existing.note = note or existing.note
        await db.flush()
        return existing

    row = ContentRoleGrant(
        user_id=user_id,
        role=role_value,
        granted_by_id=granted_by_id,
        granted_by_label=granted_by_label,
        note=note,
    )
    db.add(row)
    await db.flush()
    return row


async def revoke_role(
    db: AsyncSession, *, user_id: uuid.UUID, role: ContentRole | str
) -> bool:
    """Revoke a role. Returns True if an active grant was revoked."""
    role_value = role.value if isinstance(role, ContentRole) else str(role)
    row = (
        await db.execute(
            select(ContentRoleGrant).where(
                ContentRoleGrant.user_id == user_id,
                ContentRoleGrant.role == role_value,
                ContentRoleGrant.revoked_at.is_(None),
            )
        )
    ).scalar_one_or_none()
    if row is None:
        return False
    row.revoked_at = datetime.now(timezone.utc)
    await db.flush()
    return True


# ── Content gates ─────────────────────────────────────────────────────────


def _detected_allergens(meal: Meal) -> set[str]:
    """Every allergen the safety matcher would detect for this meal.

    Mirrors the import path exactly: ingredient matches plus the meal name.
    The comparison against stored links is what makes the exclusion filter
    trustworthy — a missed link is a meal that can reach an allergic user.
    """
    detected = set(allergens_for_ingredients(meal.ingredients or []))
    detected |= set(allergens_for_ingredients([{"name": meal.name}]))
    return detected


async def _linked_allergen_categories(db: AsyncSession, meal_id: uuid.UUID) -> tuple[set[str], int]:
    """(categories linked, count of dangling link rows).

    A dangling link is a ``meal_allergens`` row whose ``allergen_id`` does
    not resolve to an ``allergens`` row — a data-integrity fault. Duplicate
    links (two ingredient terms matching the same category, which the
    importer legitimately produces) are NOT dangling; counting them so once
    made every such meal un-promotable.
    """
    joined = (
        await db.execute(
            select(Allergen.category)
            .select_from(MealAllergen)
            .join(Allergen, Allergen.id == MealAllergen.allergen_id)
            .where(MealAllergen.meal_id == meal_id)
        )
    ).scalars().all()
    total_links = (
        await db.execute(
            select(func.count())
            .select_from(MealAllergen)
            .where(MealAllergen.meal_id == meal_id)
        )
    ).scalar() or 0
    return set(joined), max(total_links - len(joined), 0)


async def publication_blockers(db: AsyncSession, meal: Meal) -> list[dict]:
    """Everything that must be fixed before content may advance.

    Returns an empty list when the meal is fit to move. An empty list is the
    ONLY way past either gate.
    """
    blockers: list[dict] = []

    if not meal.ingredients:
        blockers.append(
            {"code": Blocker.MISSING_INGREDIENTS, "message": "The meal lists no ingredients."}
        )

    if (meal.calories or 0) <= 0 or not any(
        [(meal.protein_g or 0) > 0, (meal.carbs_g or 0) > 0, (meal.fat_g or 0) > 0]
    ):
        blockers.append(
            {
                "code": Blocker.MISSING_NUTRITION_DATA,
                "message": "Calories and at least one macronutrient must be recorded.",
            }
        )

    has_source = bool(str(meal.source or "").strip() or str(meal.source_url or "").strip())
    if not has_source or not str(meal.evidence_version or "").strip():
        blockers.append(
            {
                "code": Blocker.MISSING_EVIDENCE,
                "message": "A source reference and evidence version are required.",
            }
        )

    detected = _detected_allergens(meal)
    linked, dangling = await _linked_allergen_categories(db, meal.id)
    missing = sorted(detected - linked)
    if missing or dangling:
        blockers.append(
            {
                "code": Blocker.MISSING_ALLERGEN_LINKS,
                "message": "Allergen links do not cover what the safety matcher detects.",
                "missing_categories": missing,
                "dangling_links": dangling,
            }
        )

    violations = find_claim_violations(meal)
    if violations:
        blockers.append(
            {
                "code": Blocker.UNSOURCED_CLINICAL_CLAIM,
                "message": "Unsupported clinical claims remain in patient-visible fields.",
                "violations": violations[:5],
            }
        )

    return blockers


async def _assert_publishable(db: AsyncSession, meal: Meal) -> None:
    blockers = await publication_blockers(db, meal)
    if blockers:
        raise _unprocessable(
            Blocker.CONTENT_NOT_PUBLISHABLE,
            "This meal cannot advance until the listed content problems are fixed.",
            blockers=blockers,
            blocking_codes=[b["code"] for b in blockers],
        )


async def _assert_transition(meal: Meal, target: ContentStatus) -> None:
    try:
        transition(meal.content_status, target)
    except ValueError:
        raise _conflict(
            Blocker.INVALID_TRANSITION,
            f"Illegal content transition: {meal.content_status} -> {target.value}.",
            from_status=meal.content_status,
            to_status=target.value,
        )


async def _assert_separation_of_duties(
    db: AsyncSession, meal: Meal, actor: ReviewActor
) -> None:
    """The publisher must not be the reviewer who passed this meal."""
    if not settings.CONTENT_REQUIRE_SEPARATION_OF_DUTIES:
        return

    last_review = (
        await db.execute(
            select(ContentTransition)
            .where(
                ContentTransition.meal_id == meal.id,
                ContentTransition.to_status == ContentStatus.REVIEWED.value,
            )
            .order_by(ContentTransition.created_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()

    reviewer_id = last_review.actor_id if last_review is not None else None
    reviewer_label = (
        (last_review.actor_label if last_review is not None else None) or meal.reviewer or ""
    )

    same_actor = (reviewer_id is not None and reviewer_id == actor.user_id) or (
        reviewer_id is None
        and bool(reviewer_label)
        and reviewer_label.strip().lower() == actor.label.strip().lower()
    )
    if same_actor:
        raise _conflict(
            Blocker.SELF_APPROVAL_FORBIDDEN,
            "Content must be published by someone other than the reviewer who passed it.",
            reviewer=str(reviewer_label or reviewer_id),
        )


# ── Transition ledger ─────────────────────────────────────────────────────


def _content_version_number(meal: Meal) -> int:
    """Best-effort numeric content version (ContentVersion.version is an int)."""
    raw = str(meal.evidence_version or "1")
    digits = ""
    for char in raw:
        if char.isdigit():
            digits += char
        else:
            break
    return int(digits) if digits else 1


async def _record_transition(
    db: AsyncSession,
    meal: Meal,
    *,
    from_status: str,
    to_status: str,
    actor: ReviewActor,
    rationale: str | None,
) -> ContentTransition:
    """Write the immutable governance record for one state change."""
    record = ContentTransition(
        meal_id=meal.id,
        actor_id=actor.user_id,
        actor_label=actor.label[:255] if actor.label else None,
        actor_role=actor.role.value,
        from_status=from_status,
        to_status=to_status,
        source_snapshot=str(meal.source or meal.source_url or "")[:500] or None,
        evidence_version=str(meal.evidence_version or "")[:32] or None,
        rationale=rationale,
    )
    db.add(record)

    # Keep the pre-existing content_versions trail in step so reviewers using
    # either surface see the same history.
    db.add(
        ContentVersion(
            meal_id=meal.id,
            version=_content_version_number(meal),
            change_note=(rationale or f"{from_status} -> {to_status}")[:500],
            reviewer=(actor.label or str(actor.user_id))[:255],
            status=to_status,
        )
    )

    await audit_service.record_event(
        db,
        audit_service.EventCodes.CONTENT_STATUS_CHANGED,
        actor.user_id,
        {
            "meal_id": str(meal.id),
            "from": from_status,
            "to": to_status,
            "role": actor.role.value,
        },
    )
    await db.flush()
    return record


# ── Workflow operations ───────────────────────────────────────────────────


async def _load_meal(db: AsyncSession, meal_id: uuid.UUID | str) -> Meal:
    try:
        parsed = meal_id if isinstance(meal_id, uuid.UUID) else uuid.UUID(str(meal_id))
    except (ValueError, TypeError):
        raise _http(status.HTTP_404_NOT_FOUND, ErrorCode.NOT_FOUND, "Meal not found.")
    meal = await db.get(Meal, parsed)
    if meal is None:
        raise _http(status.HTTP_404_NOT_FOUND, ErrorCode.NOT_FOUND, "Meal not found.")
    return meal


async def review_meal(
    db: AsyncSession,
    *,
    meal_id: uuid.UUID | str,
    actor: ReviewActor,
    rationale: str | None = None,
) -> Meal:
    """REVIEW_REQUIRED -> REVIEWED. Requires the REVIEWER role."""
    if actor.role is not ContentRole.REVIEWER:
        raise _http(
            status.HTTP_403_FORBIDDEN,
            ErrorCode.FORBIDDEN,
            "Reviewer privileges required.",
            {"blocking_code": Blocker.ROLE_REQUIRED, "required_roles": [ContentRole.REVIEWER.value]},
        )

    meal = await _load_meal(db, meal_id)
    await _assert_transition(meal, ContentStatus.REVIEWED)
    await _assert_publishable(db, meal)

    previous = meal.content_status
    meal.content_status = ContentStatus.REVIEWED.value
    meal.reviewer = (actor.label or str(actor.user_id))[:255]
    meal.reviewed_at = datetime.now(timezone.utc)
    await db.flush()

    await _record_transition(
        db,
        meal,
        from_status=previous,
        to_status=ContentStatus.REVIEWED.value,
        actor=actor,
        rationale=rationale,
    )
    await db.refresh(meal)
    return meal


async def publish_meal(
    db: AsyncSession,
    *,
    meal_id: uuid.UUID | str,
    actor: ReviewActor,
    rationale: str | None = None,
) -> Meal:
    """REVIEWED -> PUBLISHED. Requires the PUBLISHER role."""
    if actor.role is not ContentRole.PUBLISHER:
        raise _http(
            status.HTTP_403_FORBIDDEN,
            ErrorCode.FORBIDDEN,
            "Publisher privileges required.",
            {
                "blocking_code": Blocker.ROLE_REQUIRED,
                "required_roles": [ContentRole.PUBLISHER.value],
            },
        )

    meal = await _load_meal(db, meal_id)
    await _assert_transition(meal, ContentStatus.PUBLISHED)
    await _assert_publishable(db, meal)
    await _assert_separation_of_duties(db, meal, actor)

    previous = meal.content_status
    meal.content_status = ContentStatus.PUBLISHED.value
    meal.approved_by = (actor.label or str(actor.user_id))[:255]
    meal.approved_at = datetime.now(timezone.utc)
    await db.flush()

    await _record_transition(
        db,
        meal,
        from_status=previous,
        to_status=ContentStatus.PUBLISHED.value,
        actor=actor,
        rationale=rationale,
    )
    await db.refresh(meal)
    return meal


async def retire_meal(
    db: AsyncSession,
    *,
    meal_id: uuid.UUID | str,
    actor: ReviewActor,
    rationale: str | None = None,
) -> Meal:
    """Any state -> RETIRED. Withdraws content from every suggestion path."""
    if actor.role not in (ContentRole.PUBLISHER, ContentRole.REVIEWER):
        raise _http(
            status.HTTP_403_FORBIDDEN,
            ErrorCode.FORBIDDEN,
            "Reviewer or publisher privileges required.",
            {"blocking_code": Blocker.ROLE_REQUIRED, "required_roles": ["REVIEWER", "PUBLISHER"]},
        )

    meal = await _load_meal(db, meal_id)
    await _assert_transition(meal, ContentStatus.RETIRED)

    previous = meal.content_status
    meal.content_status = ContentStatus.RETIRED.value
    meal.retired_at = datetime.now(timezone.utc)
    await db.flush()

    await _record_transition(
        db,
        meal,
        from_status=previous,
        to_status=ContentStatus.RETIRED.value,
        actor=actor,
        rationale=rationale,
    )
    await db.refresh(meal)
    return meal


async def pending_meals(db: AsyncSession, limit: int = 50) -> list[Meal]:
    """The reviewer queue: content awaiting review or publication."""
    result = await db.execute(
        select(Meal)
        .where(
            Meal.content_status.in_(
                [ContentStatus.REVIEW_REQUIRED.value, ContentStatus.REVIEWED.value]
            )
        )
        .order_by(Meal.created_at.asc())
        .limit(limit)
    )
    return list(result.scalars().all())


async def transitions_for_meal(db: AsyncSession, meal_id: uuid.UUID) -> list[ContentTransition]:
    """Full, ordered decision history for one meal."""
    result = await db.execute(
        select(ContentTransition)
        .where(ContentTransition.meal_id == meal_id)
        .order_by(ContentTransition.created_at.asc())
    )
    return list(result.scalars().all())
