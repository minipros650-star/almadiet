"""AlmaDiet — clinical-claim policy for patient-visible meal content.

The app must never present an unsourced clinical or medical assertion (ADR/0001).
That rule is enforced in three places, all of which route through this module:

  1. import  — descriptive prose fields are SANITIZED (the offending sentence
     is dropped) so unusable text never enters the catalog;
  2. review  — the content-review gate REJECTS a meal that still carries a
     claim anywhere a patient could see it;
  3. publish — the publication gate re-checks, so a claim can never become
     recommendable.

Two mechanisms cover every patient-visible field, and the difference is
deliberate:

  * MUTABLE fields are free descriptive prose. A claim sentence is removed,
    because the field is prose we own.
  * INSPECTED fields identify or classify the content (names, region, meal
    type, cuisine, ingredient labels). Rewriting those would corrupt meaning,
    so a claim there is a content defect and BLOCKS the workflow instead of
    being silently edited away.

``patient_visible_text_paths`` enumerates the coverage so a test can prove it
against the response schema rather than trusting this docstring.
"""

from __future__ import annotations

from typing import Any, Iterable

#: Claim phrases prohibited in patient-visible content (ADR/0001).
BANNED_CLAIMS = (
    "clinically approved", "medically approved", "who approved",
    "who certified", "doctor approved", "clinically validated",
    "medically validated", "clinically proven", "medically proven",
    "ai doctor", "clinical ai",
)

#: Prose fields we own and therefore rewrite when a claim is present.
MUTABLE_TEXT_FIELDS: tuple[str, ...] = (
    "cautions",
    "food_safety_notes",
    "best_time_to_eat",
    "serving_basis",
    "serving_size",
)

#: Prose list fields we own and therefore rewrite when a claim is present.
MUTABLE_LIST_FIELDS: tuple[str, ...] = ("benefits", "substitutions")

#: Fields that identify or classify the content. Never rewritten — only
#: inspected, because editing them would change what the content *is*.
#: Includes provenance and identifiers so the inventory covers EVERY text
#: field the meal response schema exposes (proved by tests/test_consent_and_claims.py).
INSPECTED_TEXT_FIELDS: tuple[str, ...] = (
    "name",
    "name_tamil",
    "name_malayalam",
    "name_kannada",
    "name_telugu",
    "region",
    "meal_type",
    "cuisine",
    "dataset_id",
    "image_url",
    "source",
    "source_url",
    "evidence_version",
    "content_status",
    "preparation_notes",
)

#: List-valued classifier fields: inspected, never rewritten.
#: `trimester_suitability` is imported verbatim from the dataset, so it is
#: scanned. `allergens` is deliberately NOT here: it is a derived property
#: assembled from catalog taxonomy codes by the safety matcher (see
#: DERIVED_PATIENT_PATHS).
INSPECTED_LIST_FIELDS: tuple[str, ...] = ("trimester_suitability",)

#: Patient-visible paths intentionally outside the claim policy. These carry
#: values produced by the server from its own controlled vocabulary, not free
#: text a claim could live in:
#:   * allergens[] — AllergenCategory codes derived from the allergen catalog.
#: Excluded also because `Meal.allergens` is a Python property over a
#: relationship, so reading it would force a lazy load on every gate call.
DERIVED_PATIENT_PATHS: frozenset[str] = frozenset({"allergens[]"})

#: Nested patient-visible text: (container field, subkeys inspected).
INSPECTED_NESTED_FIELDS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("ingredients", ("name", "quantity")),
)


def find_banned_claim(text: str | None) -> str | None:
    """Return the first banned claim phrase in ``text``, else None."""
    if not text:
        return None
    low = str(text).lower()
    for claim in BANNED_CLAIMS:
        if claim in low:
            return claim
    return None


def contains_banned_claim(text: str | None) -> bool:
    return find_banned_claim(text) is not None


def strip_banned_claims(text: str | None) -> str | None:
    """Remove sentences carrying an unsourced clinical claim from prose.

    Sentence splitting mirrors the original import behaviour ("; " is treated
    as a sentence boundary) so existing content is filtered identically.
    """
    if not text:
        return text
    cleaned_lines = []
    for line in str(text).replace("; ", ".\n").split(". "):
        if contains_banned_claim(line):
            continue
        cleaned_lines.append(line.strip().rstrip("."))
    return ". ".join(x for x in cleaned_lines if x) or None


