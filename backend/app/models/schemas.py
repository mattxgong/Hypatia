"""Pydantic schemas for API request/response contracts (Task 1.6)."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.db_models import ChatRole, FileStatus, FileType, WikiCategory


class ClassCreate(BaseModel):
    name: str
    description: str | None = None


class ClassUpdate(BaseModel):
    name: str | None = None
    description: str | None = None


class ClassRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    description: str | None
    created_at: datetime
    updated_at: datetime


class FileRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    class_id: uuid.UUID
    original_filename: str
    file_type: FileType
    file_size_bytes: int
    raw_path: str
    converted_path: str | None
    status: FileStatus
    error_message: str | None
    metadata_json: dict | None
    created_at: datetime
    updated_at: datetime


class FileUploadResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    class_id: uuid.UUID
    original_filename: str
    status: FileStatus


class WikiPageRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    class_id: uuid.UUID
    path: str
    title: str
    category: WikiCategory
    content: str
    source_file_ids: list[str] | None
    created_at: datetime
    updated_at: datetime


class WikiPageSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    class_id: uuid.UUID
    path: str
    title: str
    category: WikiCategory
    updated_at: datetime


class ChatMessageCreate(BaseModel):
    content: str
    command: str | None = None


class ChatMessageRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    class_id: uuid.UUID
    role: ChatRole
    content: str
    command: str | None
    metadata_json: dict | None
    created_at: datetime
    updated_at: datetime


class CommandRequest(BaseModel):
    command: str
    args: dict | None = None


class CommandResponse(BaseModel):
    chat_message: ChatMessageRead
    updated_wiki_paths: list[str] = Field(default_factory=list)
