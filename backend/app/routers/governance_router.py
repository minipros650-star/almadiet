"""AlmaDiet — Governance Router (/api/v1/governance).

Reviewer-only control plane for the recommendation architecture:

* SafetyPolicyVersion: create DRAFT → clinician ACTIVATES (sets
  approved_by/approved_at atomically; prior ACTIVE versions are retired
  so exactly one policy is active).
* ModelRegistry: register CANDIDATE → record ModelEvaluationRun →
  APPROVE (only when the run passed all gates). No auto-promotion.
* Retiring a model flips its status; approval rows are never edited.

All endpoints require the reviewer gate (REVIEWER_EMAILS; dev bootstrap
allowlist). Regular users receive 403.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.jwt_handler import get_current_user
from app.config import settings
from app.database import get_db
from app.models.evidence import (
    ModelEvaluationRun,
    ModelRegistry,
    SafetyPolicyVersion,
)
from app.services.audit_service import EventCodes, record_event

router = APIRouter(prefix="/api/v1/governance", tags=["Governance (admin)"])


def require_reviewer(user: object = Depends(get_current_user)) -> object:
    reviewer_emails = {
        e.strip().lower()
        for e in os.getenv("REVIEWER_EMAILS", "").split(",")
        if e.strip()
    }
    if settings.ENVIRONMENT == "development" and not reviewer_emails:
        reviewer_emails = {
            e.strip().lower()
            for e in os.getenv("BOOTSTRAP_ADMIN_EMAILS", "admin@example.com").split(",")
            if e.strip()
        }
    if getattr(user, "email", "").lower() not in reviewer_emails:
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="Reviewer privileges required")
    return user


def _now() -> datetime:
    return datetime.now(timezone.utc)


# ── Safety policy versions ──────────────────────────────────────────

class PolicyCreateRequest(BaseModel):
    policy_id: str = Field(..., min_length=2, max_length=100)
    version: str = Field(..., min_length=1, max_length=32)
    payload: dict = Field(..., description="Clinician-authored policy payload")


class PolicyActivateRequest(BaseModel):
    rationale: str | None = Field(None, max_length=2000)


@router.post("/policies", status_code=201)
async def create_policy(
    data: PolicyCreateRequest,
    db: AsyncSession = Depends(get_db),
    reviewer: object = Depends(require_reviewer),
):
    existing = await db.execute(
        select(SafetyPolicyVersion).where(
            SafetyPolicyVersion.policy_id == data.policy_id,
            SafetyPolicyVersion.version == data.version,
        )
    )
    if existing.scalar_one_or_none() is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, detail="Policy version already exists")
    row = SafetyPolicyVersion(
        policy_id=data.policy_id,
        version=data.version,
        payload=data.payload,
        status="DRAFT",
    )
    db.add(row)
    await db.flush()
    return {"id": str(row.id), "status": row.status}


@router.post("/policies/{policy_id}/{version}/activate", status_code=200)
async def activate_policy(
    policy_id: str,
    version: str,
    data: PolicyActivateRequest,
    db: AsyncSession = Depends(get_db),
    reviewer: object = Depends(require_reviewer),
):
    """Clinician approval point: activates exactly one policy version."""
    row = await db.execute(
        select(SafetyPolicyVersion).where(
            SafetyPolicyVersion.policy_id == policy_id,
            SafetyPolicyVersion.version == version,
        )
    )
    policy = row.scalar_one_or_none()
    if policy is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Policy version not found")
    if policy.status == "RETIRED":
        raise HTTPException(status.HTTP_409_CONFLICT, detail="Retired policies cannot be reactivated")
    # Retire any other ACTIVE version of the same policy.
    others = await db.execute(
        select(SafetyPolicyVersion).where(
            SafetyPolicyVersion.policy_id == policy_id,
            SafetyPolicyVersion.status == "ACTIVE",
        )
    )
    for other in others.scalars():
        other.status = "RETIRED"
    policy.status = "ACTIVE"
    policy.approved_by = getattr(reviewer, "email", "unknown")
    policy.approved_at = _now()
    await db.flush()
    await record_event(
        db, EventCodes.CONTENT_STATUS_CHANGED, getattr(reviewer, "id", None),
        {"kind": "safety_policy_activated", "policy": f"{policy_id}@{version}",
         "rationale": data.rationale},
    )
    return {"policy": f"{policy.policy_id}@{policy.version}", "status": policy.status,
            "approved_by": policy.approved_by}


# ── Model registry + evaluation runs ────────────────────────────────

class ModelRegisterRequest(BaseModel):
    model_name: str = Field(..., min_length=2, max_length=100)
    model_version: str = Field(..., min_length=1, max_length=32)
    policy_version: str | None = None
    catalog_version: str | None = None
    artifact_uri: str | None = Field(None, max_length=500)
    feature_definition_version: str | None = None
    dataset_version: str | None = None
    random_seed: int | None = None


class EvaluationRunRequest(BaseModel):
    dataset_version: str = Field(..., min_length=1, max_length=32)
    feature_definition_version: str = Field(..., min_length=1, max_length=32)
    split_seed: int = Field(..., ge=0)
    metrics: dict
    beats_baseline: bool
    subgroup_checks_pass: bool
    notes: str | None = Field(None, max_length=4000)


class ModelApproveRequest(BaseModel):
    rationale: str | None = Field(None, max_length=2000)


@router.post("/models", status_code=201)
async def register_model(
    data: ModelRegisterRequest,
    db: AsyncSession = Depends(get_db),
    reviewer: object = Depends(require_reviewer),
):
    existing = await db.execute(
        select(ModelRegistry).where(
            ModelRegistry.model_name == data.model_name,
            ModelRegistry.model_version == data.model_version,
        )
    )
    if existing.scalar_one_or_none() is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, detail="Model version already registered")
    row = ModelRegistry(
        model_name=data.model_name,
        model_version=data.model_version,
        feature_flag="ENABLE_LEARNED_RANKER",
        status="CANDIDATE",
        policy_version=data.policy_version,
        catalog_version=data.catalog_version,
        artifact_uri=data.artifact_uri,
        feature_definition_version=data.feature_definition_version,
        dataset_version=data.dataset_version,
        random_seed=data.random_seed,
    )
    db.add(row)
    await db.flush()
    return {"id": str(row.id), "status": row.status}


@router.post("/models/{model_id}/evaluations", status_code=201)
async def record_evaluation(
    model_id: str,
    data: EvaluationRunRequest,
    db: AsyncSession = Depends(get_db),
    reviewer: object = Depends(require_reviewer),
):
    model = await db.get(ModelRegistry, model_id)
    if model is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Model not found")
    gates_pass = data.beats_baseline and data.subgroup_checks_pass
    run = ModelEvaluationRun(
        model_id=model.id,
        dataset_version=data.dataset_version,
        feature_definition_version=data.feature_definition_version,
        split_seed=data.split_seed,
        metrics=data.metrics,
        beats_baseline=data.beats_baseline,
        subgroup_checks_pass=data.subgroup_checks_pass,
        result="GATES_PASSED" if gates_pass else "GATES_FAILED",
        notes=data.notes,
    )
    db.add(run)
    await db.flush()
    if model.status == "CANDIDATE" and not gates_pass:
        model.status = "EVALUATED"
    await db.flush()
    return {"run_id": str(run.id), "result": run.result}


@router.post("/models/{model_id}/approve", status_code=200)
async def approve_model(
    model_id: str,
    data: ModelApproveRequest,
    db: AsyncSession = Depends(get_db),
    reviewer: object = Depends(require_reviewer),
):
    """Explicit human approval — the ONLY path to status APPROVED."""
    model = await db.get(ModelRegistry, model_id)
    if model is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Model not found")
    runs = await db.execute(
        select(ModelEvaluationRun)
        .where(ModelEvaluationRun.model_id == model.id)
        .order_by(ModelEvaluationRun.created_at.desc())
        .limit(1)
    )
    latest = runs.scalar_one_or_none()
    if latest is None or latest.result != "GATES_PASSED":
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail="Model cannot be approved without a GATES_PASSED evaluation run",
        )
    model.status = "APPROVED"
    model.approved_by = getattr(reviewer, "email", "unknown")
    model.approved_at = _now()
    await db.flush()
    await record_event(
        db, EventCodes.CONTENT_STATUS_CHANGED, getattr(reviewer, "id", None),
        {"kind": "model_approved", "model": f"{model.model_name}@{model.model_version}",
         "rationale": data.rationale},
    )
    return {"model": f"{model.model_name}@{model.model_version}", "status": model.status,
            "approved_by": model.approved_by}


@router.post("/models/{model_id}/retire", status_code=200)
async def retire_model(
    model_id: str,
    db: AsyncSession = Depends(get_db),
    reviewer: object = Depends(require_reviewer),
):
    model = await db.get(ModelRegistry, model_id)
    if model is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Model not found")
    model.status = "RETIRED"
    await db.flush()
    return {"model": f"{model.model_name}@{model.model_version}", "status": model.status}
