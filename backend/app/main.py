"""FastAPI application entry point."""
from __future__ import annotations

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.routers import audio

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

app = FastAPI(
    title="Meeting Minutes Agent — Backend",
    description="音声ファイルから自動で議事録を生成するAPIサービス",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(audio.router, prefix="/api/v1")


@app.get("/health", include_in_schema=False)
async def health() -> JSONResponse:
    """Liveness probe endpoint for Container Apps."""
    return JSONResponse({"status": "ok"})

