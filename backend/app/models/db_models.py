"""SQLAlchemy ORM models for the Hypatia database schema (Task 1.4)."""

from __future__ import annotations

import enum
import uuid
from datetime import UTC, datetime

from sqlalchemy import (
    JSON,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
    LargeBinary,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy.types import Uuid


def _utcnow() -> datetime:
    return datetime.now(UTC)


class Base(DeclarativeBase):
    pass


class FileType(str, enum.Enum):
    PDF = "pdf"
    DOCX = "docx"
    PPTX = "pptx"
    XLSX = "xlsx"
    IMAGE = "image"
    VIDEO = "video"
    AUDIO = "audio"
    MARKDOWN = "markdown"
    OTHER = "other"


class FileStatus(str, enum.Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    READY = "ready"
    ERROR = "error"


class WikiCategory(str, enum.Enum):
    SOURCE_SUMMARY = "source-summary"
    CONCEPT = "concept"
    ENTITY = "entity"
    SYNTHESIS = "synthesis"
    INDEX = "index"
    LOG = "log"


class ChatRole(str, enum.Enum):
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"


class StudyMethod(str, enum.Enum):
    HEURISTIC = "heuristic"
    LLM = "llm"
    HYBRID = "hybrid"


class CardType(str, enum.Enum):
    BASIC = "basic"
    CLOZE = "cloze"


class CardOrigin(str, enum.Enum):
    HEURISTIC = "heuristic"
    LLM = "llm"
    USER = "user"


class QuestionType(str, enum.Enum):
    MCQ = "mcq"
    TRUE_FALSE = "tf"
    MATCHING = "matching"
    FILL = "fill"
    SHORT = "short"


def _enum_values(enum_cls: type[enum.Enum]) -> list[str]:
    return [member.value for member in enum_cls]


class Class(Base):
    __tablename__ = "classes"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )

    files: Mapped[list[File]] = relationship(back_populates="class_", cascade="all, delete-orphan")
    wiki_pages: Mapped[list[WikiPage]] = relationship(
        back_populates="class_", cascade="all, delete-orphan"
    )
    chat_messages: Mapped[list[ChatMessage]] = relationship(
        back_populates="class_", cascade="all, delete-orphan"
    )
    decks: Mapped[list[Deck]] = relationship(back_populates="class_", cascade="all, delete-orphan")
    quizzes: Mapped[list[Quiz]] = relationship(
        back_populates="class_", cascade="all, delete-orphan"
    )


class File(Base):
    __tablename__ = "files"
    __table_args__ = (
        UniqueConstraint(
            "class_id", "original_filename", name="uq_files_class_id_original_filename"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    class_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("classes.id"), nullable=False, index=True
    )
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    file_type: Mapped[FileType] = mapped_column(
        Enum(FileType, values_callable=_enum_values), nullable=False
    )
    file_size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    raw_path: Mapped[str] = mapped_column(String(1024), nullable=False)
    converted_path: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    status: Mapped[FileStatus] = mapped_column(
        Enum(FileStatus, values_callable=_enum_values),
        default=FileStatus.PENDING,
        nullable=False,
    )
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    metadata_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )

    class_: Mapped[Class] = relationship(back_populates="files")


class WikiPage(Base):
    __tablename__ = "wiki_pages"
    __table_args__ = (UniqueConstraint("class_id", "path", name="uq_wiki_pages_class_id_path"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    class_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("classes.id"), nullable=False, index=True
    )
    path: Mapped[str] = mapped_column(String(1024), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    category: Mapped[WikiCategory] = mapped_column(
        Enum(WikiCategory, values_callable=_enum_values), nullable=False
    )
    content: Mapped[str] = mapped_column(Text, nullable=False, default="")
    source_file_ids: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )

    class_: Mapped[Class] = relationship(back_populates="wiki_pages")


class ChatMessage(Base):
    __tablename__ = "chat_messages"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    class_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("classes.id"), nullable=False, index=True
    )
    role: Mapped[ChatRole] = mapped_column(
        Enum(ChatRole, values_callable=_enum_values), nullable=False
    )
    content: Mapped[str] = mapped_column(Text, nullable=False)
    command: Mapped[str | None] = mapped_column(String(64), nullable=True)
    metadata_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )

    class_: Mapped[Class] = relationship(back_populates="chat_messages")


class WikiPageEmbedding(Base):
    __tablename__ = "wiki_page_embeddings"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    page_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("wiki_pages.id", ondelete="CASCADE"), nullable=False, unique=True, index=True
    )
    embedding: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)


class Deck(Base):
    __tablename__ = "decks"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    class_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("classes.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    generation_method: Mapped[StudyMethod] = mapped_column(
        Enum(StudyMethod, values_callable=_enum_values), nullable=False
    )
    scope_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )

    class_: Mapped[Class] = relationship(back_populates="decks")
    cards: Mapped[list[Flashcard]] = relationship(
        back_populates="deck", cascade="all, delete-orphan"
    )


class Flashcard(Base):
    __tablename__ = "flashcards"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    deck_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("decks.id", ondelete="CASCADE"), nullable=False, index=True
    )
    card_type: Mapped[CardType] = mapped_column(
        Enum(CardType, values_callable=_enum_values), nullable=False
    )
    front: Mapped[str] = mapped_column(Text, nullable=False)
    back: Mapped[str] = mapped_column(Text, nullable=False, default="")
    # {page_path: body hash} captured at generation; a mismatch marks the card out of date.
    page_hashes: Mapped[dict[str, str] | None] = mapped_column(JSON, nullable=True)
    source_file_ids: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    origin: Mapped[CardOrigin] = mapped_column(
        Enum(CardOrigin, values_callable=_enum_values), nullable=False
    )
    ease: Mapped[float] = mapped_column(Float, nullable=False, default=2.5)
    interval_days: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    repetitions: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    lapses: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    due_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    last_reviewed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )

    deck: Mapped[Deck] = relationship(back_populates="cards")


class Quiz(Base):
    __tablename__ = "quizzes"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    class_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("classes.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    generation_method: Mapped[StudyMethod] = mapped_column(
        Enum(StudyMethod, values_callable=_enum_values), nullable=False
    )
    scope_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    settings_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )

    class_: Mapped[Class] = relationship(back_populates="quizzes")
    questions: Mapped[list[QuizQuestion]] = relationship(
        back_populates="quiz",
        cascade="all, delete-orphan",
        order_by="QuizQuestion.position",
    )
    attempts: Mapped[list[QuizAttempt]] = relationship(
        back_populates="quiz", cascade="all, delete-orphan"
    )


class QuizQuestion(Base):
    __tablename__ = "quiz_questions"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    quiz_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("quizzes.id", ondelete="CASCADE"), nullable=False, index=True
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    question_type: Mapped[QuestionType] = mapped_column(
        Enum(QuestionType, values_callable=_enum_values), nullable=False
    )
    prompt: Mapped[str] = mapped_column(Text, nullable=False)
    choices_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    answer_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    explanation: Mapped[str | None] = mapped_column(Text, nullable=True)
    page_hashes: Mapped[dict[str, str] | None] = mapped_column(JSON, nullable=True)
    source_file_ids: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    quiz: Mapped[Quiz] = relationship(back_populates="questions")


class QuizAttempt(Base):
    __tablename__ = "quiz_attempts"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    quiz_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("quizzes.id", ondelete="CASCADE"), nullable=False, index=True
    )
    answers_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    grading_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    score: Mapped[float] = mapped_column(Float, nullable=False)
    max_score: Mapped[float] = mapped_column(Float, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    quiz: Mapped[Quiz] = relationship(back_populates="attempts")
