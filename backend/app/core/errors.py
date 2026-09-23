"""
AlmaDiet — Unified API error envelope.

Every non-2xx response uses:
    {"error": {"code": str, "message": str, "details": dict}}

Stack traces are never returned to clients.
"""

from __future__ import annotations

import logging

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

logger = logging.getLogger("almadiet.errors")


class ErrorCodes:
    INVALID_INPUT = "INVALID_INPUT"
    UNAUTHORIZED = "UNAUTHORIZED"
    FORBIDDEN = "FORBIDDEN"
    NOT_FOUND = "NOT_FOUND"
    CONFLICT = "CONFLICT"
    CONSENT_REQUIRED = "CONSENT_REQUIRED"
    LOCKED = "LOCKED"
    RATE_LIMITED = "RATE_LIMITED"
    SERVICE_UNAVAILABLE = "SERVICE_UNAVAILABLE"
    INTERNAL = "INTERNAL"


def error_response(
    status_code: int,
    code: str,
    message: str,
    details: dict | None = None,
    headers: dict | None = None,
) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={"error": {"code": code, "message": message, "details": details or {}}},
        headers=headers,
    )


class ConsentRequired(Exception):
    """Raised when health data is saved without a current-version consent."""


class LockedOut(Exception):
    """Raised when login attempts exceed the configured threshold."""


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(StarletteHTTPException)
    async def http_exception_handler(request: Request, exc: StarletteHTTPException):
        # Map common statuses to envelope codes.
        mapping = {
            status.HTTP_400_BAD_REQUEST: ErrorCodes.INVALID_INPUT,
            status.HTTP_401_UNAUTHORIZED: ErrorCodes.UNAUTHORIZED,
            status.HTTP_403_FORBIDDEN: ErrorCodes.FORBIDDEN,
            status.HTTP_404_NOT_FOUND: ErrorCodes.NOT_FOUND,
            status.HTTP_409_CONFLICT: ErrorCodes.CONFLICT,
            status.HTTP_422_UNPROCESSABLE_ENTITY: ErrorCodes.INVALID_INPUT,
            status.HTTP_423_LOCKED: ErrorCodes.LOCKED,
            status.HTTP_429_TOO_MANY_REQUESTS: ErrorCodes.RATE_LIMITED,
            status.HTTP_503_SERVICE_UNAVAILABLE: ErrorCodes.SERVICE_UNAVAILABLE,
        }
        code = mapping.get(exc.status_code, ErrorCodes.INTERNAL)
        return error_response(
            exc.status_code,
            code,
            str(exc.detail) if exc.detail else "Request failed.",
            headers=getattr(exc, "headers", None),
        )

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(request: Request, exc: RequestValidationError):
        details = {}
        for err in exc.errors():
            loc = ".".join(str(p) for p in err.get("loc", []) if p != "body")
            details[loc] = err.get("msg", "Invalid value")
        return error_response(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            ErrorCodes.INVALID_INPUT,
            "The submitted information is invalid.",
            details,
        )

    @app.exception_handler(ConsentRequired)
    async def consent_required_handler(request: Request, exc: ConsentRequired):
        return error_response(
            status.HTTP_409_CONFLICT,
            ErrorCodes.CONSENT_REQUIRED,
            "Consent is required before saving health information.",
            {"consent_version": getattr(request.app.state, "consent_version", None)},
        )

    @app.exception_handler(LockedOut)
    async def locked_out_handler(request: Request, exc: LockedOut):
        return error_response(
            status.HTTP_423_LOCKED,
            ErrorCodes.LOCKED,
            "Too many failed attempts. Try again later.",
        )

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception):
        # Log server-side with stack; NEVER leak details to the client.
        logger.exception("Unhandled error on %s %s", request.method, request.url.path)
        return error_response(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            ErrorCodes.INTERNAL,
            "An unexpected error occurred. Please try again.",
        )
