"""Anki-style learning steps and a daily new-card limit for flashcards.

``learning_step`` is the card's position in its (re)learning steps, or NULL
once it has graduated. ``first_reviewed_at`` marks when a card was first
studied, so the due list can cap new cards per day.

Existing cards with no successful review yet (repetitions = 0) start in their
learning steps; the rest have graduated. ``first_reviewed_at`` is backfilled
from ``last_reviewed_at``.

Revision ID: b3d8f1a6c2e9
Revises: a7c4e9b2d5f1
Create Date: 2026-10-27

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "b3d8f1a6c2e9"
down_revision: str | None = "a7c4e9b2d5f1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("flashcards", schema=None) as batch_op:
        batch_op.add_column(sa.Column("learning_step", sa.Integer(), nullable=True))
        batch_op.add_column(
            sa.Column("first_reviewed_at", sa.DateTime(timezone=True), nullable=True)
        )
    op.execute("UPDATE flashcards SET learning_step = 0 WHERE repetitions = 0")
    op.execute("UPDATE flashcards SET first_reviewed_at = last_reviewed_at")


def downgrade() -> None:
    with op.batch_alter_table("flashcards", schema=None) as batch_op:
        batch_op.drop_column("first_reviewed_at")
        batch_op.drop_column("learning_step")
