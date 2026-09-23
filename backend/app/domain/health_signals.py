"""AlmaDiet — Informational health-value thresholds.

These thresholds trigger NEUTRAL clinician-discussion suggestions only.
They are NOT diagnoses, NOT statuses, and their output never feeds the meal
pipeline. Wording is mandated: "commonly used reference range" +
"this app cannot interpret lab values — share with your doctor/midwife".
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class DiscussionPoint:
    field: str          # which recorded value
    direction: str      # "below" | "above"
    value: float
    message: str


# Commonly used pregnancy reference ranges (informational only).
RANGES: dict[str, tuple[float, float]] = {
    "bmi": (18.5, 30.0),                # obesity threshold used as upper marker
    "blood_pressure_sys": (90.0, 140.0),
    "blood_pressure_dia": (60.0, 90.0),
    "hemoglobin": (11.0, 20.0),
    "blood_sugar_fasting": (70.0, 92.0),  # fasting, pregnancy-specific upper marker
}


def _message(field: str, direction: str, value: float, low: float, high: float) -> str:
    unit = {
        "bmi": "",
        "blood_pressure_sys": "mmHg",
        "blood_pressure_dia": "mmHg",
        "hemoglobin": "g/dL",
        "blood_sugar_fasting": "mg/dL",
    }.get(field, "")
    return (
        f"Your recorded {field.replace('_', ' ')} ({value:g}{' ' + unit if unit else ''}) is "
        f"{'below' if direction == 'below' else 'above'} the commonly used reference "
        f"range ({low:g}–{high:g}{(' ' + unit) if unit else ''}). This app cannot "
        "interpret lab values — please share this with your doctor or midwife."
    )


def discussion_points(record) -> list[DiscussionPoint]:
    """Compare a health record's optional values against reference ranges.

    `record` may be a HealthRecord ORM object or a dict. Missing values are
    skipped — never invented (SR-7).
    """
    def get(name: str):
        if isinstance(record, dict):
            return record.get(name)
        return getattr(record, name, None)

    points: list[DiscussionPoint] = []
    for field, (low, high) in RANGES.items():
        value = get(field)
        if value is None:
            continue
        try:
            value = float(value)
        except (TypeError, ValueError):
            continue
        if value < low:
            points.append(DiscussionPoint(field, "below", value, _message(field, "below", value, low, high)))
        elif value > high:
            points.append(DiscussionPoint(field, "above", value, _message(field, "above", value, low, high)))
    return points


def discussion_messages(record) -> list[str]:
    return [p.message for p in discussion_points(record)]
