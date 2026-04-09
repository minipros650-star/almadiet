"""
AlmaDiet — ML Model Trainer
Generates synthetic pregnancy nutrition data and trains a Random Forest model
to predict nutrient priority scores based on maternal health parameters.

The model outputs a priority ranking of nutrients:
  [calories, protein, iron, calcium, folic_acid, fiber, omega3, vitamin_c]

Each score (0-10) indicates how important that nutrient is for the given
trimester, BMI, hemoglobin, blood sugar, and dietary preference.
"""

import os
import numpy as np
import pandas as pd
from pathlib import Path
from sklearn.ensemble import RandomForestRegressor
from sklearn.model_selection import train_test_split, cross_val_score
from sklearn.preprocessing import LabelEncoder
import joblib

from app.config import settings

NUTRIENT_NAMES = [
    "calories_priority",
    "protein_priority",
    "iron_priority",
    "calcium_priority",
    "folate_priority",
    "fiber_priority",
    "vitamin_c_priority",
]


def _generate_synthetic_data(n_samples: int = 5000) -> pd.DataFrame:
    """
    Generate synthetic training data for the nutrition priority model.
    Uses clinical guidelines for pregnancy nutrition by trimester.
    """
    np.random.seed(42)
    data = []

    for _ in range(n_samples):
        trimester = np.random.choice([1, 2, 3])
        week = np.random.randint(
            {1: 1, 2: 14, 3: 27}[trimester],
            {1: 14, 2: 27, 3: 42}[trimester],
        )
        bmi = np.random.normal(24, 5)
        bmi = np.clip(bmi, 15, 45)
        hemoglobin = np.random.normal(11.5, 2)
        hemoglobin = np.clip(hemoglobin, 4, 17)
        blood_sugar = np.random.normal(85, 20)
        blood_sugar = np.clip(blood_sugar, 40, 300)
        is_vegetarian = np.random.choice([0, 1], p=[0.6, 0.4])
        region_code = np.random.choice([0, 1, 2, 3])  # kerala, tamilnadu, karnataka, andhra
        age = np.random.randint(18, 42)
        weight_gain = np.random.normal(
            {1: 1, 2: 5, 3: 10}[trimester], 3
        )
        weight_gain = np.clip(weight_gain, -2, 25)

        # ── Generate target nutrient priorities based on clinical rules ──
        cal = 5.0  # base calorie priority
        pro = 5.0
        iron = 5.0
        calc = 5.0
        folic = 5.0
        fiber = 5.0
        vitc = 5.0

        # Trimester-specific adjustments
        if trimester == 1:
            folic += 4.0  # Critical for neural tube
            vitc += 1.5
            cal -= 1.0  # Less calorie increase needed
        elif trimester == 2:
            iron += 3.0  # Increased blood volume
            calc += 3.0  # Bone development
            pro += 2.0
            cal += 1.5
        else:  # trimester 3
            cal += 3.0  # Maximum calorie need
            pro += 3.0  # Rapid fetal growth
            vitc += 2.0  # Brain development support
            iron += 2.0
            calc += 2.0

        # BMI adjustments
        if bmi < 18.5:
            cal += 2.5
            pro += 1.5
        elif bmi > 30:
            cal -= 2.0
            fiber += 2.0

        # Hemoglobin adjustments (anemia)
        if hemoglobin < 11:
            iron += 3.0
            vitc += 2.0  # Helps iron absorption
        if hemoglobin < 7:
            iron += 2.0  # Critical anemia

        # Blood sugar adjustments (GDM risk)
        if blood_sugar > 92:
            fiber += 2.5
            cal -= 1.5
            pro += 1.0
        if blood_sugar > 126:
            fiber += 1.5
            cal -= 2.0

        # Vegetarian: may need more iron and protein from plant sources
        if is_vegetarian:
            iron += 1.5
            pro += 1.0
            vitc += 1.0  # Vitamin C aids plant iron absorption

        # Age adjustments
        if age > 35:
            folic += 1.0
            calc += 1.0

        # Clamp all priorities to 0-10
        priorities = np.clip(
            [cal, pro, iron, calc, folic, fiber, vitc], 0, 10
        )
        # Add some noise
        priorities += np.random.normal(0, 0.3, 7)
        priorities = np.clip(priorities, 0, 10)

        data.append({
            "trimester": trimester,
            "week": week,
            "bmi": round(bmi, 1),
            "hemoglobin": round(hemoglobin, 1),
            "blood_sugar": round(blood_sugar, 1),
            "is_vegetarian": is_vegetarian,
            "region_code": region_code,
            "age": age,
            "weight_gain": round(weight_gain, 1),
            **{name: round(float(val), 2) for name, val in zip(NUTRIENT_NAMES, priorities)},
        })

    return pd.DataFrame(data)


def train_model() -> dict:
    """
    Train the Random Forest model on synthetic pregnancy data.
    Saves model and returns training metrics.
    """
    print("📊 Generating synthetic training data...")
    df = _generate_synthetic_data(5000)

    feature_cols = [
        "trimester", "week", "bmi", "hemoglobin", "blood_sugar",
        "is_vegetarian", "region_code", "age", "weight_gain",
    ]
    X = df[feature_cols].values
    y = df[NUTRIENT_NAMES].values

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=42
    )

    print("🌲 Training Random Forest model...")
    model = RandomForestRegressor(
        n_estimators=200,
        max_depth=15,
        min_samples_split=5,
        min_samples_leaf=2,
        random_state=42,
        n_jobs=-1,
    )
    model.fit(X_train, y_train)

    # Evaluate
    train_score = model.score(X_train, y_train)
    test_score = model.score(X_test, y_test)

    print(f"✅ Training R² score: {train_score:.4f}")
    print(f"✅ Test R² score:     {test_score:.4f}")

    # Save model
    model_dir = Path(settings.ML_MODEL_PATH).parent
    model_dir.mkdir(parents=True, exist_ok=True)

    joblib.dump(model, settings.ML_MODEL_PATH)
    joblib.dump(feature_cols, settings.ML_PREPROCESSOR_PATH)

    print(f"💾 Model saved to {settings.ML_MODEL_PATH}")

    return {
        "train_score": round(train_score, 4),
        "test_score": round(test_score, 4),
        "n_features": len(feature_cols),
        "n_targets": len(NUTRIENT_NAMES),
        "n_samples": len(df),
    }


if __name__ == "__main__":
    metrics = train_model()
    print(f"\n📈 Training complete: {metrics}")
