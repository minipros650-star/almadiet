"""Condition restrictions + food-safety filter tests."""

from __future__ import annotations

from app.domain.conditions import (
    condition_exclusions,
    explanations_for_conditions,
    restrictions_for_conditions,
)
from app.domain.food_safety import exclusion_notes, unsafe_reason_for_ingredient


def test_gdm_excludes_desserts():
    meal = {"name": "Semiya Payasam", "meal_type": "Dessert", "sugar_g": 30}
    assert "gestational_diabetes" in condition_exclusions(meal, ["gestational_diabetes"])
    safe = {"name": "Ragi Dosa", "meal_type": "Breakfast", "sugar_g": 1}
    assert condition_exclusions(safe, ["gestational_diabetes"]) == []


def test_hypertension_excludes_high_sodium():
    meal = {"name": "Mango Pickle", "meal_type": "Condiment", "sodium_mg": 1500}
    assert "hypertension" in condition_exclusions(meal, ["hypertension"])


def test_nausea_excludes_spicy():
    meal = {"name": "Spicy Chilli Fry", "meal_type": "Lunch"}
    assert "severe_nausea_vomiting" in condition_exclusions(meal, ["severe_nausea_vomiting"])


def test_explanations_defer_to_clinician():
    for text in explanations_for_conditions(["gestational_diabetes", "anemia"]):
        low = text.lower()
        assert "clinician" in low or "doctor" in low
        assert "treat" not in low and "cure" not in low and "diagnos" not in low


def test_food_safety_raw_papaya_alcohol():
    assert unsafe_reason_for_ingredient("Raw papaya salad")
    assert unsafe_reason_for_ingredient("Wine sauce")
    assert unsafe_reason_for_ingredient("Cooked rice") is None


def test_exclusion_notes_scan_text():
    notes = exclusion_notes(
        {"ingredients": [{"name": "Rice"}], "cautions": "Contains unpasteurized milk"}
    )
    assert notes
