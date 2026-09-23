"""AlmaDiet ML package.

IMPORTANT: nothing in this package participates in the online
recommendation path unless an explicitly approved ModelRegistry row plus
a GATES_PASSED evaluation run exist and the feature flag is enabled.
Training/evaluation is offline-only (see preference_pipeline).
"""

from app.ml.preference_pipeline import (
    ALLOWED_FEATURES,
    LinearPreferenceScorer,
    baseline_rank,
    dataset_fingerprint,
    evaluate_ranker,
    extract_features,
)

__all__ = [
    "ALLOWED_FEATURES",
    "LinearPreferenceScorer",
    "baseline_rank",
    "dataset_fingerprint",
    "evaluate_ranker",
    "extract_features",
]
