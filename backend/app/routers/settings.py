"""Settings API router — read/update global application settings."""

from __future__ import annotations

import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.config import settings
from app.utils.logging import get_logger

logger = get_logger()

router = APIRouter(prefix="/api/settings", tags=["settings"])

VALID_PROVIDERS = ("copilot", "copilot-ollama", "anthropic", "openai", "ollama")


def _mask_key(key: str | None) -> str | None:
    if not key:
        return None
    if len(key) <= 8:
        return "****"
    return key[:4] + "..." + key[-4:]


class SettingsRead(BaseModel):
    llm_provider: str
    llm_model: str | None
    llm_temperature: float
    llm_max_tokens: int
    anthropic_api_key: str | None
    openai_api_key: str | None
    github_token: str | None
    ollama_base_url: str


class SettingsUpdate(BaseModel):
    llm_provider: str | None = None
    llm_model: str | None = None
    llm_temperature: float | None = None
    llm_max_tokens: int | None = None
    anthropic_api_key: str | None = None
    openai_api_key: str | None = None
    github_token: str | None = None
    ollama_base_url: str | None = None


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
    )


@router.get("", response_model=SettingsRead)
async def get_settings() -> SettingsRead:
    return _build_response()


@router.put("", response_model=SettingsRead)
async def update_settings(body: SettingsUpdate) -> SettingsRead:
    if body.llm_provider is not None:
        if body.llm_provider not in VALID_PROVIDERS:
            raise HTTPException(
                status_code=422,
                detail=f"Invalid provider. Must be one of: {', '.join(VALID_PROVIDERS)}",
            )
        settings.llm_provider = body.llm_provider
        logger.info("settings_updated", field="llm_provider", value=body.llm_provider)

    if body.llm_model is not None:
        settings.llm_model = body.llm_model if body.llm_model else None
        logger.info("settings_updated", field="llm_model", value=body.llm_model)

    if body.llm_temperature is not None:
        settings.llm_temperature = body.llm_temperature
        logger.info("settings_updated", field="llm_temperature", value=body.llm_temperature)

    if body.llm_max_tokens is not None:
        settings.llm_max_tokens = body.llm_max_tokens
        logger.info("settings_updated", field="llm_max_tokens", value=body.llm_max_tokens)

    if body.anthropic_api_key is not None:
        settings.anthropic_api_key = body.anthropic_api_key if body.anthropic_api_key else None
        logger.info("settings_updated", field="anthropic_api_key", value="[redacted]")

    if body.openai_api_key is not None:
        settings.openai_api_key = body.openai_api_key if body.openai_api_key else None
        logger.info("settings_updated", field="openai_api_key", value="[redacted]")

    if body.github_token is not None:
        settings.github_token = body.github_token if body.github_token else None
        logger.info("settings_updated", field="github_token", value="[redacted]")

    if body.ollama_base_url is not None:
        settings.ollama_base_url = body.ollama_base_url
        logger.info("settings_updated", field="ollama_base_url", value=body.ollama_base_url)

    return _build_response()


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
