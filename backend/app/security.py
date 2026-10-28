"""Request gate for the local backend: Host, Origin and launch-token checks.

The backend listens on loopback, but any web page in the user's browser can
still reach it: WebSockets ignore CORS, simple cross-origin POSTs run before
CORS can block the response, and DNS rebinding makes a foreign page look
same-origin. Each check below closes one of those gaps:

- ``Host`` must be in ``settings.allowed_hosts`` (defeats DNS rebinding).
- A browser ``Origin``, when sent, must match the CORS settings.
- When ``settings.api_token`` is set (the desktop app sets a fresh one per
  launch), every request except ``/health`` needs ``Authorization: Bearer``.
"""

from __future__ import annotations

import hmac
import re

from starlette.datastructures import Headers
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send
from starlette.websockets import WebSocketClose

from app.config import settings
from app.utils.logging import get_logger

logger = get_logger()

_UNAUTHENTICATED_PATHS = {"/health"}


def _host_name(host_header: str) -> str:
    """``127.0.0.1:8000`` -> ``127.0.0.1``; ``[::1]:8000`` -> ``::1``."""
    if host_header.startswith("["):
        return host_header[1 : host_header.find("]")]
    return host_header.rsplit(":", 1)[0] if host_header.count(":") == 1 else host_header


def _host_allowed(headers: Headers) -> bool:
    allowed = settings.allowed_hosts
    return "*" in allowed or _host_name(headers.get("host", "")).lower() in allowed


def _origin_allowed(headers: Headers) -> bool:
    origin = headers.get("origin")
    if origin is None:
        return True
    if origin in settings.cors_origins:
        return True
    pattern = settings.cors_origin_regex
    return bool(pattern and re.fullmatch(pattern, origin))


def _token_valid(scope: Scope, headers: Headers) -> bool:
    expected = settings.api_token
    if not expected or scope["path"] in _UNAUTHENTICATED_PATHS:
        return True
    scheme, _, supplied = headers.get("authorization", "").partition(" ")
    return scheme.lower() == "bearer" and hmac.compare_digest(supplied, expected)


class LocalAccessMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] not in ("http", "websocket"):
            await self.app(scope, receive, send)
            return

        headers = Headers(scope=scope)
        if not _host_allowed(headers):
            problem, status_code = "host", 400
        elif not _origin_allowed(headers):
            problem, status_code = "origin", 403
        elif not _token_valid(scope, headers):
            problem, status_code = "token", 401
        else:
            await self.app(scope, receive, send)
            return

        logger.warning("request_rejected", reason=problem, path=scope["path"])
        if scope["type"] == "websocket":
            # Closing before accept makes the server refuse the handshake (HTTP 403).
            await WebSocketClose(code=1008)(scope, receive, send)
            return
        response = JSONResponse(
            status_code=status_code,
            content={"detail": f"Request rejected ({problem})", "code": "HTTP_ERROR"},
        )
        await response(scope, receive, send)
