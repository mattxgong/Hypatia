"""Add flashcard decks and practice quizzes (Phase 9).

Revision ID: f4b2c8d6e1a3
Revises: e5a9c3d1b7f2
Create Date: 2026-10-01

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "f4b2c8d6e1a3"
down_revision: str | None = "e5a9c3d1b7f2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _study_method() -> sa.Enum:
    return sa.Enum("heuristic", "llm", "hybrid", name="studymethod")


def upgrade() -> None:
    op.create_table(
        "decks",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "class_id",
            sa.Uuid(),
            sa.ForeignKey("classes.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("generation_method", _study_method(), nullable=False),
        sa.Column("scope_json", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_decks_class_id", "decks", ["class_id"])

    op.create_table(
        "flashcards",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "deck_id",
            sa.Uuid(),
            sa.ForeignKey("decks.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("card_type", sa.Enum("basic", "cloze", name="cardtype"), nullable=False),
        sa.Column("front", sa.Text(), nullable=False),
        sa.Column("back", sa.Text(), nullable=False),
        sa.Column("page_hashes", sa.JSON(), nullable=True),
        sa.Column("source_file_ids", sa.JSON(), nullable=True),
        sa.Column("origin", sa.Enum("heuristic", "llm", "user", name="cardorigin"), nullable=False),
        sa.Column("ease", sa.Float(), nullable=False),
        sa.Column("interval_days", sa.Integer(), nullable=False),
        sa.Column("repetitions", sa.Integer(), nullable=False),
        sa.Column("lapses", sa.Integer(), nullable=False),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_flashcards_deck_id", "flashcards", ["deck_id"])

    op.create_table(
        "quizzes",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "class_id",
            sa.Uuid(),
            sa.ForeignKey("classes.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("generation_method", _study_method(), nullable=False),
        sa.Column("scope_json", sa.JSON(), nullable=True),
        sa.Column("settings_json", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_quizzes_class_id", "quizzes", ["class_id"])

    op.create_table(
        "quiz_questions",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "quiz_id",
            sa.Uuid(),
            sa.ForeignKey("quizzes.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column(
            "question_type",
            sa.Enum("mcq", "tf", "matching", "fill", "short", name="questiontype"),
            nullable=False,
        ),
        sa.Column("prompt", sa.Text(), nullable=False),
        sa.Column("choices_json", sa.JSON(), nullable=True),
        sa.Column("answer_json", sa.JSON(), nullable=False),
        sa.Column("explanation", sa.Text(), nullable=True),
        sa.Column("page_hashes", sa.JSON(), nullable=True),
        sa.Column("source_file_ids", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_quiz_questions_quiz_id", "quiz_questions", ["quiz_id"])

    op.create_table(
        "quiz_attempts",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "quiz_id",
            sa.Uuid(),
            sa.ForeignKey("quizzes.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("answers_json", sa.JSON(), nullable=False),
        sa.Column("grading_json", sa.JSON(), nullable=False),
        sa.Column("score", sa.Float(), nullable=False),
        sa.Column("max_score", sa.Float(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_quiz_attempts_quiz_id", "quiz_attempts", ["quiz_id"])


def downgrade() -> None:
    op.drop_index("ix_quiz_attempts_quiz_id", table_name="quiz_attempts")
    op.drop_table("quiz_attempts")
    op.drop_index("ix_quiz_questions_quiz_id", table_name="quiz_questions")
    op.drop_table("quiz_questions")
    op.drop_index("ix_quizzes_class_id", table_name="quizzes")
    op.drop_table("quizzes")
    op.drop_index("ix_flashcards_deck_id", table_name="flashcards")
    op.drop_table("flashcards")
    op.drop_index("ix_decks_class_id", table_name="decks")
    op.drop_table("decks")
