"""Test fixtures — async SQLite in-memory database + httpx ASGI client."""

from __future__ import annotations

import asyncio
import os

os.environ.setdefault("ENVIRONMENT", "development")
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

import app.database as database_module


@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture
async def db_engine():
    engine = create_async_engine("sqlite+aiosqlite://", echo=False)
    import app.models  # noqa: F401 — register models

    async with engine.begin() as conn:
        from app.database import Base

        await conn.run_sync(Base.metadata.create_all)

    # Point the app at this engine. get_db() reads async_session_maker from
    # the module at call time, so patching the attribute (without reload)
    # redirects every request to this test engine.
    database_module.engine = engine
    database_module.async_session_maker = async_sessionmaker(
        engine, class_=database_module.AsyncSession, expire_on_commit=False
    )
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture
async def db_session(db_engine):
    maker = async_sessionmaker(db_engine, class_=database_module.AsyncSession, expire_on_commit=False)
    async with maker() as session:
        yield session


@pytest_asyncio.fixture
async def client(db_engine):
    # Import main once per session; its get_db dependency resolves the
    # (patched) sessionmaker at request time, so no reload is needed.
    import main

    transport = ASGITransport(app=main.app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest_asyncio.fixture
async def seeded_db(db_engine):
    """Database with allergen rows + a few meals (published + pending)."""
    maker = async_sessionmaker(db_engine, class_=database_module.AsyncSession, expire_on_commit=False)
    async with maker() as session:
        from app.models.allergen import Allergen
        from app.domain.allergens import DISPLAY_NAMES, AllergenCategory

        for cat in AllergenCategory:
            session.add(
                Allergen(category=cat.value, display_name=DISPLAY_NAMES[cat.value])
            )
        await session.commit()
    yield db_engine


@pytest_asyncio.fixture
async def active_policy(db_engine):
    """An ACTIVE, clinician-approved SafetyPolicyVersion.

    Mirrors the production deployment gate: personalized generation runs
    only when a reviewer-activated policy exists. Tests that exercise the
    happy path use this; governance tests exercise the gate itself.
    """
    maker = async_sessionmaker(db_engine, class_=database_module.AsyncSession, expire_on_commit=False)
    async with maker() as session:
        from datetime import datetime, timezone

        from app.models.evidence import SafetyPolicyVersion

        policy = SafetyPolicyVersion(
            policy_id="maternal_nutrition_policy",
            version="1.0.0-test",
            payload={
                "approved_content_statuses": ["PUBLISHED"],
                "approved_allergen_mappings": "taxonomy",
                "approved_food_safety_tags": ["raw_mercury_fish", "unpasteurized_dairy"],
                "restriction_logic": "exclude_declared_allergens_and_unsafe_tags",
                "clinician_review_required": [
                    "diabetes", "hypertension", "kidney_disease",
                ],
            },
            status="DRAFT",
        )
        session.add(policy)
        await session.commit()
        # Activate = the clinician approval action (as governance router does).
        policy.status = "ACTIVE"
        policy.approved_by = "clinician@example.com"
        policy.approved_at = datetime.now(timezone.utc)
        await session.commit()
        policy_id = str(policy.id)
    yield policy_id


@pytest.fixture(autouse=True)
def _reset_rate_limits():
    """Rate-limit/lockout state must not leak between tests (shared IP)."""
    from app.core import rate_limit as rl
    from app.services import user_service as us

    rl.login_rate_limiter._events.clear()
    rl.register_rate_limiter._events.clear()
    us.login_lockout._failures.clear()
    us.login_lockout._locked_until.clear()
    yield
    rl.login_rate_limiter._events.clear()
    rl.register_rate_limiter._events.clear()
    us.login_lockout._failures.clear()
    us.login_lockout._locked_until.clear()


def make_meal(**overrides):
    """Factory for Meal rows used across suites."""
    from app.models.meal import Meal
    from app.domain.content_state import ContentStatus

    base = dict(
        name="Test Meal",
        region="Kerala",
        meal_type="Breakfast",
        trimester_suitability=["First", "Second", "Third"],
        calories=200,
        protein_g=6,
        carbs_g=30,
        fat_g=5,
        fiber_g=3,
        iron_mg=2,
        calcium_mg=80,
        folate_mcg=40,
        vitamin_c_mg=5,
        sodium_mg=120,
        sugar_g=3,
        ingredients=[{"name": "Rice", "quantity": "1 cup"}],
        is_vegetarian=True,
        content_status=ContentStatus.REVIEWED.value,
        source="Test source",
        evidence_version="1",
    )
    base.update(overrides)
    return Meal(**base)


async def register_and_login(client, email="user1@test.com", password="Password123"):
    resp = await client.post(
        "/api/v1/auth/register",
        json={
            "email": email,
            "password": password,
            "name": "Test User",
            "region": "kerala",
            "language": "en",
        },
    )
    if resp.status_code == 409:
        resp = await client.post(
            "/api/v1/auth/login", json={"email": email, "password": password}
        )
    body = resp.json()
    return body["access_token"], body["refresh_token"], body["user"]["id"]
