"""Add FTS5 virtual table for wiki page search.

Revision ID: c7e2a0f31b84
Revises: af54031e5fdb
Create Date: 2026-08-12

"""

from collections.abc import Sequence

from alembic import op

revision: str = "c7e2a0f31b84"
down_revision: str | None = "af54031e5fdb"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create the FTS5 virtual table for wiki page full-text search."""
    op.execute("""
        CREATE VIRTUAL TABLE IF NOT EXISTS wiki_pages_fts USING fts5(
            page_id UNINDEXED,
            class_id UNINDEXED,
            path UNINDEXED,
            title,
            content,
            tags
        )
    """)


def downgrade() -> None:
    """Drop the FTS5 virtual table."""
    op.execute("DROP TABLE IF EXISTS wiki_pages_fts")
