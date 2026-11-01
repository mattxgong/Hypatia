"""Request gate for the backend: Host, Origin and token checks.

The backend listens on loopback, but any web page in the user's browser can
still reach it: WebSockets ignore CORS, simple cross-origin POSTs run before
CORS can block the response, and DNS rebinding makes a foreign page look
same-origin. Each check below closes one of those gaps:

- ``Host`` must be in ``settings.allowed_hosts`` (defeats DNS rebinding).
- A browser ``Origin``, when sent, must match the CORS settings.
- When ``settings.api_token`` is set (the desktop app sets a fresh one per
  launch), every request except ``/health`` and pairing needs
  ``Authorization: Bearer`` with that token or a paired device's token.

The request's ``state.principal`` records who sent it: ``LOCAL`` for the
desktop app, or a device ID. Without a launch token (development, tests),
requests count as local.
"""

from __future__ import annotations

import hmac
import re

from fastapi import Request
from starlette.datastructures import Headers
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send
from starlette.websockets import WebSocketClose

from app.config import settings
from app.errors import ErrorCode, HypatiaError
from app.services import device_auth
from app.utils.logging import get_logger

logger = get_logger()

_UNAUTHENTICATED_PATHS = {"/health", "/api/devices/pair"}

LOCAL = "local"


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


def _bearer(headers: Headers) -> str | None:
    scheme, _, supplied = headers.get("authorization", "").partition(" ")
    return supplied if scheme.lower() == "bearer" and supplied else None


async def _principal(scope: Scope, headers: Headers) -> str | ErrorCode | None:
    """``LOCAL``, a device ID, None for an open path, or why the request is refused."""
    expected = settings.api_token
    token = _bearer(headers)
    if token and expected and hmac.compare_digest(token.encode(), expected.encode()):
        return LOCAL
    if token:
        client = scope.get("client")
        device_id = await device_auth.authenticate(token, client[0] if client else None)
        if device_id is not None:
            return str(device_id)
    if scope["path"] in _UNAUTHENTICATED_PATHS:
        return None
    if not expected:
        return LOCAL
    return ErrorCode.AUTH_INVALID if token else ErrorCode.AUTH_REQUIRED


def require_local_client(request: Request) -> None:
    """Dependency for actions only the desktop app may take, such as pairing."""
    if request.state.principal != LOCAL:
        raise HypatiaError(ErrorCode.LOCAL_CLIENT_REQUIRED)


class LocalAccessMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] not in ("http", "websocket"):
            await self.app(scope, receive, send)
            return

        headers = Headers(scope=scope)
        if not _host_allowed(headers):
            await self._reject(scope, receive, send, "host", 400, "HTTP_ERROR")
            return
        if not _origin_allowed(headers):
            await self._reject(scope, receive, send, "origin", 403, "HTTP_ERROR")
            return
        principal = await _principal(scope, headers)
        if isinstance(principal, ErrorCode):
            await self._reject(scope, receive, send, "token", 401, principal)
            return
        scope.setdefault("state", {})["principal"] = principal
        await self.app(scope, receive, send)

    @staticmethod
    async def _reject(
        scope: Scope, receive: Receive, send: Send, problem: str, status_code: int, code: str
    ) -> None:
        logger.warning("request_rejected", reason=problem, path=scope["path"])
        if scope["type"] == "websocket":
            # Closing before accept makes the server refuse the handshake (HTTP 403).
            await WebSocketClose(code=1008)(scope, receive, send)
            return
        content: dict[str, str | None] = {"detail": f"Request rejected ({problem})", "code": code}
        if isinstance(code, ErrorCode):
            error = HypatiaError(code)
            content = {"detail": error.detail, "code": code, "user_action": error.user_action}
        await JSONResponse(status_code=status_code, content=content)(scope, receive, send)
