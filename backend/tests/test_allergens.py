"""CRITICAL TESTS 1 & 2 (unit level) — allergen taxonomy and matching."""

from __future__ import annotations

import pytest

from app.domain.allergens import (
    allergens_for_ingredients,
    check_user_allergies,
    cross_contact_warning,
    match_ingredient,
    normalize_term,
)


def test_peanut_synonyms_all_match():
    """TEST 1: peanut / groundnut / peanut butter / peanut flour all map."""
    for term in ("peanut", "groundnut", "peanut butter", "peanut flour", "Groundnuts"):
        assert AllergenCategory.PEANUT.value in match_ingredient(term), term


from app.domain.allergens import AllergenCategory  # noqa: E402


def test_normalized_matching_case_plural():
    assert match_ingredient("Peanuts") == match_ingredient("peanut")
    assert "milk" in match_ingredient("Curd")
    assert "egg" in match_ingredient("Eggs")


def test_multi_ingredient_meal_detection():
    ingredients = [
        {"name": "Rice flour"},
        {"name": "Peanut butter"},
        {"name": "Jaggery"},
    ]
    matched = allergens_for_ingredients(ingredients)
    assert matched == {"peanut": ["Peanut butter"]}


def test_check_user_allergies_multi_allergy():
    """TEST 2: multiple allergies all detected."""
    ingredients = [{"name": "Almonds"}, {"name": "Shrimp"}, {"name": "Wheat flour"}]
    found = check_user_allergies(
        ["tree_nut", "shellfish", "wheat_gluten"], [], ingredients, ""
    )
    assert found == {"tree_nut", "shellfish", "wheat_gluten"}


def test_meal_name_last_net():
    found = check_user_allergies(["peanut"], [], [{"name": "Rice"}], "Peanut Chikki")
    assert found == {"peanut"}


def test_no_false_positive_safe_meal():
    ingredients = [{"name": "Rice"}, {"name": "Moong dal"}, {"name": "Cumin"}]
    assert check_user_allergies(["peanut", "milk"], [], ingredients, "Khichdi") == set()


def test_cross_contact_detection():
    assert cross_contact_warning("May contain traces of nuts")
    assert not cross_contact_warning("Serve fresh")
