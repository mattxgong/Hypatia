"""Settings API router — read/update global application settings."""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from app.config import settings
from app.utils.logging import get_logger

logger = get_logger()

router = APIRouter(prefix="/api/settings", tags=["settings"])

VALID_PROVIDERS = ("copilot", "copilot-ollama", "anthropic", "openai", "ollama")


class SettingsRead(BaseModel):
    llm_provider: str
    llm_model: str | None


class SettingsUpdate(BaseModel):
    llm_provider: str | None = None
    llm_model: str | None = None


@router.get("", response_model=SettingsRead)
async def get_settings() -> SettingsRead:
    return SettingsRead(
        llm_provider=settings.llm_provider,
        llm_model=settings.llm_model,
    )


@router.put("", response_model=SettingsRead)
async def update_settings(body: SettingsUpdate) -> SettingsRead:
    if body.llm_provider is not None:
        if body.llm_provider not in VALID_PROVIDERS:
            from fastapi import HTTPException

            raise HTTPException(
                status_code=422,
                detail=f"Invalid provider. Must be one of: {', '.join(VALID_PROVIDERS)}",
            )
        settings.llm_provider = body.llm_provider
        logger.info("settings_updated", field="llm_provider", value=body.llm_provider)

    if body.llm_model is not None:
        settings.llm_model = body.llm_model
        logger.info("settings_updated", field="llm_model", value=body.llm_model)

    return SettingsRead(
        llm_provider=settings.llm_provider,
        llm_model=settings.llm_model,
    )
