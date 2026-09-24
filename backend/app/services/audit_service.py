"""
AlmaDiet — Audit logging service.

Records security- and safety-relevant events with NON-sensitive context only.
"""

from __future__ import annotations

import uuid
import logging
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit_log import AuditLog

logger = logging.getLogger("almadiet.audit")


class EventCodes:
    LOGIN_SUCCESS = "LOGIN_SUCCESS"
    LOGIN_FAILED = "LOGIN_FAILED"
    LOGIN_LOCKOUT = "LOGIN_LOCKOUT"
    REGISTERED = "REGISTERED"
    TOKEN_REFRESHED = "TOKEN_REFRESHED"
    TOKEN_REVOKED = "TOKEN_REVOKED"
    LOGOUT_ALL = "LOGOUT_ALL"
    PROFILE_UPDATED = "PROFILE_UPDATED"
    HEALTH_RECORD_CREATED = "HEALTH_RECORD_CREATED"
    HEALTH_RECORD_DELETED = "HEALTH_RECORD_DELETED"
    PLAN_GENERATED = "PLAN_GENERATED"
    MEAL_SWAPPED = "MEAL_SWAPPED"
    CONSENT_ACCEPTED = "CONSENT_ACCEPTED"
    DATA_EXPORTED = "DATA_EXPORTED"
    ACCOUNT_DELETED = "ACCOUNT_DELETED"
    URGENT_NOTE_CREATED = "URGENT_NOTE_CREATED"
    CONTENT_STATUS_CHANGED = "CONTENT_STATUS_CHANGED"


async def record_event(
    db: AsyncSession,
    event_code: str,
    user_id: uuid.UUID | None = None,
    context: dict[str, Any] | None = None,
) -> None:
    """
    Persist an audit event.

    `context` must contain only non-sensitive operational metadata
    (counts, ids, codes). Health values are prohibited.
    """
    entry = AuditLog(
        user_id=user_id,
        event_code=event_code,
        context=context or {},
    )
    db.add(entry)
    logger.info("audit event=%s user=%s", event_code, user_id)
