"""User ORM model — hardened."""

import uuid
from datetime import date, datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Float,
    Integer,
    String,
    UniqueConstraint,
    func,
)
from app.database import Base, GUID, JSONType
from sqlalchemy.orm import Mapped, mapped_column, relationship



class User(Base):
    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint("age IS NULL OR (age BETWEEN 14 AND 55)", name="ck_users_age"),
        CheckConstraint("height_cm IS NULL OR (height_cm BETWEEN 100 AND 250)", name="ck_users_height"),
        CheckConstraint(
            "pre_pregnancy_weight_kg IS NULL OR (pre_pregnancy_weight_kg BETWEEN 30 AND 200)",
            name="ck_users_prepreg_weight",
        ),
        CheckConstraint(
            "region IN ('kerala','tamilnadu','karnataka','andhra')",
            name="ck_users_region",
        ),
        CheckConstraint(
            "language IN ('en','ml','ta','kn','te')",
            name="ck_users_language",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    phone: Mapped[str | None] = mapped_column(String(20), nullable=True)
    region: Mapped[str] = mapped_column(String(20), nullable=False, default="kerala")
    language: Mapped[str] = mapped_column(String(5), nullable=False, default="en")
    lmp_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    due_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    age: Mapped[int | None] = mapped_column(Integer, nullable=True)
    height_cm: Mapped[float | None] = mapped_column(Float, nullable=True)
    pre_pregnancy_weight_kg: Mapped[float | None] = mapped_column(Float, nullable=True)

    # ── Server-derived profile fields (never client-supplied) ──
    pre_pregnancy_bmi: Mapped[float | None] = mapped_column(Float, nullable=True)
    gestational_week: Mapped[int | None] = mapped_column(Integer, nullable=True)
    trimester: Mapped[int | None] = mapped_column(Integer, nullable=True)
    profile_complete: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    # ── Suggestion preferences (optional, ranking inputs) ─────
    # declared_allergies: None = "not yet declared" (profile incomplete);
    # [] = user explicitly declared "no known allergies". Distinction is
    # load-bearing for profile completion.
    declared_allergies: Mapped[list | None] = mapped_column(JSONType, nullable=True)
    dietary_preference: Mapped[str | None] = mapped_column(String(20), nullable=True)
    disliked_ingredients: Mapped[list | None] = mapped_column(JSONType, nullable=True, default=list)
    cooking_time_preference: Mapped[str | None] = mapped_column(
        String(20), nullable=True
    )  # quick | moderate | relaxed
    budget_preference: Mapped[str | None] = mapped_column(
        String(20), nullable=True
    )  # low | medium | high

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    health_records = relationship("HealthRecord", back_populates="user", cascade="all, delete-orphan")
    diet_plans = relationship("DietPlan", back_populates="user", cascade="all, delete-orphan")
    urgent_notes = relationship("UrgentHelpNote", back_populates="user", cascade="all, delete-orphan")
    refresh_tokens = relationship("RefreshToken", back_populates="user", cascade="all, delete-orphan")
    consents = relationship("Consent", back_populates="user", cascade="all, delete-orphan")
    favorites = relationship("MealFavorite", cascade="all, delete-orphan")

    def __repr__(self) -> str:  # pragma: no cover
        return f"<User {self.email}>"
