"""Article-level cross references (cites) between articles."""

import sqlalchemy as sa
from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "article_references",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column(
            "source_article_id",
            sa.String(64),
            sa.ForeignKey("articles.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "target_article_id",
            sa.String(64),
            sa.ForeignKey("articles.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column("evidence", sa.Text, nullable=False),
        sa.UniqueConstraint("source_article_id", "target_article_id", name="uq_article_reference"),
    )
    op.create_index("ix_article_references_source", "article_references", ["source_article_id"])
    op.create_index("ix_article_references_target", "article_references", ["target_article_id"])


def downgrade() -> None:
    op.drop_table("article_references")
