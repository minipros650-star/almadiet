"""
AlmaDiet — Application Configuration
Loads environment variables for database, API keys, and JWT settings.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# Load .env file from backend root
env_path = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(dotenv_path=env_path)


class Settings:
    """Application settings loaded from environment variables."""

    # ── Database ──────────────────────────────────────────────
    DATABASE_URL: str = os.getenv(
        "DATABASE_URL",
        "postgresql+asyncpg://postgres:postgres@localhost:5432/almadiet"
    )

    # ── JWT Authentication ────────────────────────────────────
    JWT_SECRET_KEY: str = os.getenv("JWT_SECRET_KEY", "almadiet-super-secret-key-change-in-production")
    JWT_ALGORITHM: str = "HS256"
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 7  # 7 days

    # ── Google Gemini API ─────────────────────────────────────
    GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "")
    GEMINI_MODEL: str = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")

    # ── ML Model Paths ────────────────────────────────────────
    ML_MODEL_PATH: str = str(Path(__file__).resolve().parent / "ml" / "model.pkl")
    ML_PREPROCESSOR_PATH: str = str(Path(__file__).resolve().parent / "ml" / "preprocessor.pkl")

    # ── Meal Dataset ──────────────────────────────────────────
    MEALS_DATASET_PATH: str = str(Path(__file__).resolve().parent.parent / "data" / "meals_dataset.json")

    # ── Server ────────────────────────────────────────────────
    HOST: str = os.getenv("HOST", "0.0.0.0")
    PORT: int = int(os.getenv("PORT", "8000"))
    DEBUG: bool = os.getenv("DEBUG", "true").lower() == "true"

    # ── Image Storage ─────────────────────────────────────────
    IMAGE_STORAGE_DIR: str = str(Path(__file__).resolve().parent.parent / "data" / "meal_images")


settings = Settings()
