"""Factory for creating the configured LLM provider instance."""

from __future__ import annotations

from app.config import Settings, settings
from app.services.ollama_manager import (
    DEFAULT_CONTEXT_LENGTH,
    DEFAULT_OLLAMA_MODEL,
    NATIVE_OLLAMA_PROVIDER,
    cached_context_length,
    is_ollama_provider,
)
from app.utils.logging import get_logger

from .llm_providers.base import LLMProvider

logger = get_logger()


def get_llm_provider(cfg: Settings | None = None) -> LLMProvider:
    """Create an LLM provider based on the application settings.

    Dispatches on ``settings.llm_provider``:
      - ``"copilot"`` (default): GitHub Copilot model catalog.
      - ``"copilot-ollama"``: Copilot SDK with BYOK Ollama backend.
      - ``"anthropic"``: Direct Anthropic API.
      - ``"openai"``: Direct OpenAI API.
      - ``"ollama"``: Ollama's native API (no Copilot CLI needed).
    """
    if cfg is None:
        cfg = settings

    provider_name = cfg.llm_provider
    model = cfg.llm_model
    temperature = cfg.llm_temperature

    if provider_name == "copilot":
        from .llm_providers.copilot_provider import CopilotProvider

        return CopilotProvider(
            model=model or cfg.copilot_model,
            temperature=temperature,
        )

    if provider_name == "copilot-ollama":
        from copilot.session import ProviderConfig

        from .llm_providers.copilot_provider import CopilotProvider

        provider_config: ProviderConfig = {
            "type": "openai",
            "base_url": f"{cfg.ollama_base_url}/v1",
        }
        return CopilotProvider(
            model=model or DEFAULT_OLLAMA_MODEL,
            provider_config=provider_config,
            temperature=temperature,
        )

    if provider_name == "anthropic":
        from .llm_providers.anthropic_provider import AnthropicProvider

        if not cfg.anthropic_api_key:
            raise ValueError("HYPATIA_ANTHROPIC_API_KEY is required for the 'anthropic' provider")
        return AnthropicProvider(
            api_key=cfg.anthropic_api_key,
            model=model or "claude-sonnet-4-20250514",
            temperature=temperature,
        )

    if provider_name == "openai":
        from .llm_providers.openai_provider import OpenAIProvider

        if not cfg.openai_api_key:
            raise ValueError("HYPATIA_OPENAI_API_KEY is required for the 'openai' provider")
        return OpenAIProvider(
            api_key=cfg.openai_api_key,
            model=model or "gpt-4o",
            temperature=temperature,
        )

    if provider_name == "ollama":
        from .llm_providers.ollama_provider import OllamaProvider

        return OllamaProvider(
            base_url=cfg.ollama_base_url,
            model=model or DEFAULT_OLLAMA_MODEL,
            temperature=temperature,
            # Ask for the same window the prompt budget was computed against,
            # otherwise Ollama serves its 4096-token default and silently drops
            # everything past it off the front of the prompt.
            num_ctx=get_context_window(cfg),
            # Ollama reports thinking in a field of its own rather than in
            # `content`. A reasoning model left to think would exhaust the
            # output budget before writing a single wiki page.
            think=False,
        )

    raise ValueError(
        f"Unknown llm_provider={provider_name!r}. "
        "Valid options: copilot, copilot-ollama, anthropic, openai, ollama"
    )


#: Ollama serves a 4096-token context by default. The native ``ollama`` provider
#: raises this per model by passing ``num_ctx``; ``copilot-ollama`` goes through
#: the Copilot SDK's OpenAI transport, which drops the option, so it is stuck
#: with whatever the server was started with.
OLLAMA_CONTEXT_WINDOW = DEFAULT_CONTEXT_LENGTH

#: Every hosted provider Hypatia supports offers at least this much context.
DEFAULT_CONTEXT_WINDOW = 128_000


def get_context_window(cfg: Settings | None = None) -> int:
    """Total context window, in tokens, of the configured model.

    Callers size their prompts against this. An explicit ``llm_context_window``
    always wins; otherwise it is inferred from the provider, since a local
    Ollama model has orders of magnitude less room than a hosted one and
    overflowing it silently drops the front of the prompt.

    For the native Ollama provider the figure is whatever
    ``ollama_manager.refresh_context_length`` resolved from ``/api/show`` at
    startup — Hypatia then asks for exactly that much via ``num_ctx``, so the
    budget and the served window agree. Before the cache is warm, or if Ollama
    was unreachable, this falls back to the server's own default.
    """
    if cfg is None:
        cfg = settings
    if cfg.llm_context_window:
        return cfg.llm_context_window
    if cfg.llm_provider == NATIVE_OLLAMA_PROVIDER:
        cached = cached_context_length(cfg.ollama_base_url, cfg.llm_model or DEFAULT_OLLAMA_MODEL)
        return cached or OLLAMA_CONTEXT_WINDOW
    if is_ollama_provider(cfg.llm_provider):
        return OLLAMA_CONTEXT_WINDOW
    return DEFAULT_CONTEXT_WINDOW
