"""
AlmaDiet — ML Predictor
Loads the trained Random Forest model and predicts nutrient priorities
for a given set of maternal health parameters.
"""

from pathlib import Path
from typing import Optional

import numpy as np
import joblib

from app.config import settings

# Region name → numeric code mapping
REGION_MAP = {"kerala": 0, "tamilnadu": 1, "karnataka": 2, "andhra": 3}

NUTRIENT_NAMES = [
    "calories", "protein", "iron", "calcium",
    "folate", "fiber", "vitamin_c",
]

_model = None
_feature_cols = None


def _load_model():
    """Lazy-load the trained model."""
    global _model, _feature_cols
    model_path = Path(settings.ML_MODEL_PATH)
    preprocessor_path = Path(settings.ML_PREPROCESSOR_PATH)

    if not model_path.exists():
        raise FileNotFoundError(
            f"ML model not found at {model_path}. "
            "Run 'python -m app.ml.trainer' to train the model first."
        )

    _model = joblib.load(str(model_path))
    _feature_cols = joblib.load(str(preprocessor_path))


def predict_nutrient_priorities(
    trimester: int,
    week: int,
    bmi: float,
    hemoglobin: Optional[float] = None,
    blood_sugar: Optional[float] = None,
    is_vegetarian: bool = False,
    region: str = "kerala",
    age: int = 28,
    weight_gain: float = 0.0,
) -> dict[str, float]:
    """
    Predict nutrient priority scores (0-10) for the given health parameters.

    Returns a dict mapping nutrient name → priority score.
    Higher score = more important for this patient's current state.
    """
    global _model, _feature_cols
    if _model is None:
        _load_model()

    region_code = REGION_MAP.get(region.lower(), 0)

    features = np.array([[
        trimester,
        week,
        bmi or 24.0,
        hemoglobin or 11.5,
        blood_sugar or 85.0,
        int(is_vegetarian),
        region_code,
        age,
        weight_gain,
    ]])

    predictions = _model.predict(features)[0]
    # Clamp to 0-10
    predictions = np.clip(predictions, 0, 10)

    return {
        name: round(float(score), 2)
        for name, score in zip(NUTRIENT_NAMES, predictions)
    }


def get_top_nutrients(priorities: dict[str, float], top_n: int = 4) -> list[str]:
    """Get the top N most important nutrients sorted by priority."""
    sorted_nutrients = sorted(priorities.items(), key=lambda x: x[1], reverse=True)
    return [name for name, _ in sorted_nutrients[:top_n]]
