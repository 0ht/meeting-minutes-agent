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
    decisions: List[str]
    action_items: List[dict]   # {"owner": str, "task": str, "due": str|None}
    next_meeting: Optional[str] = None
    raw_markdown: str


class TerminologyEnhancedResult(BaseModel):
    """Final minutes after terminology enrichment."""
    markdown: str
    glossary: List[dict]   # {"term": str, "definition": str}


# ── API request / response ────────────────────────────────────────────────────

class JobResponse(BaseModel):
    job_id: str
    status: JobStatus
    message: Optional[str] = None


class JobResultResponse(BaseModel):
    job_id: str
    status: JobStatus
    message: Optional[str] = None
    # populated when status == "done"
    content_analysis: Optional[ContentAnalysisResult] = None
    script: Optional[ScriptResult] = None
    minutes: Optional[MinutesResult] = None
    final_minutes: Optional[TerminologyEnhancedResult] = None
