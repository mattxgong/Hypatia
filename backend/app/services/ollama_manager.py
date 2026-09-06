"""Release Ollama models that Hypatia is no longer using, and inspect them.

Hypatia talks to an Ollama server over HTTP rather than spawning it, so there is
no child process to stop. What holds memory is the *model*: Ollama keeps the
weights resident for ``keep_alive`` (5 minutes by default) after the last
request. Sending any request with ``keep_alive: 0`` evicts the model
immediately, which is what these helpers do when the provider changes or the
backend shuts down.

This module also answers "how much context can this model actually take?".
Ollama serves every model in a 4096-token window unless told otherwise, even
though the model itself was trained for far more — granite4.2:3b reports
131072. ``/api/show`` exposes the real figure, so Hypatia reads it once and
passes the result back as ``num_ctx`` on each request instead of asking the
user to set OLLAMA_CONTEXT_LENGTH by hand.
"""

from __future__ import annotations

from dataclasses import dataclass

import httpx

from app.utils.logging import get_logger

logger = get_logger()

#: Providers in app/services/llm_service.py that route through an Ollama server.
OLLAMA_PROVIDERS = ("ollama", "copilot-ollama")

#: The one that talks to Ollama directly. ``copilot-ollama`` goes through the
#: Copilot SDK's OpenAI transport, which drops ``num_ctx``, so context
#: auto-sizing applies to this provider only.
NATIVE_OLLAMA_PROVIDER = "ollama"

#: Model llm_service falls back to when llm_model is unset.
DEFAULT_OLLAMA_MODEL = "llama3.2"

#: What Ollama serves when the server sets no OLLAMA_CONTEXT_LENGTH.
DEFAULT_CONTEXT_LENGTH = 4096

#: Ceiling on the context Hypatia will ask for on its own. Ollama allocates a
#: KV cache proportional to num_ctx, so requesting a modern model's full 128k
#: would reserve gigabytes and spill the weights onto the CPU. Users who know
#: their hardware can override with HYPATIA_LLM_CONTEXT_WINDOW.
MAX_AUTO_CONTEXT_LENGTH = 32_768


@dataclass(frozen=True)
class OllamaModelInfo:
    """What ``/api/show`` tells us about a model."""

    #: Context length the model was trained for, not the one it is served with.
    context_length: int | None
    #: Whether the model emits chain-of-thought unless asked not to.
    thinks: bool


#: Context length chosen per (base_url, model). Populated by
#: ``refresh_context_length`` at startup and on settings changes, and read
#: synchronously by llm_service.get_context_window when sizing prompts.
_context_lengths: dict[tuple[str, str], int] = {}


def is_ollama_provider(provider: str | None) -> bool:
    return provider in OLLAMA_PROVIDERS


async def show_model(base_url: str, model: str) -> OllamaModelInfo | None:
    """Read a model's trained context length and capabilities from Ollama.

    Returns None if Ollama is unreachable or does not have the model, since
    every caller has a usable fallback and none of them should fail on it.
    """
    url = f"{base_url.rstrip('/')}/api/show"
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(url, json={"model": model})
            response.raise_for_status()
            data = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        logger.warning("ollama_show_failed", model=model, error=str(exc))
        return None

    # The key is namespaced by architecture — "granite.context_length",
    # "qwen2.context_length" — so match on the suffix rather than guessing.
    context_length: int | None = None
    for key, value in (data.get("model_info") or {}).items():
        if key.endswith(".context_length") and isinstance(value, int):
            context_length = value
            break

    capabilities = data.get("capabilities") or []
    return OllamaModelInfo(context_length=context_length, thinks="thinking" in capabilities)


def choose_context_length(model_max: int | None) -> int:
    """Context to request for a model whose trained maximum is ``model_max``."""
    if not model_max or model_max <= 0:
        return DEFAULT_CONTEXT_LENGTH
    return max(min(model_max, MAX_AUTO_CONTEXT_LENGTH), DEFAULT_CONTEXT_LENGTH)


def cached_context_length(base_url: str, model: str) -> int | None:
    """Context length already resolved for this model, if any."""
    return _context_lengths.get((base_url.rstrip("/"), model))


def clear_context_cache() -> None:
    _context_lengths.clear()


async def refresh_context_length(base_url: str, model: str) -> int:
    """Resolve and cache how much context to ask ``model`` for.

    Falls back to Ollama's 4096-token default when the server cannot be reached,
    which is what the model would have been served with anyway.
    """
    info = await show_model(base_url, model)
    chosen = choose_context_length(info.context_length if info else None)
    _context_lengths[(base_url.rstrip("/"), model)] = chosen

    logger.info(
        "ollama_context_resolved",
        model=model,
        model_max=info.context_length if info else None,
        chosen=chosen,
        thinks=info.thinks if info else None,
    )
    return chosen


async def refresh_if_native_ollama(provider: str | None, model: str | None, base_url: str) -> None:
    """Warm the context cache when ``provider`` is the direct Ollama one."""
    if provider != NATIVE_OLLAMA_PROVIDER:
        return
    await refresh_context_length(base_url, model or DEFAULT_OLLAMA_MODEL)


async def unload_model(base_url: str, model: str) -> bool:
    """Ask Ollama to evict ``model`` from memory. Returns whether it worked.

    Best-effort: an unreachable or already-stopped Ollama is logged and
    reported as False rather than raised, since callers are shutdown and
    settings paths that must not fail because of it.
    """
    url = f"{base_url.rstrip('/')}/api/generate"
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(url, json={"model": model, "keep_alive": 0})
            response.raise_for_status()
    except httpx.HTTPError as exc:
        logger.warning("ollama_unload_failed", model=model, error=str(exc))
        return False

    logger.info("ollama_unloaded", model=model)
    return True


async def unload_if_ollama(provider: str | None, model: str | None, base_url: str) -> bool:
    """Unload ``model`` if ``provider`` is Ollama-backed; otherwise do nothing."""
    if not is_ollama_provider(provider):
        return False
    return await unload_model(base_url, model or DEFAULT_OLLAMA_MODEL)
