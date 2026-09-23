"""AlmaDiet — FastAPI application entry point (hardened)."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from app.config import ConfigError, settings
from app.core.logging_setup import configure_logging
from app.schemas.errors import ErrorCode, envelope

configure_logging(debug=settings.DEBUG)
logger = logging.getLogger("almadiet")

app_version = "2.0.0"


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting AlmaDiet backend (environment=%s, auth=%s)", settings.ENVIRONMENT, settings.AUTH_MODE)

    # Schema is ALWAYS owned by Alembic in deployed environments. Only an
    # explicit local development run (ENVIRONMENT=development) may create a
    # scratch schema and seed an empty catalog — serverless (Vercel) and
    # production never do. Migration/seeding are controlled commands:
    #   python -m scripts.migrate && python -m scripts.seed_meals
    if settings.ENVIRONMENT == "development":
        from app.database import create_tables
        await create_tables()
        logger.info("Dev schema ensured (create_tables)")

        # Dev convenience seeding (empty database only).
        from app.database import async_session_maker
        from app.services.meal_service import get_meal_count, seed_meals
        async with async_session_maker() as db:
            count = await get_meal_count(db)
            if count == 0:
                try:
                    seeded = await seed_meals(db)
                    await db.commit()
                    logger.info("Seeded %d meals (REVIEW_REQUIRED)", seeded)
                except FileNotFoundError as e:
                    logger.warning("Meal dataset missing: %s", e)
            else:
                logger.info("%d meals already present", count)

    yield

    from app.database import close_engine
    await close_engine()
    logger.info("AlmaDiet backend shut down")


app = FastAPI(
    title="AlmaDiet API",
    description=(
        "Evidence-informed pregnancy nutrition support. NOT a medical device: "
        "no diagnosis, no treatment, no emergency functionality."
    ),
    version=app_version,
    lifespan=lifespan,
    docs_url="/docs" if not settings.IS_PRODUCTION else None,
    redoc_url=None,
)

# ── CORS (allowlist; wildcard rejected in production by config) ──────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS or ["*"] if not settings.IS_PRODUCTION else settings.ALLOWED_ORIGINS,
    allow_credentials=bool(settings.ALLOWED_ORIGINS),
    allow_methods=["GET", "POST", "PATCH", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
    max_age=600,
)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        response.headers.setdefault("Cache-Control", "no-store")
        return response


app.add_middleware(SecurityHeadersMiddleware)

# ── Uniform error envelope ────────────────────────────────────────────────


# Human-readable wording for the most common physiological-bound violations.
# Pydantic messages stay authoritative for anything not listed here.
_VALIDATION_FIELD_LABELS = {
    "trimester": "Pregnancy trimester",
    "week_number": "Pregnancy week",
    "current_weight_kg": "Weight",
    "bmi": "BMI",
    "blood_pressure_sys": "Systolic blood pressure",
    "blood_pressure_dia": "Diastolic blood pressure",
    "hemoglobin": "Hemoglobin",
    "blood_sugar_fasting": "Fasting blood sugar",
    "allergies": "Allergies",
    "medical_conditions": "Medical conditions",
    "dietary_preference": "Dietary preference",
    "notes": "Notes",
}


def _friendly_validation_msg(err: dict) -> str:
    msg = str(err.get("msg", "invalid"))
    ctx = err.get("ctx") or {}
    lower, upper = ctx.get("ge", ctx.get("gt")), ctx.get("le", ctx.get("lt"))
    if lower is not None and upper is not None:
        return f"must be between {lower} and {upper}."
    if lower is not None:
        return f"must be at least {lower}."
    if upper is not None:
        return f"must be at most {upper}."
    if "unable to parse" in msg.lower():
        return "is not a valid number."
    return msg + ("" if msg.endswith(".") else ".")


@app.exception_handler(RequestValidationError)
async def validation_error_handler(request: Request, exc: RequestValidationError):
    details = {}
    for err in exc.errors():
        field = ".".join(str(p) for p in err.get("loc", [])[1:]) or "body"
        label = _VALIDATION_FIELD_LABELS.get(field, field.replace("_", " ").capitalize())
        details.setdefault(field, f"{label} {_friendly_validation_msg(err)}")
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content=envelope(ErrorCode.INVALID_INPUT, "The submitted information is invalid.", details),
    )


@app.exception_handler(HTTPException)
async def http_error_handler(request: Request, exc: HTTPException):
    # detail may already be an envelope dict from routers
    if isinstance(exc.detail, dict) and "error" in exc.detail:
        return JSONResponse(status_code=exc.status_code, content=exc.detail)
    code_map = {
        status.HTTP_401_UNAUTHORIZED: ErrorCode.UNAUTHORIZED,
        status.HTTP_403_FORBIDDEN: ErrorCode.FORBIDDEN,
        status.HTTP_404_NOT_FOUND: ErrorCode.NOT_FOUND,
        status.HTTP_409_CONFLICT: ErrorCode.CONFLICT,
        status.HTTP_423_LOCKED: ErrorCode.LOCKED,
        status.HTTP_429_TOO_MANY_REQUESTS: ErrorCode.RATE_LIMITED,
    }
    code = code_map.get(exc.status_code, ErrorCode.INTERNAL)
    return JSONResponse(
        status_code=exc.status_code,
        content=envelope(code, str(exc.detail)),
        headers=exc.headers or {},
    )


@app.exception_handler(Exception)
async def unhandled_error_handler(request: Request, exc: Exception):
    logger.exception("Unhandled error on %s %s", request.method, request.url.path)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content=envelope(ErrorCode.INTERNAL, "Something went wrong. Please try again."),
    )


# ── Routers (v1) ──────────────────────────────────────────────────────────
from app.routers.auth_router import router as auth_router
from app.routers.consent_router import router as consent_router
from app.routers.health_router import router as health_router
from app.routers.diet_router import router as diet_router
from app.routers.meal_router import router as meal_router
from app.routers.urgent_router import router as urgent_router
from app.routers.privacy_router import router as privacy_router
from app.routers.files_router import router as files_router
from app.routers.profile_router import router as profile_router
from app.routers.content_governance_router import router as content_governance_router
from app.routers.evidence_router import router as evidence_router
from app.routers.governance_router import router as governance_router

app.include_router(auth_router)
app.include_router(consent_router)
app.include_router(health_router)
app.include_router(diet_router)
app.include_router(meal_router)
app.include_router(urgent_router)
app.include_router(privacy_router)
app.include_router(profile_router)
app.include_router(files_router)
app.include_router(content_governance_router)
app.include_router(evidence_router)
app.include_router(governance_router)


@app.get("/", tags=["Root"])
async def root():
    return {
        "app": "AlmaDiet",
        "version": app_version,
        "boundary": "nutrition-support information only — not a medical device",
        "status": "running",
    }


@app.get("/healthz", tags=["Root"])
async def healthz():
    return {"status": "ok"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host=settings.HOST, port=settings.PORT, reload=settings.DEBUG)
