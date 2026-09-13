"""Richer human feedback: expected articles, retrieved articles, temporal flags, conversation."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None

COLUMNS = (
    sa.Column("expected_articles", JSONB),
    sa.Column("retrieved_articles", JSONB),
    sa.Column("as_of", sa.Date),
    sa.Column("historical", sa.Boolean),
    sa.Column("conversation_id", sa.String(36)),
)


def upgrade() -> None:
    for column in COLUMNS:
        op.add_column("feedback", column)
    op.create_index("ix_feedback_conversation_id", "feedback", ["conversation_id"])


def downgrade() -> None:
    op.drop_index("ix_feedback_conversation_id", table_name="feedback")
    for column in COLUMNS:
        op.drop_column("feedback", column.name)
