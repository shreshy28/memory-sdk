"""Add indexes for policy-scoped hybrid retrieval.

Revision ID: 0004_hybrid_retrieval
Revises: 0003_episode_formation
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0004_hybrid_retrieval"
down_revision: str | None = "0003_episode_formation"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("ALTER TABLE memory_embeddings ALTER COLUMN embedding TYPE vector(16)")
    op.execute(
        "CREATE INDEX ix_memory_versions_text_fts ON memory_versions "
        "USING gin (to_tsvector('simple', text))"
    )
    op.execute(
        "CREATE INDEX ix_memories_retrieval_scope ON memories "
        "(tenant_id, project_id, subject_id, status, current_version_id)"
    )
    op.execute(
        "CREATE INDEX ix_memory_embeddings_cosine ON memory_embeddings "
        "USING hnsw (embedding vector_cosine_ops)"
    )


def downgrade() -> None:
    op.drop_index("ix_memory_embeddings_cosine", table_name="memory_embeddings")
    op.drop_index("ix_memories_retrieval_scope", table_name="memories")
    op.drop_index("ix_memory_versions_text_fts", table_name="memory_versions")
    op.execute("ALTER TABLE memory_embeddings ALTER COLUMN embedding TYPE vector")
