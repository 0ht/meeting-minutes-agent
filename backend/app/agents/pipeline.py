"""Agent pipeline — orchestrates the four agents in sequence.

Pipeline:
  Audio bytes
    → SpeechTranscriptionAgent   → ContentAnalysisResult
    → ScriptAgent                → ScriptResult
    → MinutesAgent               → MinutesResult
    → TerminologyAgent           → TerminologyEnhancedResult
"""
from __future__ import annotations

import asyncio
import logging
import uuid
from typing import Dict

from app.agents.speech_transcription import SpeechTranscriptionAgent
from app.agents import history_store
from app.agents.minutes_agent import MinutesAgent
from app.agents.script_agent import ScriptAgent
from app.agents.terminology_agent import TerminologyAgent
from app.models.schemas import (
    ContentAnalysisResult,
    JobResultResponse,
    JobStatus,
    MinutesResult,
    ScriptResult,
    TerminologyEnhancedResult,
)

logger = logging.getLogger(__name__)

# In-memory job store (use Redis / DB in production)
_jobs: Dict[str, JobResultResponse] = {}
_jobs_lock = asyncio.Lock()


async def _update_job(job_id: str, **kwargs: object) -> None:
    async with _jobs_lock:
        job = _jobs.get(job_id)
        if job:
            for k, v in kwargs.items():
                setattr(job, k, v)


async def create_job() -> str:
    """Create a new job entry and return its ID."""
    job_id = str(uuid.uuid4())
    async with _jobs_lock:
        _jobs[job_id] = JobResultResponse(job_id=job_id, status=JobStatus.pending)
    return job_id


async def get_job(job_id: str) -> JobResultResponse | None:
    """Retrieve a job by ID."""
    async with _jobs_lock:
        return _jobs.get(job_id)


async def run_pipeline(
    job_id: str,
    audio_bytes: bytes | None = None,
    filename: str = "audio.wav",
    transcript: ContentAnalysisResult | None = None,
) -> None:
    """Run the full agent pipeline in the background for *job_id*.

    Either *audio_bytes* or *transcript* must be supplied. If *transcript* is
    given, Step 1 (Speech Transcription) is skipped.
    """
    if transcript is None and audio_bytes is None:
        raise ValueError("Either audio_bytes or transcript must be provided.")

    await _update_job(
        job_id,
        status=JobStatus.processing,
        message="音声ファイルを解析中..." if transcript is None else "スクリプトを生成中...",
    )

    try:
        # ── Step 1: Speech Transcription ──────────────────────────────────────
        if transcript is not None:
            logger.info("[%s] Step 1: Skipped (transcript provided)", job_id)
            content = transcript
        else:
            logger.info("[%s] Step 1: Speech Transcription", job_id)
            speech_agent = SpeechTranscriptionAgent()
            content = await speech_agent.analyze(audio_bytes, filename)  # type: ignore[arg-type]
        await _update_job(
            job_id,
            content_analysis=content,
            message="スクリプトを生成中...",
        )

        # ── Step 2: Script generation ─────────────────────────────────────────
        logger.info("[%s] Step 2: Script Agent", job_id)
        script_agent = ScriptAgent()
        script: ScriptResult = await script_agent.generate(content)
        await _update_job(
            job_id,
            script=script,
            message="議事録を作成中...",
        )

        # ── Step 3: Minutes creation ──────────────────────────────────────────
        logger.info("[%s] Step 3: Minutes Agent", job_id)
        minutes_agent = MinutesAgent()
        minutes: MinutesResult = await minutes_agent.generate(script)
        await _update_job(
            job_id,
            minutes=minutes,
            message="用語を補足中...",
        )

        # ── Step 4: Terminology enrichment ────────────────────────────────────
        logger.info("[%s] Step 4: Terminology Agent", job_id)
        term_agent = TerminologyAgent()
        final: TerminologyEnhancedResult = await term_agent.enhance(minutes)
        await _update_job(
            job_id,
            final_minutes=final,
            status=JobStatus.done,
            message="完了しました",
        )
        logger.info("[%s] Pipeline complete", job_id)

        # ── Persist to history (best-effort; failure is non-fatal) ────────────
        try:
            job = await get_job(job_id)
            if job is not None:
                if transcript is not None:
                    input_kind = "transcript"
                    input_filename = "transcript.txt"
                    input_payload = (transcript.raw_transcript or "").encode("utf-8")
                else:
                    input_kind = "audio"
                    input_filename = filename or "audio.wav"
                    input_payload = audio_bytes or b""
                title = (
                    minutes.title
                    if getattr(minutes, "title", None)
                    else f"議事録 {job_id[:8]}"
                )
                await history_store.save_job(
                    job_id=job_id,
                    job_payload=job.model_dump(mode="json"),
                    input_kind=input_kind,
                    input_filename=input_filename,
                    input_bytes=input_payload,
                    title=title,
                )
        except Exception as exc:  # noqa: BLE001
            logger.warning("[%s] Failed to archive job to history: %s", job_id, exc)

    except Exception as exc:  # noqa: BLE001
        logger.exception("[%s] Pipeline failed: %s", job_id, exc)
        await _update_job(
            job_id,
            status=JobStatus.error,
            message=f"エラーが発生しました: {exc}",
        )
