"""Story run checkpoints: the full story state after every turn, so an unfinished run can be continued.

Revision ID: 0002
Revises: 0001
Create Date: 2026-09-29
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("story_runs", sa.Column("state", postgresql.JSONB(astext_type=sa.Text()), nullable=True))
    op.add_column("story_runs", sa.Column("resumed_count", sa.Integer(), server_default="0", nullable=False))


def downgrade() -> None:
    op.drop_column("story_runs", "resumed_count")
    op.drop_column("story_runs", "state")
