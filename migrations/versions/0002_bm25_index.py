"""BM25 index (pg_search) over chunks.embed_text with Spanish stemming."""

from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None

BM25_INDEX_SQL = """
CREATE INDEX chunks_bm25 ON chunks USING bm25 (id, embed_text, document_id, article_id)
WITH (
  key_field = 'id',
  text_fields = '{"embed_text": {"tokenizer": {"type": "default", "stemmer": "Spanish"}}}'
)
"""


def upgrade() -> None:
    op.execute(BM25_INDEX_SQL)


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS chunks_bm25")
