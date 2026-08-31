"""LLM availability check dependency (Task 4.9)."""

from __future__ import annotations

import asyncio
import time

from app.errors import HypatiaError, LLMUnavailableError
from app.services.llm_service import get_llm_provider

_cache_result: bool | None = None
_cache_time: float = 0.0
_CACHE_TTL_SECONDS = 30.0
_PROBE_TIMEOUT_SECONDS = 5.0


async def check_llm_available() -> None:
    """FastAPI dependency that raises LLMUnavailableError if the LLM is unreachable.

    Caches the result for 30 seconds to avoid repeated probes.
    """
    global _cache_result, _cache_time

    now = time.monotonic()
    if _cache_result is not None and (now - _cache_time) < _CACHE_TTL_SECONDS:
        if not _cache_result:
            raise LLMUnavailableError()
        return

    try:
        provider = get_llm_provider()
        await asyncio.wait_for(
            provider.complete("test", "ping", max_tokens=1),
            timeout=_PROBE_TIMEOUT_SECONDS,
        )
        _cache_result = True
        _cache_time = now
    except HypatiaError:
        _cache_result = False
        _cache_time = now
        raise
    except (TimeoutError, OSError, ValueError, RuntimeError):
        _cache_result = False
        _cache_time = now
        raise LLMUnavailableError() from None
