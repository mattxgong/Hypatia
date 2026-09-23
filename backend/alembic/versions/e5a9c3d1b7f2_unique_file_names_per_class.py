"""Make source file names unique within a Class.

Revision ID: e5a9c3d1b7f2
Revises: d8f3a72c1e95
Create Date: 2026-09-23

"""

from collections.abc import Sequence
from pathlib import PurePath

import sqlalchemy as sa

from alembic import op

revision: str = "e5a9c3d1b7f2"
down_revision: str | None = "d8f3a72c1e95"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _rename_duplicates() -> None:
    """Rename later duplicates to ``name-N.ext``, matching raw-file collision names.

    Wiki pages reference files by ID, so renaming never orphans content.
    """
    conn = op.get_bind()
    rows = conn.execute(
        sa.text("SELECT id, class_id, original_filename FROM files ORDER BY created_at, id")
    ).fetchall()

    taken: dict[str, set[str]] = {}
    for _, class_id, filename in rows:
        taken.setdefault(class_id, set()).add(filename)

    seen: dict[str, set[str]] = {}
    for file_id, class_id, filename in rows:
        class_seen = seen.setdefault(class_id, set())
        if filename not in class_seen:
            class_seen.add(filename)
            continue

        path = PurePath(filename)
        counter = 1
        renamed = f"{path.stem}-{counter}{path.suffix}"
        while renamed in taken[class_id]:
            counter += 1
            renamed = f"{path.stem}-{counter}{path.suffix}"

        conn.execute(
            sa.text("UPDATE files SET original_filename = :name WHERE id = :id"),
            {"name": renamed, "id": file_id},
        )
        taken[class_id].add(renamed)
        class_seen.add(renamed)


def upgrade() -> None:
    _rename_duplicates()
    with op.batch_alter_table("files", schema=None) as batch_op:
        batch_op.create_unique_constraint(
            "uq_files_class_id_original_filename", ["class_id", "original_filename"]
        )


def downgrade() -> None:
    with op.batch_alter_table("files", schema=None) as batch_op:
        batch_op.drop_constraint("uq_files_class_id_original_filename", type_="unique")
