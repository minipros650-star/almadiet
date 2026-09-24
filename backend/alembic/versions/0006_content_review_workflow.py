"""Migration 0006 — content review & publication workflow.

Creates:
  * content_role_grants  (database-granted REVIEWER/PUBLISHER authority)
  * content_transitions  (immutable ledger: actor, states, source, rationale)

And makes consent acceptance idempotent:
  * uq_consents_user_version on consents (user_id, consent_version)

Uses batch_alter_table-compatible primitives only (works on PostgreSQL and
SQLite). No rows are inserted: the first role grant is a documented manual
bootstrap (scripts/bootstrap_content_role.py), never a migration side effect.
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql as pg

revision: str = "0006"
down_revision: Union[str, None] = "0005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _guid():
    return pg.UUID(as_uuid=True).with_variant(sa.CHAR(32), "sqlite")


def upgrade() -> None:
    op.create_table(
        "content_role_grants",
        sa.Column("id", _guid(), primary_key=True),
        sa.Column("user_id", _guid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("role", sa.String(20), nullable=False),
        sa.Column("granted_by_id", _guid(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("granted_by_label", sa.String(255), nullable=True),
        sa.Column("note", sa.String(500), nullable=True),
        sa.Column("granted_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("role IN ('REVIEWER','PUBLISHER')", name="ck_content_role_grants_role"),
        sa.UniqueConstraint("user_id", "role", name="uq_content_role_grants_user_role"),
    )
    op.create_index("ix_content_role_grants_user_id", "content_role_grants", ["user_id"])
    op.create_index("ix_content_role_grants_role", "content_role_grants", ["role"])

    op.create_table(
        "content_transitions",
        sa.Column("id", _guid(), primary_key=True),
        sa.Column("meal_id", _guid(), sa.ForeignKey("meals.id", ondelete="CASCADE"), nullable=False),
        sa.Column("actor_id", _guid(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("actor_label", sa.String(255), nullable=True),
        sa.Column("actor_role", sa.String(20), nullable=True),
        sa.Column("from_status", sa.String(20), nullable=False),
        sa.Column("to_status", sa.String(20), nullable=False),
        sa.Column("source_snapshot", sa.String(500), nullable=True),
        sa.Column("evidence_version", sa.String(32), nullable=True),
        sa.Column("rationale", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.CheckConstraint(
            "to_status IN ('DRAFT','REVIEW_REQUIRED','REVIEWED','PUBLISHED','RETIRED')",
            name="ck_content_transitions_to_status",
        ),
    )
    op.create_index(
        "ix_content_transitions_meal_created", "content_transitions", ["meal_id", "created_at"]
    )

    # Consent acceptance becomes a fact per (user, version) rather than an
    # append-only log.
    with op.batch_alter_table("consents") as batch:
        batch.create_unique_constraint(
            "uq_consents_user_version", ["user_id", "consent_version"]
        )


def downgrade() -> None:
    with op.batch_alter_table("consents") as batch:
        batch.drop_constraint("uq_consents_user_version", type_="unique")

    op.drop_index("ix_content_transitions_meal_created", table_name="content_transitions")
    op.drop_table("content_transitions")
    op.drop_index("ix_content_role_grants_role", table_name="content_role_grants")
    op.drop_index("ix_content_role_grants_user_id", table_name="content_role_grants")
    op.drop_table("content_role_grants")
