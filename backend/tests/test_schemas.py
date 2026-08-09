"""Task 1.6 acceptance: schemas import cleanly and round-trip test data."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

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
