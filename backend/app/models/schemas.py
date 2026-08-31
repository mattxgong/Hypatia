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


class ClassReadWithStats(ClassRead):
    file_count: int = 0
    page_count: int = 0


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


class WikiTreeNodeRead(BaseModel):
    path: str
    title: str
    category: WikiCategory
    user_edited: bool


class WikiPageUpdate(BaseModel):
    content: str


class TaskStatusRead(BaseModel):
    task_id: str
    operation: str
    class_id: str
    progress: int
    message: str
    status: str
    error: str | None = None
    created_at: str


class ExportResponse(BaseModel):
    export_path: str
    page_count: int


class WikiSearchResultRead(BaseModel):
    page_id: str
    class_id: str
    path: str
    title: str
    category: str
    rank: float
    snippet: str


class WikiSearchResponse(BaseModel):
    results: list[WikiSearchResultRead]
    total_count: int


# --- Settings ---


class SettingsRead(BaseModel):
    llm_provider: str
    llm_model: str | None
    llm_temperature: float
    llm_max_tokens: int
    anthropic_api_key: str | None
    openai_api_key: str | None
    github_token: str | None
    ollama_base_url: str
    whisper_model_size: str
    whisper_device: str


class SettingsUpdate(BaseModel):
    llm_provider: str | None = None
    llm_model: str | None = None
    llm_temperature: float | None = None
    llm_max_tokens: int | None = None
    anthropic_api_key: str | None = None
    openai_api_key: str | None = None
    github_token: str | None = None
    ollama_base_url: str | None = None
    whisper_model_size: str | None = None
    whisper_device: str | None = None


class ValidateKeyRequest(BaseModel):
    provider: str
    api_key: str


class ValidateKeyResponse(BaseModel):
    valid: bool
    error: str | None = None
