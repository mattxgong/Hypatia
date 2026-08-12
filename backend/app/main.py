from __future__ import annotations

import time
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import Response
from starlette.middleware.base import RequestResponseEndpoint

from app.config import settings
from app.database import engine, run_migrations
from app.routers import files as files_router
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
app.include_router(files_router.router)


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
