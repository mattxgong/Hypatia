"""Task 1.6 acceptance: schemas import cleanly and round-trip test data."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from app.models.db_models import ChatRole, FileStatus, FileType, WikiCategory
from app.models.schemas import (
    ChatMessageCreate,
    ChatMessageRead,
    ClassCreate,
    ClassRead,
    ClassUpdate,
    CommandRequest,
    CommandResponse,
    FileRead,
    FileUploadResponse,
    SettingsUpdate,
    ValidateKeyRequest,
    WikiPageRead,
    WikiPageSummary,
)


def test_class_create_and_update_round_trip() -> None:
    create = ClassCreate(name="Intro to ML", description="Fall 2026")
    assert ClassCreate.model_validate_json(create.model_dump_json()) == create

    update = ClassUpdate(name="Intro to ML (renamed)")
    assert update.description is None
    assert ClassUpdate.model_validate_json(update.model_dump_json()) == update


def test_class_read_round_trip() -> None:
    now = datetime.now(UTC)
    read = ClassRead(
        id=uuid.uuid4(), name="Data Structures", description=None, created_at=now, updated_at=now
    )
    assert ClassRead.model_validate_json(read.model_dump_json()) == read


def test_file_read_and_upload_response_round_trip() -> None:
    now = datetime.now(UTC)
    file_read = FileRead(
        id=uuid.uuid4(),
        class_id=uuid.uuid4(),
        original_filename="lecture-1.pdf",
        file_type=FileType.PDF,
        file_size_bytes=1024,
        raw_path="raw/lecture-1.pdf",
        converted_path=None,
        status=FileStatus.PENDING,
        error_message=None,
        metadata_json=None,
        created_at=now,
        updated_at=now,
    )
    assert FileRead.model_validate_json(file_read.model_dump_json()) == file_read

    upload_response = FileUploadResponse(
        id=file_read.id,
        class_id=file_read.class_id,
        original_filename=file_read.original_filename,
        status=FileStatus.PROCESSING,
    )
    assert (
        FileUploadResponse.model_validate_json(upload_response.model_dump_json()) == upload_response
    )


def test_wiki_page_read_and_summary_round_trip() -> None:
    now = datetime.now(UTC)
    page = WikiPageRead(
        id=uuid.uuid4(),
        class_id=uuid.uuid4(),
        path="concepts/gradient-descent.md",
        title="Gradient Descent",
        category=WikiCategory.CONCEPT,
        content="# Gradient Descent\n\n...",
        source_file_ids=["abc", "def"],
        created_at=now,
        updated_at=now,
    )
    assert WikiPageRead.model_validate_json(page.model_dump_json()) == page

    summary = WikiPageSummary(
        id=page.id,
        class_id=page.class_id,
        path=page.path,
        title=page.title,
        category=page.category,
        updated_at=page.updated_at,
    )
    assert WikiPageSummary.model_validate_json(summary.model_dump_json()) == summary


def test_chat_message_create_and_read_round_trip() -> None:
    create = ChatMessageCreate(content="Summarize lecture 1", command="/summarize")
    assert ChatMessageCreate.model_validate_json(create.model_dump_json()) == create

    now = datetime.now(UTC)
    read = ChatMessageRead(
        id=uuid.uuid4(),
        class_id=uuid.uuid4(),
        role=ChatRole.USER,
        content="Summarize lecture 1",
        command="/summarize",
        metadata_json=None,
        created_at=now,
        updated_at=now,
    )
    assert ChatMessageRead.model_validate_json(read.model_dump_json()) == read


def test_command_request_and_response_round_trip() -> None:
    request = CommandRequest(command="/regenerate", args={"path": "concepts/foo.md"})
    assert CommandRequest.model_validate_json(request.model_dump_json()) == request

    now = datetime.now(UTC)
    chat_message = ChatMessageRead(
        id=uuid.uuid4(),
        class_id=uuid.uuid4(),
        role=ChatRole.ASSISTANT,
        content="Regenerated the page.",
        command="/regenerate",
        metadata_json=None,
        created_at=now,
        updated_at=now,
    )
    response = CommandResponse(chat_message=chat_message, updated_wiki_paths=["concepts/foo.md"])
    round_tripped = CommandResponse.model_validate_json(response.model_dump_json())
    assert round_tripped == response


def test_command_response_default_updated_wiki_paths() -> None:
    now = datetime.now(UTC)
    chat_message = ChatMessageRead(
        id=uuid.uuid4(),
        class_id=uuid.uuid4(),
        role=ChatRole.ASSISTANT,
        content="No changes made.",
        command=None,
        metadata_json=None,
        created_at=now,
        updated_at=now,
    )
    response = CommandResponse(chat_message=chat_message)
    assert response.updated_wiki_paths == []


def test_class_inputs_are_trimmed_and_bounded() -> None:
    assert ClassCreate(name="  Biology  ").name == "Biology"

    with pytest.raises(ValidationError):
        ClassCreate(name="   ")
    with pytest.raises(ValidationError):
        ClassCreate(name="x" * 256)
    with pytest.raises(ValidationError):
        ClassUpdate(description="x" * 4001)


@pytest.mark.parametrize(
    "payload",
    [
        {"llm_provider": "unknown"},
        {"llm_temperature": -0.1},
        {"llm_temperature": 2.1},
        {"llm_max_tokens": 0},
        {"whisper_model_size": "enormous"},
        {"whisper_device": "metal"},
        {"ollama_base_url": "localhost:11434"},
    ],
)
def test_settings_update_rejects_invalid_values(payload: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        SettingsUpdate(**payload)


def test_settings_update_accepts_supported_values_and_secret_clear() -> None:
    update = SettingsUpdate(
        llm_provider="copilot-ollama",
        llm_temperature=0,
        llm_max_tokens=1_000_000,
        openai_api_key="",
        ollama_base_url="http://localhost:11434",
        whisper_model_size="large-v3",
        whisper_device="cuda",
    )

    assert update.openai_api_key == ""


def test_validate_key_request_rejects_unknown_provider() -> None:
    with pytest.raises(ValidationError):
        ValidateKeyRequest(provider="gemini", api_key="unused")
