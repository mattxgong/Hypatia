from __future__ import annotations

import time
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from starlette.middleware.base import RequestResponseEndpoint

from app import __version__
from app.config import Settings, settings
from app.database import engine, run_migrations
from app.errors import HypatiaError
from app.routers import backup as backup_router
from app.routers import chat as chat_router
from app.routers import classes as classes_router
from app.routers import files as files_router
from app.routers import settings as settings_router
from app.routers import tasks as tasks_router
from app.routers import wiki as wiki_router
from app.services.credential_store import CredentialStore
from app.services.settings_store import load_settings
from app.services.wiki_search import ensure_fts_index
from app.utils.logging import bind_context, clear_context, configure_logging, get_logger

configure_logging()
logger = get_logger()


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    settings.data_dir.mkdir(parents=True, exist_ok=True)

    persisted = load_settings(settings.data_dir)
    for key, value in persisted.items():
        if hasattr(settings, key) and getattr(settings, key) == Settings.model_fields[key].default:
            setattr(settings, key, value)

    cred_store = CredentialStore(settings.data_dir)
    _app.state.credential_store = cred_store
    _secret_keys = {"anthropic_api_key", "openai_api_key", "github_token"}
    for field in _secret_keys:
        env_val = getattr(settings, field, None)
        if env_val:
            if cred_store.get(field) is None:
                cred_store.set(field, env_val)
        else:
            stored = cred_store.get(field)
            if stored:
                setattr(settings, field, stored)

    await run_migrations()
    await ensure_fts_index(engine)
    logger.info("app_startup", data_dir=str(settings.data_dir))
    yield
    logger.info("app_shutdown")


app = FastAPI(title="Hypatia Backend", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_origin_regex=settings.cors_origin_regex,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(backup_router.router)
app.include_router(classes_router.router)
app.include_router(files_router.router)
app.include_router(wiki_router.router)
app.include_router(chat_router.router)
app.include_router(tasks_router.router)
app.include_router(settings_router.router)


@app.exception_handler(HypatiaError)
async def hypatia_error_handler(request: Request, exc: HypatiaError) -> JSONResponse:
    if exc.http_status >= 500:
        logger.exception("hypatia_error", code=exc.code.value, detail=exc.detail)
    else:
        logger.warning("hypatia_error", code=exc.code.value, detail=exc.detail)
    body: dict[str, str | None] = {"detail": exc.detail, "code": exc.code.value}
    if exc.user_action:
        body["user_action"] = exc.user_action
    return JSONResponse(status_code=exc.http_status, content=body)


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail, "code": "HTTP_ERROR"},
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.exception("unhandled_exception", exc_type=type(exc).__name__, detail=str(exc))
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error", "code": "INTERNAL_ERROR"},
    )


@app.middleware("http")
async def correlation_id_middleware(
    request: Request, call_next: RequestResponseEndpoint
) -> Response:
    correlation_id = request.headers.get("X-Correlation-Id") or str(uuid.uuid4())
    bind_context(correlation_id=correlation_id, operation=f"{request.method} {request.url.path}")
    start = time.perf_counter()
    try:
        response = await call_next(request)
    finally:
        duration_ms = round((time.perf_counter() - start) * 1000, 2)
        logger.debug("request_complete", duration_ms=duration_ms)
        clear_context()
    response.headers["X-Correlation-Id"] = correlation_id
    return response


@app.get("/health")
async def health() -> dict[str, str]:
    logger.debug("health_check")
    return {"status": "ok", "version": __version__}
