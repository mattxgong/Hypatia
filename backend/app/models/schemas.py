"""Pydantic schemas for API request/response contracts (Task 1.6)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

from app.models.db_models import (
    CardOrigin,
    CardType,
    ChatRole,
    FileStatus,
    FileType,
    QuestionType,
    StudyMethod,
    WikiCategory,
)

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
    progress: int | None = None
    message: str
    status: str
    error: str | None = None
    result: dict[str, str] | None = None
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


# --- Study (Phase 9) ---

StudyName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=255)]
StudyDescription = Annotated[str, StringConstraints(strip_whitespace=True, max_length=4000)]
CardFront = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=20_000)
]
CardBack = Annotated[str, StringConstraints(strip_whitespace=True, max_length=20_000)]
ReviewRating = Literal["again", "hard", "good", "easy"]
DeckExportFormat = Literal["csv", "anki"]
GenerationMethod = Literal["heuristic", "llm", "hybrid"]
_CLOZE_MARKER = "{{c1::"


class StudyScope(BaseModel):
    type: Literal["class", "topic", "pages", "file"] = "class"
    query: (
        Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=500)]
        | None
    ) = None
    paths: list[Annotated[str, StringConstraints(min_length=1, max_length=1024)]] | None = Field(
        default=None, max_length=500
    )
    file_id: uuid.UUID | None = None

    @model_validator(mode="after")
    def _check_required_field(self) -> StudyScope:
        if self.type == "topic" and not self.query:
            raise ValueError("topic scope requires 'query'")
        if self.type == "pages" and not self.paths:
            raise ValueError("pages scope requires 'paths'")
        if self.type == "file" and self.file_id is None:
            raise ValueError("file scope requires 'file_id'")
        return self


class DeckGenerateRequest(BaseModel):
    scope: StudyScope = Field(default_factory=StudyScope)
    method: GenerationMethod = "heuristic"
    count: int = Field(default=30, ge=1, le=500)
    card_types: list[CardType] = Field(
        default_factory=lambda: [CardType.BASIC, CardType.CLOZE], min_length=1
    )
    name: StudyName | None = None


class DeckCreate(BaseModel):
    name: StudyName
    description: StudyDescription | None = None


class DeckUpdate(BaseModel):
    name: StudyName | None = None
    description: StudyDescription | None = None


class DeckRead(BaseModel):
    id: uuid.UUID
    class_id: uuid.UUID
    name: str
    description: str | None
    generation_method: StudyMethod
    scope_json: dict | None
    card_count: int
    due_count: int
    stale_count: int
    created_at: datetime
    updated_at: datetime


class FlashcardCreate(BaseModel):
    card_type: CardType = CardType.BASIC
    front: CardFront
    back: CardBack = ""

    @model_validator(mode="after")
    def _check_cloze(self) -> FlashcardCreate:
        if self.card_type == CardType.CLOZE and _CLOZE_MARKER not in self.front:
            raise ValueError("cloze cards need a {{c1::answer}} deletion in 'front'")
        return self


class FlashcardUpdate(BaseModel):
    front: CardFront | None = None
    back: CardBack | None = None
    # Accept the current wiki pages as the card's new baseline, clearing "out of date".
    acknowledge_changes: bool = False


class FlashcardRead(BaseModel):
    id: uuid.UUID
    deck_id: uuid.UUID
    card_type: CardType
    front: str
    back: str
    origin: CardOrigin
    page_paths: list[str]
    source_file_ids: list[str]
    stale: bool
    ease: float
    interval_days: int
    repetitions: int
    lapses: int
    due_at: datetime
    last_reviewed_at: datetime | None
    created_at: datetime
    updated_at: datetime


class FlashcardReview(BaseModel):
    rating: ReviewRating


class DeckRefreshResponse(BaseModel):
    updated: int
    removed: int
    remaining_stale: int


class QuizGenerateRequest(BaseModel):
    scope: StudyScope = Field(default_factory=StudyScope)
    method: GenerationMethod = "heuristic"
    count: int = Field(default=10, ge=1, le=100)
    question_types: list[QuestionType] = Field(
        default_factory=lambda: [
            QuestionType.MCQ,
            QuestionType.TRUE_FALSE,
            QuestionType.MATCHING,
            QuestionType.FILL,
        ],
        min_length=1,
    )
    name: StudyName | None = None
    seed: int | None = None
    ai_grading: bool = True

    @model_validator(mode="after")
    def _check_types(self) -> QuizGenerateRequest:
        if self.method == "heuristic" and QuestionType.SHORT in self.question_types:
            raise ValueError("short-answer questions require AI or hybrid generation")
        return self


class StudyTaskStarted(BaseModel):
    """Returned (202) when AI generation runs as a background task; poll /api/tasks."""

    task_id: str
    kind: Literal["deck", "quiz"]


class QuizQuestionRead(BaseModel):
    id: uuid.UUID
    position: int
    question_type: QuestionType
    prompt: str
    choices: dict | None
    page_paths: list[str]
    stale: bool


class QuizSummaryRead(BaseModel):
    id: uuid.UUID
    class_id: uuid.UUID
    name: str
    generation_method: StudyMethod
    scope_json: dict | None
    settings_json: dict | None
    question_count: int
    stale_count: int
    attempt_count: int
    last_score: float | None
    last_max_score: float | None
    created_at: datetime
    updated_at: datetime


class QuizRead(QuizSummaryRead):
    questions: list[QuizQuestionRead]


class QuizAttemptCreate(BaseModel):
    answers: dict[uuid.UUID, dict[str, Any]] = Field(default_factory=dict, max_length=500)


class QuestionResultRead(BaseModel):
    question_id: uuid.UUID
    score: float
    correct: bool | None
    status: str
    response: dict[str, Any] | None
    expected: dict[str, Any]
    explanation: str | None
    feedback: str | None = None
    # "ai" or "self" for short answers; None for deterministic grading.
    grader: str | None = None


class AttemptSelfGrade(BaseModel):
    grades: dict[uuid.UUID, bool] = Field(min_length=1, max_length=500)


class QuizAttemptRead(BaseModel):
    id: uuid.UUID
    quiz_id: uuid.UUID
    score: float
    max_score: float
    results: list[QuestionResultRead]
    created_at: datetime