def sanitize_text_list(items: Any) -> tuple[list[str], list[str]]:
    """Filter a list-of-strings prose field.

    Returns ``(kept, removed)``. Non-string entries are dropped (they are not
    usable patient text) and reported as removed.
    """
    if not items:
        return [], []
    if isinstance(items, str):
        items = [items]
    kept: list[str] = []
    removed: list[str] = []
    for item in items:
        if not isinstance(item, str):
            removed.append(str(item))
            continue
        cleaned = strip_banned_claims(item)
        if cleaned is None or not cleaned.strip():
            removed.append(item)
            continue
        kept.append(cleaned)
    return kept, removed


def sanitize_patient_fields(meal: Any) -> dict[str, list[str]]:
    """Sanitize the mutable prose fields of a meal in place.

    MUST be called on every import path, so banned claim sentences never reach
    the catalog. Inspected fields are intentionally left untouched — see the
    module docstring. Returns the removed text per field for logging/audit.
    """
    removed: dict[str, list[str]] = {}

    for field in MUTABLE_TEXT_FIELDS:
        original = getattr(meal, field, None)
        if not original:
            continue
        cleaned = strip_banned_claims(original)
        if cleaned != original:
            setattr(meal, field, cleaned)
            # Report only genuine claim removals: the sanitizer also normalizes
            # trailing punctuation, and that is not something to log as a
            # stripped clinical claim.
            if contains_banned_claim(original):
                removed[field] = [str(original)]

    for field in MUTABLE_LIST_FIELDS:
        original = getattr(meal, field, None)
        if not original:
            continue
        kept, dropped = sanitize_text_list(original)
        if dropped:
            setattr(meal, field, kept)
            claimful = [item for item in dropped if contains_banned_claim(item)]
            if claimful:
                removed[field] = claimful

    return removed


def find_claim_violations(meal: Any) -> list[dict[str, str]]:
    """Every unsourced clinical claim still visible to a patient.

    Used by the review and publication gates: a non-empty result blocks the
    transition. Covers the inspected fields as well, because a claim inside a
    name or an ingredient label is a defect that must not go live.
    """
    violations: list[dict[str, str]] = []

    for field in INSPECTED_TEXT_FIELDS + MUTABLE_TEXT_FIELDS:
        value = getattr(meal, field, None)
        claim = find_banned_claim(value)
        if claim:
            violations.append({"field": field, "claim": claim, "text": str(value)[:200]})

    for field in MUTABLE_LIST_FIELDS + INSPECTED_LIST_FIELDS:
        for item in (getattr(meal, field, None) or []):
            claim = find_banned_claim(item)
            if claim:
                violations.append({"field": f"{field}[]", "claim": claim, "text": str(item)[:200]})

    for field, subkeys in INSPECTED_NESTED_FIELDS:
        for item in (getattr(meal, field, None) or []):
            if not isinstance(item, dict):
                continue
            for subkey in subkeys:
                claim = find_banned_claim(item.get(subkey))
                if claim:
                    violations.append(
                        {
                            "field": f"{field}[].{subkey}",
                            "claim": claim,
                            "text": str(item.get(subkey))[:200],
                        }
                    )
    return violations


def patient_visible_text_paths() -> set[str]:
    """Every meal text path a patient can see, as ``field`` or ``field[].key``.

    Covers both mechanisms (sanitized and inspected) so a caller can prove the
    claim policy has no blind spot in the response schema.
    """
    paths = set(MUTABLE_TEXT_FIELDS) | set(INSPECTED_TEXT_FIELDS)
    # List fields are reported with a [] suffix, matching the `field` value a
    # violation carries, so policy inventory and findings stay comparable.
    paths |= {f"{field}[]" for field in MUTABLE_LIST_FIELDS + INSPECTED_LIST_FIELDS}
    for field, subkeys in INSPECTED_NESTED_FIELDS:
        for subkey in subkeys:
            paths.add(f"{field}[].{subkey}")
    return paths


def iter_patient_text(meal: Any) -> Iterable[str]:
    """Flatten every patient-visible text value of a meal (for scanning)."""
    for field in MUTABLE_TEXT_FIELDS + INSPECTED_TEXT_FIELDS:
        value = getattr(meal, field, None)
        if value:
            yield str(value)
    for field in MUTABLE_LIST_FIELDS + INSPECTED_LIST_FIELDS:
        for item in (getattr(meal, field, None) or []):
            yield str(item)
    for field, subkeys in INSPECTED_NESTED_FIELDS:
        for item in (getattr(meal, field, None) or []):
            if isinstance(item, dict):
                for subkey in subkeys:
                    if item.get(subkey):
                        yield str(item[subkey])
