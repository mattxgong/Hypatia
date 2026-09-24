"""Settings API router — read/update global application settings."""

from __future__ import annotations

import asyncio
import re

import httpx
from fastapi import APIRouter, HTTPException, Request

from app.config import settings
from app.errors import ErrorCode, HypatiaError
from app.models.schemas import (
    SettingsRead,
    SettingsUpdate,
    ValidateKeyRequest,
    ValidateKeyResponse,
)
from app.services.ollama_manager import (
    is_ollama_provider,
    refresh_if_native_ollama,
    unload_if_ollama,
)
from app.services.settings_store import (
    model_slot,
    remember_model,
    save_settings,
    saved_model,
)
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
        llm_models={p: saved_model(settings, p) for p in VALID_PROVIDERS},
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
    secret_fields: dict[str, str | None] = {}

    # Captured before the update so a model still loaded under the *previous*
    # provider can be unloaded from the server it was actually running on.
    prev_provider = settings.llm_provider
    prev_model = settings.llm_model
    prev_ollama_base_url = settings.ollama_base_url

    if body.llm_provider is not None:
        if body.llm_provider not in VALID_PROVIDERS:
            raise HTTPException(
                status_code=422,
                detail=f"Invalid provider. Must be one of: {', '.join(VALID_PROVIDERS)}",
            )
        remember_model(settings, prev_provider, settings.llm_model)
        settings.llm_provider = body.llm_provider
        settings.llm_model = settings.llm_models.get(model_slot(body.llm_provider))
        persist_fields["llm_provider"] = body.llm_provider
        persist_fields["llm_model"] = settings.llm_model
        persist_fields["llm_models"] = settings.llm_models
        logger.info("settings_updated", field="llm_provider", value=body.llm_provider)

    if body.llm_model is not None:
        settings.llm_model = body.llm_model if body.llm_model else None
        remember_model(settings, settings.llm_provider, settings.llm_model)
        persist_fields["llm_model"] = settings.llm_model
        persist_fields["llm_models"] = settings.llm_models
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
        secret_fields["anthropic_api_key"] = val
        logger.info("settings_updated", field="anthropic_api_key", value="[redacted]")

    if body.openai_api_key is not None:
        val = body.openai_api_key if body.openai_api_key else None
        settings.openai_api_key = val
        secret_fields["openai_api_key"] = val
        logger.info("settings_updated", field="openai_api_key", value="[redacted]")

    if body.github_token is not None:
        val = body.github_token if body.github_token else None
        settings.github_token = val
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
            if value is None:
                cred_store.delete(key)
            else:
                cred_store.set(key, value)

    # Switching away from an Ollama-backed provider (or to a different Ollama
    # model) leaves the old model resident until keep_alive expires; evict it now.
    if is_ollama_provider(prev_provider) and (
        settings.llm_provider != prev_provider or settings.llm_model != prev_model
    ):
        await unload_if_ollama(prev_provider, prev_model, prev_ollama_base_url)

    # The new model has a context window of its own, and prompts are sized
    # against it from the next request onwards.
    if (
        settings.llm_provider != prev_provider
        or settings.llm_model != prev_model
        or settings.ollama_base_url != prev_ollama_base_url
    ):
        await refresh_if_native_ollama(
            settings.llm_provider, settings.llm_model, settings.ollama_base_url
        )

    return _build_response()


@router.post("/unload-ollama")
async def unload_ollama() -> dict[str, bool]:
    """Evict the currently configured Ollama model from memory.

    The desktop app calls this just before it terminates the backend: on
    Windows the process is force-killed, so the shutdown hook never runs.
    """
    unloaded = await unload_if_ollama(
        settings.llm_provider, settings.llm_model, settings.ollama_base_url
    )
    return {"unloaded": unloaded}


_PROVIDER_LABELS = {
    "copilot": "GitHub Copilot",
    "copilot-ollama": "Ollama (via Copilot)",
    "anthropic": "Anthropic",
    "openai": "OpenAI",
    "ollama": "Ollama",
}

#: Local models can take a while to load into memory on the first request.
_CONNECTION_TEST_TIMEOUT = 120.0


