"""Run the backend with remote access: two listeners, one process (Phase 10.3).

    python -m app.serve --port 8001 --remote-port 8765

The desktop app keeps plain HTTP on loopback, so its loaders (media, PDF,
images) need no certificate handling. Phones get HTTPS on every interface
with the pinned self-signed certificate. Both serve the same app, so they
share one database, ingestion queue and set of background jobs; only the
loopback server runs the lifespan and handles signals.
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
from collections.abc import Generator

import uvicorn

from app.config import settings
from app.services.remote_access import ensure_certificate


class _FollowerServer(uvicorn.Server):
    """Leaves signals to the main server, which stops this one when it stops."""

    @contextlib.contextmanager
    def capture_signals(self) -> Generator[None, None, None]:
        yield


async def _serve(local: uvicorn.Server, remote: uvicorn.Server) -> None:
    main = asyncio.create_task(local.serve())
    # Phones wait until startup (migrations, recovery) has finished.
    while not local.started and not main.done():
        await asyncio.sleep(0.05)
    follower = asyncio.create_task(remote.serve()) if local.started else None
    try:
        await main
    finally:
        if follower is not None:
            remote.should_exit = True
            await follower


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--port", type=int, required=True, help="loopback HTTP port")
    parser.add_argument("--remote-port", type=int, required=True, help="HTTPS port for phones")
    args = parser.parse_args()

    if not settings.api_token:
        raise SystemExit("Remote access needs HYPATIA_API_TOKEN; refusing to start.")
    settings.remote_access_enabled = True
    settings.remote_port = args.remote_port
    cert, key = ensure_certificate(settings.data_dir)

    local = uvicorn.Server(uvicorn.Config("app.main:app", host="127.0.0.1", port=args.port))
    remote = _FollowerServer(
        uvicorn.Config(
            "app.main:app",
            host="0.0.0.0",  # reaching other devices is the point
            port=args.remote_port,
            ssl_certfile=str(cert),
            ssl_keyfile=str(key),
            lifespan="off",
        )
    )
    asyncio.run(_serve(local, remote))


if __name__ == "__main__":
    main()
