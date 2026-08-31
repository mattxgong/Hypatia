"""Settings API router — read/update global application settings."""

from __future__ import annotations

import httpx
from fastapi import APIRouter, HTTPException, Request

from app.config import settings
from app.models.schemas import (
    SettingsRead,
    SettingsUpdate,
    ValidateKeyRequest,
    ValidateKeyResponse,
)
from app.services.settings_store import save_settings
from app.utils.logging import get_logger

logger = get_logger()

router = APIRouter(prefix="/api/settings", tags=["settings"])

VALID_PROVIDERS = ("copilot", "copilot-ollama", "anthropic", "openai", "ollama")


def _mask_key(key: str | None) -> str | None:
    if not key:
        return None
    if len(key) <= 12:
        return "****"
    return key[:4] + "..." + key[-4:]


def _build_response() -> SettingsRead:
    return SettingsRead(
        llm_provider=settings.llm_provider,
        llm_model=settings.llm_model,
        llm_temperature=settings.llm_temperature,
        llm_max_tokens=settings.llm_max_tokens,
        anthropic_api_key=_mask_key(settings.anthropic_api_key),
        openai_api_key=_mask_key(settings.openai_api_key),
        github_token=_mask_key(settings.github_token),
        ollama_base_url=settings.ollama_base_url,
        whisper_model_size=settings.whisper_model_size,
        whisper_device=settings.whisper_device,
    )


@router.get("", response_model=SettingsRead)
async def get_settings() -> SettingsRead:
    return _build_response()


@router.put("", response_model=SettingsRead)
async def update_settings(body: SettingsUpdate, request: Request) -> SettingsRead:
    persist_fields: dict[str, object] = {}
    secret_fields: dict[str, str] = {}

    if body.llm_provider is not None:
        if body.llm_provider not in VALID_PROVIDERS:
            raise HTTPException(
                status_code=422,
                detail=f"Invalid provider. Must be one of: {', '.join(VALID_PROVIDERS)}",
            )
        settings.llm_provider = body.llm_provider
        persist_fields["llm_provider"] = body.llm_provider
        logger.info("settings_updated", field="llm_provider", value=body.llm_provider)

    if body.llm_model is not None:
        settings.llm_model = body.llm_model if body.llm_model else None
        persist_fields["llm_model"] = settings.llm_model
        logger.info("settings_updated", field="llm_model", value=body.llm_model)

    if body.llm_temperature is not None:
        settings.llm_temperature = body.llm_temperature
        persist_fields["llm_temperature"] = body.llm_temperature
        logger.info("settings_updated", field="llm_temperature", value=body.llm_temperature)

    if body.llm_max_tokens is not None:
        settings.llm_max_tokens = body.llm_max_tokens
        persist_fields["llm_max_tokens"] = body.llm_max_tokens
        logger.info("settings_updated", field="llm_max_tokens", value=body.llm_max_tokens)

    if body.anthropic_api_key is not None:
        val = body.anthropic_api_key if body.anthropic_api_key else None
        settings.anthropic_api_key = val
        if val:
            secret_fields["anthropic_api_key"] = val
        logger.info("settings_updated", field="anthropic_api_key", value="[redacted]")

    if body.openai_api_key is not None:
        val = body.openai_api_key if body.openai_api_key else None
        settings.openai_api_key = val
        if val:
            secret_fields["openai_api_key"] = val
        logger.info("settings_updated", field="openai_api_key", value="[redacted]")

    if body.github_token is not None:
        val = body.github_token if body.github_token else None
        settings.github_token = val
        if val:
            secret_fields["github_token"] = val
        logger.info("settings_updated", field="github_token", value="[redacted]")

    if body.ollama_base_url is not None:
        settings.ollama_base_url = body.ollama_base_url
        persist_fields["ollama_base_url"] = body.ollama_base_url
        logger.info("settings_updated", field="ollama_base_url", value=body.ollama_base_url)

    if body.whisper_model_size is not None:
        settings.whisper_model_size = body.whisper_model_size
        persist_fields["whisper_model_size"] = body.whisper_model_size
        logger.info("settings_updated", field="whisper_model_size", value=body.whisper_model_size)

    if body.whisper_device is not None:
        settings.whisper_device = body.whisper_device
        persist_fields["whisper_device"] = body.whisper_device
        logger.info("settings_updated", field="whisper_device", value=body.whisper_device)

    if persist_fields:
        save_settings(settings.data_dir, persist_fields)

    if secret_fields and hasattr(request.app.state, "credential_store"):
        cred_store = request.app.state.credential_store
        for key, value in secret_fields.items():
            cred_store.set(key, value)

    return _build_response()


@router.post("/validate-key", response_model=ValidateKeyResponse)
async def validate_key(body: ValidateKeyRequest) -> ValidateKeyResponse:
    """Test whether an API key is valid by constructing a temporary provider."""
    from app.services.llm_service import get_llm_provider

    if body.provider not in VALID_PROVIDERS:
        raise HTTPException(status_code=422, detail=f"Invalid provider: {body.provider}")

    temp_cfg = settings.model_copy(deep=True)

    if body.provider == "anthropic":
        temp_cfg.anthropic_api_key = body.api_key
    elif body.provider == "openai":
        temp_cfg.openai_api_key = body.api_key
    elif body.provider == "copilot":
        temp_cfg.github_token = body.api_key

    temp_cfg.llm_provider = body.provider

    try:
        provider = get_llm_provider(cfg=temp_cfg)
        await provider.complete("test", "Say hello.", max_tokens=5)
        return ValidateKeyResponse(valid=True)
    except Exception as exc:  # noqa: BLE001
        return ValidateKeyResponse(valid=False, error=str(exc))


@router.get("/usage")
async def get_usage() -> dict[str, object]:
    """Return token usage totals since the backend started."""
    from app.services.llm_providers.base import usage_totals

    return usage_totals.to_dict()


@router.get("/ollama-models")
async def list_ollama_models() -> list[str]:
    """Query the Ollama API for available local models."""
    base = settings.ollama_base_url.rstrip("/")
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(f"{base}/api/tags")
            resp.raise_for_status()
            data = resp.json()
            models = data.get("models", [])
            return sorted(m["name"] for m in models if "name" in m)
    except httpx.HTTPError as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Could not reach Ollama at {base}: {exc}",
        ) from exc
