"""Audio router — endpoints for submitting audio and polling job status."""
from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, File, HTTPException, UploadFile, status
from fastapi.responses import JSONResponse

from app.agents.pipeline import create_job, get_job, run_pipeline
from app.config import get_settings
from app.models.schemas import JobResponse, JobResultResponse, JobStatus

logger = logging.getLogger(__name__)
router = APIRouter(tags=["audio"])

_ALLOWED_EXTENSIONS = {".wav", ".mp3", ".mp4", ".m4a", ".ogg", ".webm", ".flac"}


def _validate_audio(file: UploadFile, max_mb: int) -> None:
    ext = Path(file.filename or "").suffix.lower()
    if ext not in _ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=f"対応していないファイル形式です: {ext}。対応形式: {', '.join(_ALLOWED_EXTENSIONS)}",
        )
    # content_type check (browsers may send audio/webm;codecs=opus etc.)
    ct = (file.content_type or "").split(";")[0].strip()
    if ct and not ct.startswith("audio/") and ct not in {"application/octet-stream", "video/webm"}:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=f"対応していないコンテンツタイプです: {ct}",
        )


@router.post(
    "/audio/upload",
    response_model=JobResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="音声ファイルをアップロードして議事録生成を開始する",
)
async def upload_audio(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(..., description="音声ファイル (wav, mp3, mp4, ogg, webm, flac)"),
) -> JobResponse:
    settings = get_settings()
    _validate_audio(file, settings.max_audio_size_mb)

    audio_bytes = await file.read()
    max_bytes = settings.max_audio_size_mb * 1024 * 1024
    if len(audio_bytes) > max_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"ファイルサイズが上限 ({settings.max_audio_size_mb} MB) を超えています。",
        )

    job_id = await create_job()
    background_tasks.add_task(run_pipeline, job_id, audio_bytes, file.filename or "audio.wav")
    logger.info("Job %s created for file %s (%d bytes)", job_id, file.filename, len(audio_bytes))
    return JobResponse(job_id=job_id, status=JobStatus.pending, message="処理を開始しました")


@router.get(
    "/audio/jobs/{job_id}",
    response_model=JobResultResponse,
    summary="処理ジョブのステータスと結果を取得する",
)
async def get_job_status(job_id: str) -> JobResultResponse:
    job = await get_job(job_id)
    if job is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"ジョブ '{job_id}' が見つかりません。",
        )
    return job
