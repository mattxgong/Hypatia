"""SQLAlchemy ORM models for the Hypatia database schema (Task 1.4)."""

from __future__ import annotations

import enum
import uuid
from datetime import UTC, datetime

from sqlalchemy import (
    JSON,
    DateTime,
    Enum,
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


class File(Base):
    __tablename__ = "files"

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
