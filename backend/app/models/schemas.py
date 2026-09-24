"""Pydantic schemas for API request/response contracts (Task 1.6)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from app.models.db_models import ChatRole, FileStatus, FileType, WikiCategory

ClassName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=255)]
ClassDescription = Annotated[str, StringConstraints(strip_whitespace=True, max_length=4000)]
ProviderName = Literal["copilot", "copilot-ollama", "anthropic", "openai", "ollama"]
WhisperModelSize = Literal[
    "tiny",
    "base",
    "small",
    "medium",
    "large-v1",
    "large-v2",
    "large-v3",
    "distil-large-v2",
    "distil-large-v3",
    "turbo",
]
WhisperDevice = Literal["cpu", "cuda"]
BoundedModelName = Annotated[str, StringConstraints(strip_whitespace=True, max_length=255)]
BoundedSecret = Annotated[str, StringConstraints(max_length=8192)]
OllamaBaseUrl = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        min_length=1,
        max_length=2048,
        pattern=r"^https?://[^\s]+$",
    ),
]


class ClassCreate(BaseModel):
    name: ClassName
    description: ClassDescription | None = None


class ClassUpdate(BaseModel):
    name: ClassName | None = None
    description: ClassDescription | None = None


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
    # Queued for or undergoing wiki ingestion (source summary not written yet).
    ingesting: bool = False


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
    content: Annotated[str, StringConstraints(min_length=1, max_length=100_000)]
    command: Annotated[str, StringConstraints(max_length=64)] | None = None


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
    command: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=64)]
    args: dict | None = None


class CommandResponse(BaseModel):
    chat_message: ChatMessageRead
    updated_wiki_paths: list[str] = Field(default_factory=list)


class WikiTreeNodeRead(BaseModel):
    id: uuid.UUID
    path: str
    title: str
    category: WikiCategory
    user_edited: bool
    updated_at: datetime


class WikiPageUpdate(BaseModel):
    content: Annotated[str, StringConstraints(max_length=5_000_000)]


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
    llm_models: dict[str, str | None]
    llm_temperature: float
    llm_max_tokens: int
    anthropic_api_key: str | None
    openai_api_key: str | None
    github_token: str | None
    ollama_base_url: str
    whisper_model_size: str
    whisper_device: str


class SettingsUpdate(BaseModel):
    llm_provider: ProviderName | None = None
    llm_model: BoundedModelName | None = None
    llm_temperature: float | None = Field(default=None, ge=0, le=2)
    llm_max_tokens: int | None = Field(default=None, ge=1, le=1_000_000)
    anthropic_api_key: BoundedSecret | None = None
    openai_api_key: BoundedSecret | None = None
    github_token: BoundedSecret | None = None
    ollama_base_url: OllamaBaseUrl | None = None
    whisper_model_size: WhisperModelSize | None = None
    whisper_device: WhisperDevice | None = None


class ValidateKeyRequest(BaseModel):
    provider: ProviderName
    # None tests the saved key; "" tests with no key at all.
    api_key: BoundedSecret | None = None
    # None tests the saved model; "" tests the provider's default.
    model: BoundedModelName | None = None
    ollama_base_url: OllamaBaseUrl | None = None


class ValidateKeyResponse(BaseModel):
    valid: bool
    error: str | None = None
