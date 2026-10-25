"""Add durable episodes and retry-safe formation storage.

Revision ID: 0003_episode_formation
Revises: 0002_memory_kernel
"""

# ruff: noqa: E501

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects import postgresql

revision: str = "0003_episode_formation"
down_revision: str | None = "0002_memory_kernel"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCOPED_TABLES = ("episodes", "formation_runs", "profile_entries", "session_state")


def _scope_columns() -> list[sa.Column[object]]:
    return [
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
    ]


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.create_table(
        "episodes",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        *_scope_columns(),
        sa.Column("subject_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("agent_id", postgresql.UUID(as_uuid=True)),
        sa.Column("session_id", postgresql.UUID(as_uuid=True)),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("role", sa.Text()),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ingested_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("source", sa.Text(), nullable=False),
        sa.Column("source_ref", sa.Text()),
        sa.Column("sensitivity", sa.Text(), nullable=False),
        sa.Column("consent_basis", sa.Text()),
        sa.Column("status", sa.Text(), nullable=False),
        sa.UniqueConstraint("tenant_id", "project_id", "id"),
        sa.ForeignKeyConstraint(
            ["tenant_id", "project_id", "subject_id"],
            ["subjects.tenant_id", "subjects.project_id", "subjects.id"],
        ),
    )
    op.create_table(
        "outbox_jobs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        *_scope_columns(),
        sa.Column(
            "operation_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("operations.id"),
            nullable=False,
        ),
        sa.Column("job_type", sa.Text(), nullable=False),
        sa.Column("deduplication_key", sa.Text(), nullable=False, unique=True),
        sa.Column("payload_version", sa.Integer(), nullable=False),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("available_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("lease_owner", sa.Text()),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True)),
        sa.Column("last_failure_code", sa.Text()),
    )
    op.create_table(
        "formation_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        *_scope_columns(),
        sa.Column(
            "operation_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("operations.id"),
            nullable=False,
        ),
        sa.Column("stage", sa.Text(), nullable=False),
        sa.Column("provider", sa.Text()),
        sa.Column("model", sa.Text()),
        sa.Column("prompt_version", sa.Text(), nullable=False),
        sa.Column("schema_version", sa.Text(), nullable=False),
        sa.Column("usage", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("safety_outcome", sa.Text()),
        sa.Column("failure_code", sa.Text()),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("operation_id", "stage"),
    )
    op.create_table(
        "memory_embeddings",
        sa.Column(
            "memory_version_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("memory_versions.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("provider", sa.Text(), nullable=False),
        sa.Column("model", sa.Text(), nullable=False),
        sa.Column("version", sa.Text(), nullable=False),
        sa.Column("dimensions", sa.Integer(), nullable=False),
        sa.Column("embedding", Vector(), nullable=False),
    )
    for table, owner, extra in (
        (
            "profile_entries",
            "subject_id",
            [
                sa.Column("priority", sa.Float(), nullable=False),
                sa.Column("token_cost", sa.Integer(), nullable=False),
            ],
        ),
        (
            "session_state",
            "session_id",
            [
                sa.Column("state_kind", sa.Text(), nullable=False),
                sa.Column("expires_at", sa.DateTime(timezone=True)),
            ],
        ),
    ):
        op.create_table(
            table,
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
            *_scope_columns(),
            sa.Column(
                "memory_version_id",
                postgresql.UUID(as_uuid=True),
                sa.ForeignKey("memory_versions.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column(owner, postgresql.UUID(as_uuid=True), nullable=False),
            *extra,
            sa.Column("status", sa.Text(), nullable=False),
            sa.UniqueConstraint("memory_version_id"),
        )
    op.alter_column("memory_evidence", "direct_entry_id", nullable=True)
    op.create_foreign_key(
        "fk_memory_evidence_episode",
        "memory_evidence",
        "episodes",
        ["episode_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_check_constraint(
        "ck_memory_evidence_source",
        "memory_evidence",
        "(direct_entry_id IS NOT NULL) <> (episode_id IS NOT NULL)",
    )
    for table in SCOPED_TABLES:
        op.execute(sa.text(f'ALTER TABLE "{table}" ENABLE ROW LEVEL SECURITY'))
        op.execute(sa.text(f'ALTER TABLE "{table}" FORCE ROW LEVEL SECURITY'))
        op.execute(
            sa.text(
                f"CREATE POLICY {table}_scope ON \"{table}\" USING (tenant_id = nullif(current_setting('app.tenant_id', true), '')::uuid AND project_id = nullif(current_setting('app.project_id', true), '')::uuid) WITH CHECK (tenant_id = nullif(current_setting('app.tenant_id', true), '')::uuid AND project_id = nullif(current_setting('app.project_id', true), '')::uuid)"
            )
        )


def downgrade() -> None:
    op.drop_constraint("ck_memory_evidence_source", "memory_evidence", type_="check")
    op.drop_constraint("fk_memory_evidence_episode", "memory_evidence", type_="foreignkey")
    op.alter_column("memory_evidence", "direct_entry_id", nullable=False)
    for table in (
        "session_state",
        "profile_entries",
        "memory_embeddings",
        "formation_runs",
        "outbox_jobs",
        "episodes",
    ):
        op.drop_table(table)
