"""Migration 0005 — evidence pipeline and model governance.

Creates:
  * evidence_sources            (allowlisted retrieved documents, hashed)
  * evidence_claims             (extracted claims; start PENDING_CLINICAL_REVIEW)
  * clinical_review_decisions   (immutable insert-only clinician decisions)
  * safety_policy_versions      (versioned clinician-approved policy interface)
  * model_registry              (explicitly approved learned-ranker versions)
  * model_evaluation_runs       (metrics vs deterministic baseline + gate results)

Uses batch_alter_table-compatible primitives only (works on PostgreSQL and
SQLite). No seeded rows: all governance tables start empty.
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql as pg

revision: str = "0005"
down_revision: Union[str, None] = "0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _guid():
    return pg.UUID(as_uuid=True).with_variant(sa.CHAR(32), "sqlite")


def _jsonb():
    return pg.JSONB().with_variant(sa.JSON(), "sqlite")


def upgrade() -> None:
    op.create_table(
        "evidence_sources",
        sa.Column("id", _guid(), primary_key=True),
        sa.Column("url", sa.String(1000), nullable=False),
        sa.Column("domain", sa.String(255), nullable=False),
        sa.Column("publisher", sa.String(255), nullable=True),
        sa.Column("title", sa.String(500), nullable=True),
        sa.Column("published_on", sa.Date(), nullable=True),
        sa.Column("reviewed_on", sa.Date(), nullable=True),
        sa.Column("retrieved_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("supporting_excerpt", sa.Text(), nullable=True),
        sa.Column("topic_tags", _jsonb(), nullable=True),
        sa.Column("status", sa.String(32), nullable=False, server_default="PENDING_REVIEW"),
        sa.Column("rejection_reason", sa.String(255), nullable=True),
        sa.UniqueConstraint("content_hash", name="uq_evidence_content_hash"),
    )
    op.create_index("ix_evidence_sources_status", "evidence_sources", ["status"])
    op.create_index("ix_evidence_sources_domain", "evidence_sources", ["domain"])

    op.create_table(
        "evidence_claims",
        sa.Column("id", _guid(), primary_key=True),
        sa.Column("source_id", _guid(), sa.ForeignKey("evidence_sources.id", ondelete="CASCADE"), nullable=False),
        sa.Column("claim_text", sa.Text(), nullable=False),
        sa.Column("topic_tags", _jsonb(), nullable=True),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="PENDING_CLINICAL_REVIEW"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("content_hash", name="uq_evidence_claim_hash"),
    )
    op.create_index("ix_evidence_claims_status", "evidence_claims", ["status"])
    op.create_index("ix_evidence_claims_source", "evidence_claims", ["source_id"])

    op.create_table(
        "clinical_review_decisions",
        sa.Column("id", _guid(), primary_key=True),
        sa.Column("claim_id", _guid(), sa.ForeignKey("evidence_claims.id", ondelete="CASCADE"), nullable=False),
        sa.Column("decision", sa.String(16), nullable=False),
        sa.Column("reviewed_by", sa.String(255), nullable=False),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("rationale", sa.Text(), nullable=True),
        sa.Column(
            "superseded_by_id", _guid(), sa.ForeignKey("clinical_review_decisions.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.create_index("ix_crd_claim", "clinical_review_decisions", ["claim_id", "reviewed_at"])

    op.create_table(
        "safety_policy_versions",
        sa.Column("id", _guid(), primary_key=True),
        sa.Column("policy_id", sa.String(100), nullable=False),
        sa.Column("version", sa.String(32), nullable=False),
        sa.Column("payload", _jsonb(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="DRAFT"),
        sa.Column("approved_by", sa.String(255), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("policy_id", "version", name="uq_safety_policy_version"),
    )
    op.create_index("ix_safety_policy_status", "safety_policy_versions", ["status"])

    op.create_table(
        "model_registry",
        sa.Column("id", _guid(), primary_key=True),
        sa.Column("model_name", sa.String(100), nullable=False),
        sa.Column("model_version", sa.String(32), nullable=False),
        sa.Column("feature_flag", sa.String(100), nullable=False, server_default="ENABLE_LEARNED_RANKER"),
        sa.Column("status", sa.String(16), nullable=False, server_default="CANDIDATE"),
        sa.Column("policy_version", sa.String(32), nullable=True),
        sa.Column("catalog_version", sa.String(32), nullable=True),
        sa.Column("artifact_uri", sa.String(500), nullable=True),
        sa.Column("feature_definition_version", sa.String(32), nullable=True),
        sa.Column("dataset_version", sa.String(32), nullable=True),
        sa.Column("random_seed", sa.Integer(), nullable=True),
        sa.Column("approved_by", sa.String(255), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("model_name", "model_version", name="uq_model_version"),
    )
    op.create_index("ix_model_registry_status", "model_registry", ["status"])

    op.create_table(
        "model_evaluation_runs",
        sa.Column("id", _guid(), primary_key=True),
        sa.Column("model_id", _guid(), sa.ForeignKey("model_registry.id", ondelete="CASCADE"), nullable=False),
        sa.Column("dataset_version", sa.String(32), nullable=False),
        sa.Column("feature_definition_version", sa.String(32), nullable=False),
        sa.Column("split_seed", sa.Integer(), nullable=False),
        sa.Column("metrics", _jsonb(), nullable=False),
        sa.Column("beats_baseline", sa.Boolean(), nullable=False),
        sa.Column("subgroup_checks_pass", sa.Boolean(), nullable=False),
        sa.Column("result", sa.String(16), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("model_id", "dataset_version", "split_seed", name="uq_eval_run"),
    )
    op.create_index("ix_eval_runs_model", "model_evaluation_runs", ["model_id", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_eval_runs_model", table_name="model_evaluation_runs")
    op.drop_table("model_evaluation_runs")
    op.drop_index("ix_model_registry_status", table_name="model_registry")
    op.drop_table("model_registry")
    op.drop_index("ix_safety_policy_status", table_name="safety_policy_versions")
    op.drop_table("safety_policy_versions")
    op.drop_index("ix_crd_claim", table_name="clinical_review_decisions")
    op.drop_table("clinical_review_decisions")
    op.drop_index("ix_evidence_claims_source", table_name="evidence_claims")
    op.drop_index("ix_evidence_claims_status", table_name="evidence_claims")
    op.drop_table("evidence_claims")
    op.drop_index("ix_evidence_sources_domain", table_name="evidence_sources")
    op.drop_index("ix_evidence_sources_status", table_name="evidence_sources")
    op.drop_table("evidence_sources")
