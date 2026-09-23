"""AlmaDiet — Evidence, policy, and model-governance models.

Governance infrastructure for the recommendation architecture:

  approved web evidence → clinician review queue → versioned approved
  policy/content → deterministic safety filter → eligible meal candidates
  → preference ranking → explainable suggestions

Design rules encoded in this schema:

* ``EvidenceSource`` rows are untrusted retrieved documents: hashed,
  allowlisted, and never rendered as user-facing advice on their own.
* ``EvidenceClaim`` rows start at ``PENDING_CLINICAL_REVIEW`` and can only
  become ``APPROVED`` or ``REJECTED`` through an immutable
  ``ClinicalReviewDecision`` record.
* ``SafetyPolicyVersion`` rows are the versioned clinician-approved policy
  interface; an activated row gates personalized generation.
* ``ModelRegistry`` rows are explicitly approved learned rankers; nothing
  is auto-registered and nothing is auto-promoted.
* ``ModelEvaluationRun`` rows record metrics vs the deterministic baseline
  and the pass/fail of every deployment gate.

Approval records are insert-only: no UPDATE path exists in code for
``ClinicalReviewDecision`` — supersession happens by appending a newer
decision (superseded_by_id), preserving a full audit trail.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Optional

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from app.database import Base, GUID, JSONType
from sqlalchemy.orm import Mapped, mapped_column, relationship


class EvidenceSource(Base):
    """A retrieved document from an allowlisted domain (untrusted input).

    Rejection is the default state: only sources with publisher, title,
    publication/review date, retrieval date, supporting excerpt, and
    document hash proceed to claim extraction.
    """

    __tablename__ = "evidence_sources"
    __table_args__ = (
        Index("ix_evidence_sources_status", "status"),
        Index("ix_evidence_sources_domain", "domain"),
        UniqueConstraint("content_hash", name="uq_evidence_content_hash"),
    )

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    url: Mapped[str] = mapped_column(String(1000), nullable=False)
    domain: Mapped[str] = mapped_column(String(255), nullable=False)
    publisher: Mapped[str | None] = mapped_column(String(255), nullable=True)
    title: Mapped[str | None] = mapped_column(String(500), nullable=True)
    published_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    reviewed_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    retrieved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    # SHA-256 of the retrieved document text — dedup + tamper evidence.
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    supporting_excerpt: Mapped[str | None] = mapped_column(Text, nullable=True)
    topic_tags: Mapped[list | None] = mapped_column(JSONType, nullable=True, default=list)
    # PENDING_REVIEW | REJECTED | ACCEPTED_FOR_REVIEW
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="PENDING_REVIEW")
    rejection_reason: Mapped[str | None] = mapped_column(String(255), nullable=True)

    def __repr__(self) -> str:  # pragma: no cover
        return f"<EvidenceSource {self.domain} [{self.status}]>"


class EvidenceClaim(Base):
    """A single extracted claim. Starts PENDING_CLINICAL_REVIEW — always."""

    __tablename__ = "evidence_claims"
    __table_args__ = (
        Index("ix_evidence_claims_status", "status"),
        Index("ix_evidence_claims_source", "source_id"),
        UniqueConstraint("content_hash", name="uq_evidence_claim_hash"),
    )

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    source_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("evidence_sources.id", ondelete="CASCADE"), nullable=False
    )
    claim_text: Mapped[str] = mapped_column(Text, nullable=False)
    topic_tags: Mapped[list | None] = mapped_column(JSONType, nullable=True, default=list)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    # PENDING_CLINICAL_REVIEW | APPROVED | REJECTED | CONFLICT_PENDING_REVIEW
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="PENDING_CLINICAL_REVIEW"
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    source = relationship("EvidenceSource")

    def __repr__(self) -> str:  # pragma: no cover
        return f"<EvidenceClaim [{self.status}] {self.claim_text[:40]!r}>"


class ClinicalReviewDecision(Base):
    """Immutable clinician decision on a claim (insert-only; supersede, never edit)."""

    __tablename__ = "clinical_review_decisions"
    __table_args__ = (Index("ix_crd_claim", "claim_id", "reviewed_at"),)

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    claim_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("evidence_claims.id", ondelete="CASCADE"), nullable=False
    )
    # APPROVED | REJECTED
    decision: Mapped[str] = mapped_column(String(16), nullable=False)
    reviewed_by: Mapped[str] = mapped_column(String(255), nullable=False)
    reviewed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    rationale: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Set when a later decision supersedes this one; the row is never edited.
    superseded_by_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        GUID(), ForeignKey("clinical_review_decisions.id", ondelete="SET NULL"), nullable=True
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<ClinicalReviewDecision {self.decision} by {self.reviewed_by}>"


class SafetyPolicyVersion(Base):
    """Versioned clinician-approved policy interface.

    The policy payload may define: approved meal-content versions, approved
    allergen mappings, approved food-safety tags, approved restriction
    logic, and clinician-review-required situations. It NEVER invents
    rules in code — clinicians author and approve the payload; the app
    only enforces it.
    """

    __tablename__ = "safety_policy_versions"
    __table_args__ = (
        UniqueConstraint("policy_id", "version", name="uq_safety_policy_version"),
        Index("ix_safety_policy_status", "status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    policy_id: Mapped[str] = mapped_column(String(100), nullable=False)
    version: Mapped[str] = mapped_column(String(32), nullable=False)
    payload: Mapped[dict] = mapped_column(JSONType, nullable=False)
    # DRAFT | ACTIVE | RETIRED
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="DRAFT")
    approved_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    def __repr__(self) -> str:  # pragma: no cover
        return f"<SafetyPolicyVersion {self.policy_id}@{self.version} [{self.status}]>"


class ModelRegistry(Base):
    """Explicitly approved learned ranker versions. Nothing auto-registers."""

    __tablename__ = "model_registry"
    __table_args__ = (
        UniqueConstraint("model_name", "model_version", name="uq_model_version"),
        Index("ix_model_registry_status", "status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    model_name: Mapped[str] = mapped_column(String(100), nullable=False)
    model_version: Mapped[str] = mapped_column(String(32), nullable=False)
    # FEATURE_FLAG name that must be enabled to use this model at all.
    feature_flag: Mapped[str] = mapped_column(String(100), nullable=False, default="ENABLE_LEARNED_RANKER")
    # CANDIDATE | EVALUATED | APPROVED | RETIRED — APPROVED requires an
    # evaluation run that beat/matched the deterministic baseline.
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="CANDIDATE")
    policy_version: Mapped[str | None] = mapped_column(String(32), nullable=True)
    catalog_version: Mapped[str | None] = mapped_column(String(32), nullable=True)
    artifact_uri: Mapped[str | None] = mapped_column(String(500), nullable=True)
    feature_definition_version: Mapped[str | None] = mapped_column(String(32), nullable=True)
    dataset_version: Mapped[str | None] = mapped_column(String(32), nullable=True)
    random_seed: Mapped[int | None] = mapped_column(Integer, nullable=True)
    approved_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    def __repr__(self) -> str:  # pragma: no cover
        return f"<ModelRegistry {self.model_name}@{self.model_version} [{self.status}]>"


class ModelEvaluationRun(Base):
    """Recorded evaluation of a candidate model against the deterministic baseline."""

    __tablename__ = "model_evaluation_runs"
    __table_args__ = (
        Index("ix_eval_runs_model", "model_id", "created_at"),
        UniqueConstraint("model_id", "dataset_version", "split_seed", name="uq_eval_run"),
    )

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    model_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("model_registry.id", ondelete="CASCADE"), nullable=False
    )
    dataset_version: Mapped[str] = mapped_column(String(32), nullable=False)
    feature_definition_version: Mapped[str] = mapped_column(String(32), nullable=False)
    split_seed: Mapped[int] = mapped_column(Integer, nullable=False)
    # metrics JSON: {"model": {"ndcg@5": ...}, "baseline": {...}, "subgroups": {...}}
    metrics: Mapped[dict] = mapped_column(JSONType, nullable=False)
    beats_baseline: Mapped[bool] = mapped_column(Boolean, nullable=False)
    subgroup_checks_pass: Mapped[bool] = mapped_column(Boolean, nullable=False)
    # GATES_PASSED | GATES_FAILED
    result: Mapped[str] = mapped_column(String(16), nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    model = relationship("ModelRegistry")

    def __repr__(self) -> str:  # pragma: no cover
        return f"<ModelEvaluationRun {self.result} model={self.model_id}>"
