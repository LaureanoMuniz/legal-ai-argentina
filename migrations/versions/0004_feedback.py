"""Human feedback per answer (Phase 14)."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "feedback",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("trace_id", sa.String(32), nullable=False),
        sa.Column("question", sa.Text, nullable=False),
        sa.Column("answer", sa.Text),
        sa.Column("label", sa.String(32), nullable=False),
        sa.Column("comment", sa.Text),
        sa.Column("reviewer", sa.String(64)),
        sa.Column("sources", JSONB),
    )
    op.create_index("ix_feedback_trace_id", "feedback", ["trace_id"])


def downgrade() -> None:
    op.drop_table("feedback")
