"""Flashcard review log for offline replay and durable Undo (Phase 10.6).

Revision ID: e4b9d1f6a2c7
Revises: d2a7f5c3e8b1
Create Date: 2026-11-01

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "e4b9d1f6a2c7"
down_revision: str | None = "d2a7f5c3e8b1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "flashcard_reviews",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "card_id",
            sa.Uuid(),
            sa.ForeignKey("flashcards.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("client_review_id", sa.String(length=64), nullable=True),
        sa.Column("rating", sa.String(length=8), nullable=False),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("previous_state", sa.JSON(), nullable=True),
        sa.UniqueConstraint("card_id", "client_review_id", name="uq_flashcard_reviews_client_id"),
    )
    op.create_index("ix_flashcard_reviews_card_id", "flashcard_reviews", ["card_id"])


def downgrade() -> None:
    op.drop_index("ix_flashcard_reviews_card_id", table_name="flashcard_reviews")
    op.drop_table("flashcard_reviews")
