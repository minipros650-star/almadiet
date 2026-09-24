"""AlmaDiet — SQLAlchemy models (hardened schema).

Constraints mirror backend/app/domain validation as defence in depth.
Migrations live in backend/alembic — create_all is a dev/test convenience only.
"""

from app.models.user import User
from app.models.refresh_token import RefreshToken
from app.models.consent import Consent
from app.models.audit_log import AuditLog
from app.models.health_record import HealthRecord
from app.models.meal import Meal
from app.models.allergen import Allergen, MealAllergen
from app.models.content_version import ContentVersion
from app.models.content_role import ContentRoleGrant
from app.models.content_transition import ContentTransition
from app.models.diet_plan import DietPlan
from app.models.urgent_note import UrgentHelpNote
from app.models.meal_image import MealImage
from app.models.meal_favorite import MealFavorite
from app.models.user_file import UserFile
from app.models.nutrition_policy import NutritionPolicyApproval
from app.models.evidence import (
    ClinicalReviewDecision,
    EvidenceClaim,
    EvidenceSource,
    ModelEvaluationRun,
    ModelRegistry,
    SafetyPolicyVersion,
)

__all__ = [
    "User",
    "RefreshToken",
    "Consent",
    "AuditLog",
    "HealthRecord",
    "Meal",
    "Allergen",
    "MealAllergen",
    "ContentVersion",
    "ContentRoleGrant",
    "ContentTransition",
    "DietPlan",
    "UrgentHelpNote",
    "MealImage",
    "MealFavorite",
    "UserFile",
    "NutritionPolicyApproval",
    "EvidenceSource",
    "EvidenceClaim",
    "ClinicalReviewDecision",
    "SafetyPolicyVersion",
    "ModelRegistry",
    "ModelEvaluationRun",
]
