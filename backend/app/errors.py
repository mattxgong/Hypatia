"""Centralized error catalog and exception hierarchy for Hypatia."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum, unique


@unique
class ErrorCode(StrEnum):
    INTERNAL_ERROR = "INTERNAL_ERROR"
    NOT_FOUND = "NOT_FOUND"
    VALIDATION_ERROR = "VALIDATION_ERROR"

    LLM_UNAVAILABLE = "LLM_UNAVAILABLE"
    LLM_AUTH_FAILED = "LLM_AUTH_FAILED"
    LLM_RATE_LIMITED = "LLM_RATE_LIMITED"
    LLM_TIMEOUT = "LLM_TIMEOUT"
    LLM_RESPONSE_INVALID = "LLM_RESPONSE_INVALID"

    INVALID_COMMAND = "INVALID_COMMAND"
    ASK_ERROR = "ASK_ERROR"
    SUMMARIZE_ERROR = "SUMMARIZE_ERROR"
    REMOVE_ERROR = "REMOVE_ERROR"
    LINT_ERROR = "LINT_ERROR"
    EXPORT_ERROR = "EXPORT_ERROR"
    REBUILD_ERROR = "REBUILD_ERROR"

    INGEST_FAILED = "INGEST_FAILED"
    FILE_TOO_LARGE = "FILE_TOO_LARGE"
    UNSUPPORTED_FORMAT = "UNSUPPORTED_FORMAT"
    FFMPEG_NOT_FOUND = "FFMPEG_NOT_FOUND"

    DB_LOCKED = "DB_LOCKED"
    INVALID_PROVIDER = "INVALID_PROVIDER"
    INVALID_SETTING = "INVALID_SETTING"


@dataclass(frozen=True)
class ErrorDetail:
    code: ErrorCode
    http_status: int
    message_template: str
    user_action: str | None = None


ERROR_CATALOG: dict[ErrorCode, ErrorDetail] = {
    ErrorCode.INTERNAL_ERROR: ErrorDetail(
        ErrorCode.INTERNAL_ERROR,
        500,
        "Internal server error",
    ),
    ErrorCode.NOT_FOUND: ErrorDetail(
        ErrorCode.NOT_FOUND,
        404,
        "Resource not found",
    ),
    ErrorCode.VALIDATION_ERROR: ErrorDetail(
        ErrorCode.VALIDATION_ERROR,
        422,
        "Validation error",
    ),
    ErrorCode.LLM_UNAVAILABLE: ErrorDetail(
        ErrorCode.LLM_UNAVAILABLE,
        503,
        "LLM provider is unavailable",
        "Check that your LLM provider is running and configured correctly in Settings.",
    ),
    ErrorCode.LLM_AUTH_FAILED: ErrorDetail(
        ErrorCode.LLM_AUTH_FAILED,
        401,
        "LLM authentication failed",
        "Check your API key in Settings.",
    ),
    ErrorCode.LLM_RATE_LIMITED: ErrorDetail(
        ErrorCode.LLM_RATE_LIMITED,
        429,
        "LLM rate limit exceeded",
        "Wait a moment and try again, or switch to a different provider.",
    ),
    ErrorCode.LLM_TIMEOUT: ErrorDetail(
        ErrorCode.LLM_TIMEOUT,
        504,
        "LLM request timed out",
        "The provider took too long to respond. Try again or check your connection.",
    ),
    ErrorCode.LLM_RESPONSE_INVALID: ErrorDetail(
        ErrorCode.LLM_RESPONSE_INVALID,
        502,
        "LLM returned an invalid response",
    ),
    ErrorCode.INVALID_COMMAND: ErrorDetail(
        ErrorCode.INVALID_COMMAND,
        400,
        "Invalid chat command",
    ),
    ErrorCode.ASK_ERROR: ErrorDetail(
        ErrorCode.ASK_ERROR,
        500,
        "Failed to process question",
    ),
    ErrorCode.SUMMARIZE_ERROR: ErrorDetail(
        ErrorCode.SUMMARIZE_ERROR,
        500,
        "Failed to generate summary",
    ),
    ErrorCode.REMOVE_ERROR: ErrorDetail(
        ErrorCode.REMOVE_ERROR,
        500,
        "Failed to remove content",
    ),
    ErrorCode.LINT_ERROR: ErrorDetail(
        ErrorCode.LINT_ERROR,
        500,
        "Failed to lint wiki",
    ),
    ErrorCode.EXPORT_ERROR: ErrorDetail(
        ErrorCode.EXPORT_ERROR,
        500,
        "Failed to export wiki",
    ),
    ErrorCode.REBUILD_ERROR: ErrorDetail(
        ErrorCode.REBUILD_ERROR,
        500,
        "Failed to rebuild wiki",
    ),
    ErrorCode.INGEST_FAILED: ErrorDetail(
        ErrorCode.INGEST_FAILED,
        500,
        "File ingestion failed",
    ),
    ErrorCode.FILE_TOO_LARGE: ErrorDetail(
        ErrorCode.FILE_TOO_LARGE,
        413,
        "File exceeds the maximum upload size",
        "Reduce the file size or increase the limit in Settings.",
    ),
    ErrorCode.UNSUPPORTED_FORMAT: ErrorDetail(
        ErrorCode.UNSUPPORTED_FORMAT,
        415,
        "Unsupported file format",
    ),
    ErrorCode.FFMPEG_NOT_FOUND: ErrorDetail(
        ErrorCode.FFMPEG_NOT_FOUND,
        500,
        "ffmpeg is not installed",
        "Install ffmpeg and ensure it is on your PATH.",
    ),
    ErrorCode.DB_LOCKED: ErrorDetail(
        ErrorCode.DB_LOCKED,
        503,
        "Database is temporarily locked",
        "Another operation is in progress. Try again shortly.",
    ),
    ErrorCode.INVALID_PROVIDER: ErrorDetail(
        ErrorCode.INVALID_PROVIDER,
        400,
        "Invalid LLM provider",
    ),
    ErrorCode.INVALID_SETTING: ErrorDetail(
        ErrorCode.INVALID_SETTING,
        400,
        "Invalid setting value",
    ),
}


class HypatiaError(Exception):
    """Base exception for all Hypatia-specific errors."""

    def __init__(
        self,
        code: ErrorCode = ErrorCode.INTERNAL_ERROR,
        detail: str | None = None,
        user_action: str | None = None,
    ) -> None:
        catalog_entry = ERROR_CATALOG.get(code)
        self.code = code
        self.detail = detail or (catalog_entry.message_template if catalog_entry else str(code))
        self.user_action = user_action or (catalog_entry.user_action if catalog_entry else None)
        self.http_status = catalog_entry.http_status if catalog_entry else 500
        super().__init__(self.detail)


class LLMUnavailableError(HypatiaError):
    def __init__(self, detail: str = "LLM provider is unavailable") -> None:
        super().__init__(code=ErrorCode.LLM_UNAVAILABLE, detail=detail)


class LLMProviderError(HypatiaError):
    def __init__(
        self,
        code: ErrorCode = ErrorCode.LLM_UNAVAILABLE,
        detail: str | None = None,
        user_action: str | None = None,
    ) -> None:
        super().__init__(code=code, detail=detail, user_action=user_action)


class ResourceNotFoundError(HypatiaError):
    def __init__(self, detail: str = "Resource not found") -> None:
        super().__init__(code=ErrorCode.NOT_FOUND, detail=detail)


class FileProcessingError(HypatiaError):
    def __init__(
        self,
        code: ErrorCode = ErrorCode.INGEST_FAILED,
        detail: str | None = None,
    ) -> None:
        super().__init__(code=code, detail=detail)


class SettingsError(HypatiaError):
    def __init__(self, detail: str | None = None) -> None:
        super().__init__(code=ErrorCode.INVALID_SETTING, detail=detail)
