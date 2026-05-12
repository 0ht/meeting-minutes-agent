"""Pydantic models (request / response schemas)."""
from __future__ import annotations

from enum import Enum
from typing import List, Optional
from pydantic import BaseModel


class JobStatus(str, Enum):
    pending = "pending"
    processing = "processing"
    done = "done"
    error = "error"
    timeout = "timeout"


# ── Intermediate agent outputs ────────────────────────────────────────────────

class ContentAnalysisResult(BaseModel):
    """Structured output from the Content Understanding agent."""
    raw_transcript: str
    speakers: List[str]
    topics: List[str]
    language: Optional[str] = None
    duration_seconds: Optional[float] = None


class ScriptResult(BaseModel):
    """Clean, structured script produced by the Script agent."""
    script: str
    participants: List[str]
    agenda_items: List[str]


class MinutesResult(BaseModel):
    """Draft meeting minutes produced by the Minutes agent."""
    title: str
    date: Optional[str] = None
    participants: List[str]
    summary: str
    # New structure: agenda topics, each with a brief summary and a few detail bullets.
    # {"title": str, "summary": str, "details": [str]}
    topics: List[dict] = []
    # Follow-up tasks (Teams-style). {"task": str, "owner": str|None, "due": str|None}
    follow_up_tasks: List[dict] = []
    # Legacy fields kept for backwards compatibility.
    decisions: List[str] = []
    action_items: List[dict] = []   # {"owner": str, "task": str, "due": str|None}
    next_meeting: Optional[str] = None
    raw_markdown: str


class TerminologyEnhancedResult(BaseModel):
    """Final minutes after terminology enrichment."""
    markdown: str
    glossary: List[dict]   # {"term": str, "definition": str}


# ── Transcription mode ─────────────────────────────────────────────────────────

class TranscriptionMode(str, Enum):
    fast = "fast"
    batch = "batch"


# ── API request / response ────────────────────────────────────────────────────

class TranscriptRequest(BaseModel):
    """Request body for submitting a pre-existing transcript."""
    transcript: str
    speakers: Optional[List[str]] = None
    language: Optional[str] = "ja"


class BlobUploadRequest(BaseModel):
    """Request body for starting a pipeline from an already-uploaded blob."""
    blob_name: str
    filename: str
    transcription_mode: TranscriptionMode = TranscriptionMode.fast


class JobResponse(BaseModel):
    job_id: str
    status: JobStatus
    message: Optional[str] = None


class JobResultResponse(BaseModel):
    job_id: str
    status: JobStatus
    message: Optional[str] = None
    # Elapsed seconds per pipeline step {"step1": 12.3, "step2": 5.1, ...}
    step_durations: Optional[dict] = None
    # populated when status == "done"
    content_analysis: Optional[ContentAnalysisResult] = None
    script: Optional[ScriptResult] = None
    minutes: Optional[MinutesResult] = None
    final_minutes: Optional[TerminologyEnhancedResult] = None
