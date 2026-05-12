"""Agent pipeline — orchestrates the four agents in sequence.

Pipeline:
  Audio bytes
    → SpeechTranscriptionAgent   → ContentAnalysisResult
    → ScriptAgent                → ScriptResult
    → MinutesAgent               → MinutesResult
    → TerminologyAgent           → TerminologyEnhancedResult
"""
from __future__ import annotations

import logging
import time

from app.agents.speech_transcription import SpeechTranscriptionAgent
from app.agents import history_store
from app.agents.job_store import create_job, get_job, update_job as _update_job
from app.agents.minutes_agent import MinutesAgent
from app.agents.script_agent import ScriptAgent
from app.agents.terminology_agent import TerminologyAgent
from app.models.schemas import (
    ContentAnalysisResult,
    JobStatus,
    MinutesResult,
    ScriptResult,
    TerminologyEnhancedResult,
)

logger = logging.getLogger(__name__)


async def run_pipeline(
    job_id: str,
    audio_bytes: bytes | None = None,
    filename: str = "audio.wav",
    transcript: ContentAnalysisResult | None = None,
    transcription_mode: str = "fast",
) -> None:
    """Run the full agent pipeline in the background for *job_id*.

    Either *audio_bytes* or *transcript* must be supplied. If *transcript* is
    given, Step 1 (Speech Transcription) is skipped.
    *transcription_mode* is ``"fast"`` or ``"batch"``.
    """
    if transcript is None and audio_bytes is None:
        raise ValueError("Either audio_bytes or transcript must be provided.")

    await _update_job(
        job_id,
        status=JobStatus.processing,
        message="音声ファイルを解析中..." if transcript is None else "スクリプトを生成中...",
    )

    try:
        durations: dict[str, float] = {}

        # ── Step 1: Speech Transcription ──────────────────────────────────────
        if transcript is not None:
            logger.info("[%s] Step 1: Skipped (transcript provided)", job_id)
            content = transcript
        else:
            logger.info("[%s] Step 1: Speech Transcription (mode=%s)", job_id, transcription_mode)
            t0 = time.monotonic()
            speech_agent = SpeechTranscriptionAgent()
            content = await speech_agent.analyze(audio_bytes, filename, job_id=job_id, mode=transcription_mode)  # type: ignore[arg-type]
            durations["step1"] = round(time.monotonic() - t0, 1)
        await _update_job(
            job_id,
            content_analysis=content,
            step_durations=durations.copy(),
            message="スクリプトを生成中...",
        )

        # ── Step 2: Script generation ─────────────────────────────────────────
        logger.info("[%s] Step 2: Script Agent", job_id)
        t0 = time.monotonic()
        script_agent = ScriptAgent()
        script: ScriptResult = await script_agent.generate(content)
        durations["step2"] = round(time.monotonic() - t0, 1)
        await _update_job(
            job_id,
            script=script,
            step_durations=durations.copy(),
            message="議事録を作成中...",
        )

        # ── Step 3: Minutes creation ──────────────────────────────────────────
        logger.info("[%s] Step 3: Minutes Agent", job_id)
        t0 = time.monotonic()
        minutes_agent = MinutesAgent()
        minutes: MinutesResult = await minutes_agent.generate(script)
        durations["step3"] = round(time.monotonic() - t0, 1)
        await _update_job(
            job_id,
            minutes=minutes,
            step_durations=durations.copy(),
            message="用語を補足中...",
        )

        # ── Step 4: Terminology enrichment ────────────────────────────────────
        logger.info("[%s] Step 4: Terminology Agent", job_id)
        t0 = time.monotonic()
        term_agent = TerminologyAgent()
        final: TerminologyEnhancedResult = await term_agent.enhance(minutes)
        durations["step4"] = round(time.monotonic() - t0, 1)
        await _update_job(
            job_id,
            final_minutes=final,
            step_durations=durations.copy(),
            status=JobStatus.done,
            message="完了しました",
        )
        logger.info("[%s] Pipeline complete — durations: %s", job_id, durations)

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
                    transcription_mode=transcription_mode,
                    step_durations=durations,
                )
        except Exception as exc:  # noqa: BLE001
            logger.warning("[%s] Failed to archive job to history: %s", job_id, exc)

    except Exception as exc:  # noqa: BLE001
        logger.exception("[%s] Pipeline failed: %s", job_id, exc)
        await _update_job(
            job_id,
            status=JobStatus.error,
            message="パイプライン処理中にエラーが発生しました。詳細はサーバーログを確認してください。",
        )
