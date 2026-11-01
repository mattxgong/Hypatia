"""Weighted quiz questions: ``points`` per question (Phase 11.2).

Existing questions are worth 1, which keeps existing attempt scores valid.

Revision ID: d2a7f5c3e8b1
Revises: c9d4e2f7a1b6
Create Date: 2026-11-01

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "d2a7f5c3e8b1"
down_revision: str | None = "c9d4e2f7a1b6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("quiz_questions", schema=None) as batch_op:
        batch_op.add_column(sa.Column("points", sa.Integer(), nullable=False, server_default="1"))


def downgrade() -> None:
    with op.batch_alter_table("quiz_questions", schema=None) as batch_op:
        batch_op.drop_column("points")
