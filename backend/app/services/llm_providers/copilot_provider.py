"""LLM provider using the GitHub Copilot SDK.

Auth is handled by the Copilot CLI (one-time ``copilot login`` browser flow)
or by setting ``GITHUB_TOKEN`` / ``COPILOT_GITHUB_TOKEN`` env var to a
fine-grained PAT with "Copilot Requests" permission. Classic PATs are not
supported.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

from copilot import CopilotClient
from copilot.session import PermissionHandler, ProviderConfig, SystemMessageReplaceConfig

from app.errors import ErrorCode, LLMProviderError
from app.utils.logging import get_logger

from .base import LLMProvider, usage_totals

logger = get_logger()


class CopilotProvider(LLMProvider):
    """Uses the github-copilot-sdk to access the Copilot model catalog or BYOK Ollama."""

    def __init__(
        self,
        model: str = "gpt-5.4",
        provider_config: ProviderConfig | None = None,
        temperature: float = 0.3,
    ) -> None:
        self._model = model
        self._provider_config = provider_config
        self._temperature = temperature
        self._client: CopilotClient | None = None

    async def _get_client(self) -> CopilotClient:
        if self._client is None:
            self._client = CopilotClient()
            await self._client.__aenter__()
        return self._client

    async def close(self) -> None:
        if self._client is not None:
            await self._client.__aexit__(None, None, None)
            self._client = None

    async def complete(
        self, system_prompt: str, user_prompt: str, *, max_tokens: int = 8192
    ) -> str:
        try:
            client = await self._get_client()
        except Exception as exc:
            logger.warning("copilot_client_error", error=str(exc))
            raise LLMProviderError(ErrorCode.LLM_UNAVAILABLE, str(exc)) from exc
        sys_msg: SystemMessageReplaceConfig = {
            "mode": "replace",
            "content": system_prompt,
        }
        session = await client.create_session(
            model=self._model,
            system_message=sys_msg,
            provider=self._provider_config,
            on_permission_request=PermissionHandler.approve_all,
        )
        try:
            response = await session.send_and_wait(user_prompt, timeout=180.0)
            if response is None:
                logger.warning("copilot_empty_response", model=self._model)
                return ""
            if hasattr(response.data, "usage") and response.data.usage:
                u = response.data.usage
                usage_totals.record(
                    self._model,
                    getattr(u, "prompt_tokens", 0) or getattr(u, "input_tokens", 0),
                    getattr(u, "completion_tokens", 0) or getattr(u, "output_tokens", 0),
                )
            return getattr(response.data, "content", "") or ""
        except Exception as exc:
            logger.warning("copilot_complete_error", error=str(exc))
            raise LLMProviderError(ErrorCode.LLM_UNAVAILABLE, str(exc)) from exc
        finally:
            await session.disconnect()

    async def stream(
        self, system_prompt: str, user_prompt: str, *, max_tokens: int = 8192
    ) -> AsyncIterator[str]:
        try:
            client = await self._get_client()
        except Exception as exc:
            logger.warning("copilot_client_error", error=str(exc))
            raise LLMProviderError(ErrorCode.LLM_UNAVAILABLE, str(exc)) from exc
        sys_msg: SystemMessageReplaceConfig = {
            "mode": "replace",
            "content": system_prompt,
        }
        session = await client.create_session(
            model=self._model,
            system_message=sys_msg,
            provider=self._provider_config,
            on_permission_request=PermissionHandler.approve_all,
        )
        try:
            if hasattr(session, "send") and callable(getattr(session, "send", None)):
                async for event in session.send(user_prompt):  # type: ignore[attr-defined]
                    if hasattr(event, "data") and hasattr(event.data, "content"):
                        chunk = event.data.content
                        if chunk:
                            yield chunk
            else:
                response = await session.send_and_wait(user_prompt, timeout=180.0)
                if response is not None:
                    content = getattr(response.data, "content", "") or ""
                    if content:
                        yield content
        except Exception as exc:
            logger.warning("copilot_stream_error", error=str(exc))
            raise LLMProviderError(ErrorCode.LLM_UNAVAILABLE, str(exc)) from exc
        finally:
            await session.disconnect()

    async def list_models(self) -> list[str]:
        try:
            client = await self._get_client()
            models = await client.list_models()
        except Exception as exc:
            logger.warning("copilot_list_models_error", error=str(exc))
            raise LLMProviderError(ErrorCode.LLM_UNAVAILABLE, str(exc)) from exc
        return [m.id for m in models]
