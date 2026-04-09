"""Agent pipeline — orchestrates the four agents in sequence.

Pipeline:
  Audio bytes
    → ContentUnderstandingAgent  → ContentAnalysisResult
    → ScriptAgent                → ScriptResult
    → MinutesAgent               → MinutesResult
    → TerminologyAgent           → TerminologyEnhancedResult
"""
from __future__ import annotations

import asyncio
import logging
import uuid
from typing import Dict

from app.agents.content_understanding import ContentUnderstandingAgent
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


async def run_pipeline(job_id: str, audio_bytes: bytes, filename: str) -> None:
    """Run the full agent pipeline in the background for *job_id*."""
    await _update_job(job_id, status=JobStatus.processing, message="音声ファイルを解析中...")

    try:
        # ── Step 1: Content Understanding ────────────────────────────────────
        logger.info("[%s] Step 1: Content Understanding", job_id)
        cu_agent = ContentUnderstandingAgent()
        content: ContentAnalysisResult = await cu_agent.analyze(audio_bytes, filename)
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

    except Exception as exc:  # noqa: BLE001
        logger.exception("[%s] Pipeline failed: %s", job_id, exc)
        await _update_job(
            job_id,
            status=JobStatus.error,
            message=f"エラーが発生しました: {exc}",
        )
