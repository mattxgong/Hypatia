"""Add wiki_page_embeddings table for semantic search.

Revision ID: d8f3a72c1e95
Revises: c7e2a0f31b84
Create Date: 2026-08-26

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "d8f3a72c1e95"
down_revision: str | None = "c7e2a0f31b84"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "wiki_page_embeddings",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "page_id",
            sa.Uuid(),
            sa.ForeignKey("wiki_pages.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        ),
        sa.Column("embedding", sa.LargeBinary(), nullable=False),
    )
    op.create_index("ix_wiki_page_embeddings_page_id", "wiki_page_embeddings", ["page_id"])


def downgrade() -> None:
    op.drop_index("ix_wiki_page_embeddings_page_id", table_name="wiki_page_embeddings")
    op.drop_table("wiki_page_embeddings")