def _describe_connection_error(exc: Exception, provider: str, model: str | None) -> str:
    """Turn a raw provider/SDK exception into a sentence a user can act on."""
    label = _PROVIDER_LABELS.get(provider, provider)
    raw = str(exc)
    text = raw.lower()
    code = exc.code if isinstance(exc, HypatiaError) else None
    ollama = is_ollama_provider(provider)

    if isinstance(exc, ValueError) and "api_key" in text:
        return f"{label} needs an API key. Enter one and try again."
    if (
        "not available" in text
        or "model_not_found" in text
        or "not_found_error" in text
        or "does not exist" in text
        or "does not have the model" in text
        or ("model" in text and "not found" in text)
    ):
        hint = f" Run `ollama pull {model}` or pick another model." if ollama and model else ""
        subject = f'The model "{model}"' if model else "The default model"
        return f"{subject} is not available on {label}. Check the model name.{hint}"
    if code == ErrorCode.LLM_AUTH_FAILED or any(
        s in text for s in ("401", "403", "unauthorized", "authentication", "api key", "x-api-key")
    ):
        if provider == "copilot":
            return (
                "GitHub sign-in failed. Run `copilot login` in a terminal, "
                "or enter a valid GitHub token."
            )
        return f"{label} rejected the API key. Check that it is correct."
    if code == ErrorCode.LLM_RATE_LIMITED or "429" in text or "rate limit" in text:
        return f"{label} is rate limiting requests. Wait a moment and try again."
    if "quota" in text or "credit balance" in text or "billing" in text:
        return f"Your {label} account has no remaining quota or credits."
    if code == ErrorCode.LLM_TIMEOUT or isinstance(exc, TimeoutError) or "timed out" in text:
        return f"{label} did not respond in time. Try again, or check your connection."
    if any(s in text for s in ("connect", "unreachable", "getaddrinfo", "name resolution")):
        if ollama:
            return "Could not reach the Ollama server. Start Ollama and check the base URL."
        return f"Could not reach {label}. Check your internet connection."

    # Drop SDK/transport prefixes such as "JSON-RPC Error -32603: Request ... failed with
    # message:" or "Error code: 500 - " so what remains is the provider's own message.
    detail = re.sub(r"^.*?failed with message:\s*", "", raw, flags=re.DOTALL)
    lines = re.sub(r"^Error code: \d+ - ", "", detail).strip().splitlines()
    summary = lines[0] if lines else type(exc).__name__
    if len(summary) > 200:
        summary = summary[:197] + "..."
    return f"Could not connect to {label}: {summary}"


@router.post("/validate-key", response_model=ValidateKeyResponse)
async def validate_key(body: ValidateKeyRequest) -> ValidateKeyResponse:
    """Test a provider configuration, which may be unsaved, with a tiny completion."""
    from app.services.llm_service import get_llm_provider

    temp_cfg = settings.model_copy(deep=True)
    temp_cfg.llm_provider = body.provider
    temp_cfg.llm_model = saved_model(settings, body.provider)

    if body.api_key is not None:
        key = body.api_key or None
        if body.provider == "anthropic":
            temp_cfg.anthropic_api_key = key
        elif body.provider == "openai":
            temp_cfg.openai_api_key = key
        elif body.provider == "copilot":
            temp_cfg.github_token = key
    if body.model is not None:
        temp_cfg.llm_model = body.model or None
    if body.ollama_base_url is not None:
        temp_cfg.ollama_base_url = body.ollama_base_url

    provider = None
    try:
        provider = get_llm_provider(cfg=temp_cfg)
        await asyncio.wait_for(
            provider.complete("test", "Say hello.", max_tokens=5),
            timeout=_CONNECTION_TEST_TIMEOUT,
        )
        return ValidateKeyResponse(valid=True)
    except Exception as exc:  # noqa: BLE001
        model = temp_cfg.llm_model
        logger.warning(
            "connection_test_failed", provider=body.provider, model=model, error=str(exc)
        )
        return ValidateKeyResponse(
            valid=False, error=_describe_connection_error(exc, body.provider, model)
        )
    finally:
        close = getattr(provider, "close", None)
        if close is not None:
            await close()


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
