"""Track user-edited wiki pages in a column.

User edits were detected by finding ``user_edited: true`` in the first 500
characters of the page text. The column is now the source of truth; existing
pages are backfilled from that same check.

Revision ID: a7c4e9b2d5f1
Revises: f4b2c8d6e1a3
Create Date: 2026-10-27

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "a7c4e9b2d5f1"
down_revision: str | None = "f4b2c8d6e1a3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("wiki_pages", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("user_edited", sa.Boolean(), nullable=False, server_default=sa.false())
        )
    op.execute(
        "UPDATE wiki_pages SET user_edited = 1 "
        "WHERE instr(substr(content, 1, 500), 'user_edited: true') > 0"
    )


def downgrade() -> None:
    with op.batch_alter_table("wiki_pages", schema=None) as batch_op:
        batch_op.drop_column("user_edited")
