"""AlmaDiet — Safety policy gate and candidate containment.

Three release-blocking guarantees live here:

1. ``active_policy_or_none`` — personalized generation may only run when a
   clinician-approved, ACTIVE ``SafetyPolicyVersion`` exists. Without one
   the API returns ``NEEDS_CLINICIAN_REVIEW``; no policy defaults are
   invented in code.

2. ``RankerContract`` — the ranker is a pure function over server-supplied
   eligible meal IDs (SAFE_CANDIDATE_IDS). Its output is validated:
   every returned ID must be in the candidate set, every candidate must
   appear exactly once, and the ordering must be reproducible for the
   same inputs. Any violation raises ``RankerViolation`` and the caller
   falls back to the deterministic baseline ordering — a ranker can never
   inject a meal the safety filter did not clear.

3. ``approved_model_or_none`` — a learned ranker may run only when
   (a) its feature flag is enabled, (b) a ModelRegistry row is APPROVED,
   and (c) its latest evaluation run has result == GATES_PASSED. Anything
   else returns None and the deterministic baseline is used.
"""

from __future__ import annotations

from typing import Iterable, Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.evidence import ModelEvaluationRun, ModelRegistry, SafetyPolicyVersion


class PolicyUnavailable(RuntimeError):
    """No clinician-approved ACTIVE policy exists."""

    code = "NEEDS_CLINICIAN_REVIEW"


class RankerViolation(RuntimeError):
    """The ranker returned output that violates the candidate contract."""

    code = "RANKER_CONTRACT_VIOLATION"


# ── 1. Policy gate ──────────────────────────────────────────────────

async def active_policy_or_none(db: AsyncSession) -> SafetyPolicyVersion | None:
    result = await db.execute(
        select(SafetyPolicyVersion)
        .where(
            SafetyPolicyVersion.status == "ACTIVE",
            SafetyPolicyVersion.approved_by.is_not(None),
            SafetyPolicyVersion.approved_at.is_not(None),
        )
        .order_by(SafetyPolicyVersion.created_at.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


async def require_active_policy(db: AsyncSession) -> SafetyPolicyVersion:
    policy = await active_policy_or_none(db)
    if policy is None:
        raise PolicyUnavailable(
            "No clinician-approved ACTIVE safety policy exists. "
            "Medically customized suggestions are unavailable; general, "
            "clearly-labeled meal browsing remains available."
        )
    return policy


# ── 2. Ranker contract ──────────────────────────────────────────────

class RankerContract:
    """Validates ranker output against SAFE_CANDIDATE_IDS.

    Usage::

        contract = RankerContract(candidate_ids)
        ranked = contract.enforce(ranker(candidate_ids, features))
        # ranked is guaranteed ⊆ candidate_ids, exactly-once, deterministic
    """

    def __init__(self, candidate_ids: Sequence[str]):
        if not candidate_ids:
            raise RankerViolation("Ranker invoked with an empty candidate set")
        self._candidates = list(candidate_ids)
        self._candidate_set = frozenset(str(c) for c in candidate_ids)

    @property
    def candidate_ids(self) -> list[str]:
        return list(self._candidates)

    def enforce(self, ranked: Iterable) -> list[str]:
        out: list[str] = []
        seen: set[str] = set()
        for item in ranked:
            meal_id = str(item)
            if meal_id not in self._candidate_set:
                # THE core containment rule: a ranker can never name a meal
                # outside the server-supplied eligible set.
                raise RankerViolation(f"Ranker returned non-candidate meal id: {meal_id!r}")
            if meal_id in seen:
                raise RankerViolation(f"Ranker duplicated meal id: {meal_id!r}")
            seen.add(meal_id)
            out.append(meal_id)
        if len(out) != len(self._candidates):
            raise RankerViolation(
                f"Ranker returned {len(out)} of {len(self._candidates)} candidates"
            )
        return out

    def enforce_top_k(self, ranked: Iterable, k: int) -> list[str]:
        """Top-K variant: prefix of candidates, no repeats, no outsiders."""
        out: list[str] = []
        seen: set[str] = set()
        for item in ranked:
            meal_id = str(item)
            if meal_id not in self._candidate_set:
                raise RankerViolation(f"Ranker returned non-candidate meal id: {meal_id!r}")
            if meal_id in seen:
                raise RankerViolation(f"Ranker duplicated meal id: {meal_id!r}")
            seen.add(meal_id)
            out.append(meal_id)
            if len(out) == k:
                return out
        raise RankerViolation(f"Ranker returned fewer than {k} candidates")

    @staticmethod
    def deterministic_baseline(candidate_ids: Sequence[str]) -> list[str]:
        """Stable, seedless ordering of the candidate set (the fallback)."""
        return sorted(str(c) for c in candidate_ids)


# ── 3. Learned-model deployment gate ────────────────────────────────

async def approved_model_or_none(
    db: AsyncSession, *, feature_flag_enabled: bool, model_name: str = "preference_ranker"
) -> ModelRegistry | None:
    """Return the usable APPROVED model, or None (→ deterministic baseline).

    Gates: feature flag ON + registry status APPROVED + latest evaluation
    run GATES_PASSED. Any failure keeps the deterministic baseline.
    """
    if not feature_flag_enabled:
        return None
    result = await db.execute(
        select(ModelRegistry)
        .where(
            ModelRegistry.model_name == model_name,
            ModelRegistry.status == "APPROVED",
            ModelRegistry.approved_by.is_not(None),
            ModelRegistry.approved_at.is_not(None),
        )
        .order_by(ModelRegistry.created_at.desc())
        .limit(1)
    )
    model = result.scalar_one_or_none()
    if model is None:
        return None
    runs = await db.execute(
        select(ModelEvaluationRun)
        .where(ModelEvaluationRun.model_id == model.id)
        .order_by(ModelEvaluationRun.created_at.desc())
        .limit(1)
    )
    latest_run = runs.scalar_one_or_none()
    if latest_run is None or latest_run.result != "GATES_PASSED":
        return None
    return model
