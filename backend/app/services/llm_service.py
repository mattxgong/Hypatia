"""Factory for creating the configured LLM provider instance."""

from __future__ import annotations

from app.config import Settings, settings
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
      - ``"ollama"``: OpenAI-compatible Ollama (no Copilot CLI needed).
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
            model=model or "llama3.2",
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
        from .llm_providers.openai_provider import OpenAIProvider

        return OpenAIProvider(
            base_url=f"{cfg.ollama_base_url}/v1",
            model=model or "llama3.2",
            temperature=temperature,
        )

    raise ValueError(
        f"Unknown llm_provider={provider_name!r}. "
        "Valid options: copilot, copilot-ollama, anthropic, openai, ollama"
    )
