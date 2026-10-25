"""Add the scoped identity and explicit-memory kernel.

Revision ID: 0002_memory_kernel
Revises: 0001_baseline
"""

# ruff: noqa: E501

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0002_memory_kernel"
down_revision: str | None = "0001_baseline"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCOPED_TABLES = (
    "subjects",
    "collections",
    "memories",
    "operations",
    "idempotency_records",
    "suppression_markers",
    "audit_events",
)


def _scope_columns() -> list[sa.Column[object]]:
    return [
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
    ]


def upgrade() -> None:
    op.create_table(
        "tenants",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_table(
        "projects",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenants.id"), nullable=False
        ),
        sa.Column("name", sa.Text(), nullable=False),
        sa.UniqueConstraint("tenant_id", "id"),
    )
    op.create_table(
        "principals",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenants.id"), nullable=False
        ),
        sa.Column("display_name", sa.Text(), nullable=False),
        sa.UniqueConstraint("tenant_id", "id"),
    )
    op.create_table(
        "project_memberships",
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("principal_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("role", sa.Text(), nullable=False, server_default="member"),
        sa.ForeignKeyConstraint(["project_id", "tenant_id"], ["projects.id", "projects.tenant_id"]),
        sa.ForeignKeyConstraint(
            ["principal_id", "tenant_id"], ["principals.id", "principals.tenant_id"]
        ),
        sa.PrimaryKeyConstraint("project_id", "principal_id"),
    )
    op.create_table(
        "api_keys",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("principal_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("key_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True)),
        sa.ForeignKeyConstraint(
            ["project_id", "principal_id"],
            ["project_memberships.project_id", "project_memberships.principal_id"],
        ),
    )
    op.create_table(
        "subjects",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        *_scope_columns(),
        sa.Column("external_id", sa.Text()),
        sa.UniqueConstraint("tenant_id", "project_id", "id"),
    )
    op.create_table(
        "agents",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        *_scope_columns(),
        sa.Column("name", sa.Text(), nullable=False),
    )
    op.create_table(
        "sessions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        *_scope_columns(),
        sa.Column("subject_id", postgresql.UUID(as_uuid=True), nullable=False),
    )
    op.create_table(
        "collections",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        *_scope_columns(),
        sa.Column("name", sa.Text(), nullable=False),
        sa.UniqueConstraint("tenant_id", "project_id", "id"),
    )
    op.create_table(
        "direct_entries",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        *_scope_columns(),
        sa.Column("actor_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "memories",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        *_scope_columns(),
        sa.Column("subject_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("collection_id", postgresql.UUID(as_uuid=True)),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("provenance_mode", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("current_version_id", postgresql.UUID(as_uuid=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("tenant_id", "project_id", "id"),
        sa.ForeignKeyConstraint(
            ["tenant_id", "project_id", "subject_id"],
            ["subjects.tenant_id", "subjects.project_id", "subjects.id"],
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "project_id", "collection_id"],
            ["collections.tenant_id", "collections.project_id", "collections.id"],
        ),
    )
    op.create_table(
        "memory_versions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "memory_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("memories.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("structured_value", postgresql.JSONB()),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("importance", sa.Float(), nullable=False),
        sa.Column("sensitivity", sa.Text(), nullable=False),
        sa.Column("valid_from", sa.DateTime(timezone=True)),
        sa.Column("valid_to", sa.DateTime(timezone=True)),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("actor_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.UniqueConstraint("memory_id", "version"),
        sa.CheckConstraint("confidence >= 0 AND confidence <= 1"),
        sa.CheckConstraint("importance >= 0 AND importance <= 1"),
        sa.CheckConstraint("valid_to IS NULL OR valid_from IS NULL OR valid_to > valid_from"),
    )
    op.create_foreign_key(
        "fk_current_version", "memories", "memory_versions", ["current_version_id"], ["id"]
    )
    op.create_table(
        "memory_evidence",
        sa.Column(
            "memory_version_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("memory_versions.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "direct_entry_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("direct_entries.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("episode_id", postgresql.UUID(as_uuid=True)),
        sa.Column("evidence_role", sa.Text(), nullable=False),
    )
    op.create_table(
        "memory_relations",
        sa.Column(
            "source_version_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("memory_versions.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "target_version_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("memory_versions.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("relation_type", sa.Text(), primary_key=True),
    )
    op.create_table(
        "operations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        *_scope_columns(),
        sa.Column("operation_type", sa.Text(), nullable=False),
        sa.Column("resource_id", postgresql.UUID(as_uuid=True)),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("committed_at", sa.DateTime(timezone=True)),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("failure_code", sa.Text()),
        sa.Column("retryable", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.create_table(
        "idempotency_records",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        *_scope_columns(),
        sa.Column("idempotency_key", sa.String(255), nullable=False),
        sa.Column("operation_type", sa.Text(), nullable=False),
        sa.Column("request_hash", sa.String(64), nullable=False),
        sa.Column(
            "operation_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("operations.id"),
            nullable=False,
        ),
        sa.Column("resource_id", postgresql.UUID(as_uuid=True)),
        sa.UniqueConstraint("tenant_id", "project_id", "idempotency_key"),
    )
    op.create_table(
        "suppression_markers",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        *_scope_columns(),
        sa.Column("memory_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("actor_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.UniqueConstraint("tenant_id", "project_id", "memory_id"),
    )
    op.create_table(
        "audit_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        *_scope_columns(),
        sa.Column("principal_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("action", sa.Text(), nullable=False),
        sa.Column("resource_type", sa.Text(), nullable=False),
        sa.Column("resource_id", postgresql.UUID(as_uuid=True)),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_memories_scope_order", "memories", ["tenant_id", "project_id", "created_at", "id"]
    )

    for table in SCOPED_TABLES:
        op.execute(sa.text(f'ALTER TABLE "{table}" ENABLE ROW LEVEL SECURITY'))
        op.execute(sa.text(f'ALTER TABLE "{table}" FORCE ROW LEVEL SECURITY'))
        op.execute(
            sa.text(
                f'CREATE POLICY {table}_scope ON "{table}" USING ('
                "tenant_id = nullif(current_setting('app.tenant_id', true), '')::uuid AND "
                "project_id = nullif(current_setting('app.project_id', true), '')::uuid) "
                "WITH CHECK (tenant_id = nullif(current_setting('app.tenant_id', true), '')::uuid AND "
                "project_id = nullif(current_setting('app.project_id', true), '')::uuid)"
            )
        )


def downgrade() -> None:
    op.drop_constraint("fk_current_version", "memories", type_="foreignkey")
    for table in (
        "audit_events",
        "suppression_markers",
        "idempotency_records",
        "operations",
        "memory_relations",
        "memory_evidence",
        "memory_versions",
        "memories",
        "direct_entries",
        "collections",
        "sessions",
        "agents",
        "subjects",
        "api_keys",
        "project_memberships",
        "principals",
        "projects",
        "tenants",
    ):
        op.drop_table(table)
