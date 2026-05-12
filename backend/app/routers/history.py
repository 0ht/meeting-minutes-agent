"""History router — list, fetch, and download archived jobs."""
from __future__ import annotations

import logging
import re
import urllib.parse
from typing import Any

from fastapi import APIRouter, BackgroundTasks, HTTPException, status
from fastapi.responses import Response

from app.agents import history_store
from app.agents.job_store import create_job
from app.agents.pipeline import run_pipeline
from app.agents.speech_transcription import SpeechTranscriptionAgent

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
    d: dict[str, Any] = {
        "job_id": e.job_id,
        "title": e.title,
        "created_at": e.created_at,
        "input_kind": e.input_kind,
        "input_filename": e.input_filename,
        "has_result": e.has_result,
        "transcription_mode": e.transcription_mode,
        "step_durations": e.step_durations,
    }
    if e.transcription_url:
        d["transcription_url"] = e.transcription_url
    return d


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


@router.get(
    "/history/{job_id}/transcription-status",
    summary="タイムアウトした Batch Transcription のステータスを確認する",
)
async def check_transcription_status(job_id: str) -> dict[str, Any]:
    _validate_job_id(job_id)
    meta = await history_store.load_job(job_id)
    if meta is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="履歴が見つかりません。")
    transcription_url = meta.get("transcription_url", "")
    if not transcription_url:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="このジョブには再開可能な文字起こしがありません。")
    agent = SpeechTranscriptionAgent()
    speech_status = await agent.check_batch_status(transcription_url)
    return {"job_id": job_id, "speech_status": speech_status}


@router.post(
    "/history/{job_id}/resume",
    summary="タイムアウトした Batch Transcription を再開する",
    status_code=status.HTTP_202_ACCEPTED,
)
async def resume_transcription(job_id: str, background_tasks: BackgroundTasks) -> dict[str, Any]:
    _validate_job_id(job_id)
    meta = await history_store.load_job(job_id)
    if meta is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="履歴が見つかりません。")
    transcription_url = meta.get("transcription_url", "")
    if not transcription_url:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="このジョブには再開可能な文字起こしがありません。")

    # Create a new job for the resumed pipeline
    new_job_id = await create_job()
    background_tasks.add_task(
        _resume_pipeline, new_job_id, job_id, transcription_url, meta,
    )
    logger.info("Resume job %s created from timed-out job %s", new_job_id, job_id)
    return {"job_id": new_job_id, "original_job_id": job_id, "message": "再開しました"}


async def _resume_pipeline(
    new_job_id: str,
    original_job_id: str,
    transcription_url: str,
    meta: dict[str, Any],
) -> None:
    """Resume a timed-out batch transcription and continue the pipeline."""
    from app.agents.job_store import update_job as _update_job
    from app.agents.minutes_agent import MinutesAgent
    from app.agents.script_agent import ScriptAgent
    from app.agents.terminology_agent import TerminologyAgent
    from app.agents.job_store import get_job
    from app.models.schemas import JobStatus
    import time

    await _update_job(new_job_id, status=JobStatus.processing, message="文字起こし結果を取得中...")
    try:
        agent = SpeechTranscriptionAgent()
        content = await agent.resume_batch(transcription_url)
        durations: dict[str, float] = {}

        await _update_job(new_job_id, content_analysis=content, message="スクリプトを生成中...")

        t0 = time.monotonic()
        script = await ScriptAgent().generate(content)
        durations["step2"] = round(time.monotonic() - t0, 1)
        await _update_job(new_job_id, script=script, step_durations=durations.copy(), message="議事録を作成中...")

        t0 = time.monotonic()
        minutes = await MinutesAgent().generate(script)
        durations["step3"] = round(time.monotonic() - t0, 1)
        await _update_job(new_job_id, minutes=minutes, step_durations=durations.copy(), message="用語を補足中...")

        t0 = time.monotonic()
        final = await TerminologyAgent().enhance(minutes)
        durations["step4"] = round(time.monotonic() - t0, 1)
        await _update_job(
            new_job_id, final_minutes=final, step_durations=durations.copy(),
            status=JobStatus.done, message="完了しました",
        )

        # Save to history
        try:
            job = await get_job(new_job_id)
            if job is not None:
                title = getattr(minutes, "title", None) or f"議事録 {new_job_id[:8]}"
                await history_store.save_job(
                    job_id=new_job_id,
                    job_payload=job.model_dump(mode="json"),
                    input_kind=meta.get("input_kind", "audio"),
                    input_filename=meta.get("input_filename", "audio.wav"),
                    input_bytes=b"",
                    title=title,
                    transcription_mode="batch",
                    step_durations=durations,
                )
        except Exception as exc:
            logger.warning("[%s] Failed to save resumed job to history: %s", new_job_id, exc)

        # Best-effort: delete the old timed-out history entry
        try:
            await history_store.delete_job(original_job_id)
        except Exception:
            pass

    except Exception as exc:
        logger.exception("[%s] Resume pipeline failed: %s", new_job_id, exc)
        await _update_job(
            new_job_id, status=JobStatus.error,
            message="再開処理中にエラーが発生しました。詳細はサーバーログを確認してください。",
        )


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
