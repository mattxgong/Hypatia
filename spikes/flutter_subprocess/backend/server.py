"""
Minimal FastAPI backend used by the Flutter subprocess spike.
The Flutter app spawns this as a child process and manages its lifecycle.
"""

from fastapi import FastAPI
from fastapi.responses import JSONResponse

app = FastAPI()


@app.get("/health")
async def health():
    return JSONResponse({"status": "ok", "service": "hypatia-backend"})


@app.get("/api/status")
async def status():
    return JSONResponse({
        "version": "0.1.0-spike",
        "uptime": "running",
    })
