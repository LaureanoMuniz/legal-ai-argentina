"""initial schema

Revision ID: 0001
Revises:
Create Date: 2026-09-12
"""

from alembic import op

from legal_ai.db.schema import metadata

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_search")
    metadata.create_all(op.get_bind())
    op.execute(
        "CREATE INDEX IF NOT EXISTS chunks_embedding_hnsw ON chunks "
        "USING hnsw (embedding vector_cosine_ops) WITH (m = 16, ef_construction = 64)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS chunks_embedding_hnsw")
    metadata.drop_all(op.get_bind())
