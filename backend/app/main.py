from __future__ import annotations

import time
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from starlette.middleware.base import RequestResponseEndpoint

from app.config import settings
from app.database import engine, run_migrations
from app.exceptions import LLMUnavailableError
from app.routers import backup as backup_router
from app.routers import chat as chat_router
from app.routers import classes as classes_router
from app.routers import files as files_router
from app.routers import settings as settings_router
from app.routers import tasks as tasks_router
from app.routers import wiki as wiki_router
from app.services.wiki_search import ensure_fts_index
from app.utils.logging import bind_context, clear_context, configure_logging, get_logger

configure_logging()
logger = get_logger()


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    settings.data_dir.mkdir(parents=True, exist_ok=True)
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


@app.exception_handler(LLMUnavailableError)
async def llm_unavailable_handler(request: Request, exc: LLMUnavailableError) -> JSONResponse:
    return JSONResponse(
        status_code=503,
        content={"detail": exc.detail, "code": "LLM_UNAVAILABLE"},
    )


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
    return {"status": "ok"}
