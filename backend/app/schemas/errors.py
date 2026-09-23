"""AlmaDiet — Canonical API error envelope.

Every non-2xx response from the API uses:
    {"error": {"code": "...", "message": "...", "details": {...}}}
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class ErrorBody(BaseModel):
    code: str
    message: str
    details: dict[str, Any] = {}


class ErrorEnvelope(BaseModel):
    error: ErrorBody


class ErrorCode:
    INVALID_INPUT = "INVALID_INPUT"
    UNAUTHORIZED = "UNAUTHORIZED"
    FORBIDDEN = "FORBIDDEN"
    NOT_FOUND = "NOT_FOUND"
    CONFLICT = "CONFLICT"
    CONSENT_REQUIRED = "CONSENT_REQUIRED"
    LOCKED = "LOCKED"
    RATE_LIMITED = "RATE_LIMITED"
    INTERNAL = "INTERNAL"


def envelope(code: str, message: str, details: dict[str, Any] | None = None) -> dict[str, Any]:
    return ErrorEnvelope(
        error=ErrorBody(code=code, message=message, details=details or {})
    ).model_dump()
