"""History router — list, fetch, and download archived jobs."""
from __future__ import annotations

import logging
import re
import urllib.parse
from typing import Any

from fastapi import APIRouter, HTTPException, status
from fastapi.responses import Response

from app.agents import history_store

logger = logging.getLogger(__name__)
router = APIRouter(tags=["history"])

_UUID_RE = re.compile(r"\A[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\Z", re.I)


def _validate_job_id(job_id: str) -> None:
    if not _UUID_RE.match(job_id):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="無効なジョブIDです。",
        )


_MIME_BY_EXT = {
    "wav": "audio/wav",
    "mp3": "audio/mpeg",
    "mp4": "audio/mp4",
    "m4a": "audio/mp4",
    "ogg": "audio/ogg",
    "webm": "audio/webm",
    "flac": "audio/flac",
    "txt": "text/plain; charset=utf-8",
    "vtt": "text/vtt; charset=utf-8",
    "srt": "application/x-subrip; charset=utf-8",
}


def _entry_to_dict(e: history_store.HistoryEntry) -> dict[str, Any]:
    return {
        "job_id": e.job_id,
        "title": e.title,
        "created_at": e.created_at,
        "input_kind": e.input_kind,
        "input_filename": e.input_filename,
        "has_result": e.has_result,
        "transcription_mode": e.transcription_mode,
        "step_durations": e.step_durations,
    }


@router.get("/history", summary="議事録の履歴一覧を返す")
async def list_history(limit: int = 100) -> dict[str, Any]:
    entries = await history_store.list_entries(limit=limit)
    return {"items": [_entry_to_dict(e) for e in entries]}


@router.get("/history/{job_id}", summary="保存済み議事録を取得する")
async def get_history(job_id: str) -> dict[str, Any]:
    _validate_job_id(job_id)
    meta = await history_store.load_job(job_id)
    if meta is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"履歴 '{job_id}' が見つかりません。",
        )
    return meta


@router.get("/history/{job_id}/input", summary="保存済み入力ファイルを取得する")
async def download_input(job_id: str) -> Response:
    _validate_job_id(job_id)
    payload = await history_store.load_input(job_id)
    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"入力ファイルが見つかりません: '{job_id}'",
        )
    data, filename = payload
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else "bin"
    mime = _MIME_BY_EXT.get(ext, "application/octet-stream")
    quoted = urllib.parse.quote(filename)
    return Response(
        content=data,
        media_type=mime,
        headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{quoted}",
        },
    )


@router.delete(
    "/history/{job_id}",
    summary="保存済み議事録を削除する",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_history(job_id: str) -> Response:
    _validate_job_id(job_id)
    deleted = await history_store.delete_job(job_id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"履歴 '{job_id}' が見つかりません。",
        )
    return Response(status_code=status.HTTP_204_NO_CONTENT)
