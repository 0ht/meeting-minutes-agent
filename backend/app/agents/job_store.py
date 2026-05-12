"""Blob-backed job store with write-through local cache.

Replaces the previous in-memory-only ``_jobs`` dict in ``pipeline.py``.
Each job's state is persisted as ``{job_id}/state.json`` inside the
``history`` Blob container so that:

* State survives container restarts.
* Polling from any replica returns current progress (cross-replica).
* No additional Azure resources are required — uses the existing storage
  account and history container.

A local in-memory cache is maintained as a write-through layer so that
same-replica polling is near-instant.
"""
from __future__ import annotations

import json
import logging
import uuid
from collections import OrderedDict
from typing import Any

from azure.core.exceptions import AzureError, ResourceNotFoundError
from azure.storage.blob.aio import BlobServiceClient

from app.agents._credential import get_async_credential
from app.config import get_settings
from app.models.schemas import JobResultResponse, JobStatus

logger = logging.getLogger(__name__)

_STATE_BLOB = "state.json"

# ── Write-through local cache (LRU, max 200 entries) ──────────────────────────
_MAX_LOCAL = 200
_local: OrderedDict[str, JobResultResponse] = OrderedDict()


def _evict() -> None:
    """Remove oldest entries when cache exceeds _MAX_LOCAL."""
    while len(_local) > _MAX_LOCAL:
        _local.popitem(last=False)


def _container_name() -> str:
    return get_settings().azure_history_container or "history"


def _blob_enabled() -> bool:
    s = get_settings()
    return bool(s.azure_storage_account_url and s.azure_history_container)


def _svc() -> BlobServiceClient:
    return BlobServiceClient(
        account_url=get_settings().azure_storage_account_url,
        credential=get_async_credential(),
    )


async def _write_state(job_id: str, job: JobResultResponse) -> None:
    """Persist *job* to Blob Storage (best-effort)."""
    if not _blob_enabled():
        return
    blob_name = f"{job_id}/{_STATE_BLOB}"
    payload = json.dumps(
        job.model_dump(mode="json"), ensure_ascii=False, default=str,
    ).encode("utf-8")
    try:
        async with _svc() as svc:
            blob = svc.get_blob_client(container=_container_name(), blob=blob_name)
            await blob.upload_blob(payload, overwrite=True)
    except AzureError as exc:
        logger.warning("Failed to write state blob for %s: %s", job_id, exc)


async def _read_state(job_id: str) -> JobResultResponse | None:
    """Read *state.json* from Blob Storage."""
    if not _blob_enabled():
        return None
    blob_name = f"{job_id}/{_STATE_BLOB}"
    try:
        async with _svc() as svc:
            blob = svc.get_blob_client(container=_container_name(), blob=blob_name)
            stream = await blob.download_blob()
            data: dict[str, Any] = json.loads(await stream.readall())
        return JobResultResponse(**data)
    except ResourceNotFoundError:
        return None
    except (AzureError, Exception) as exc:  # noqa: BLE001
        logger.warning("Failed to read state blob for %s: %s", job_id, exc)
        return None


# ── Public API ────────────────────────────────────────────────────────────────


async def create_job() -> str:
    """Create a new job entry and return its UUID."""
    job_id = str(uuid.uuid4())
    job = JobResultResponse(job_id=job_id, status=JobStatus.pending)
    _local[job_id] = job
    _evict()
    await _write_state(job_id, job)
    return job_id


async def update_job(job_id: str, **kwargs: object) -> None:
    """Merge *kwargs* into the job and persist to Blob."""
    job = _local.get(job_id)
    if job is None:
        # Replica may have restarted — try loading from blob.
        job = await _read_state(job_id)
        if job is None:
            logger.warning("update_job: job %s not found", job_id)
            return
        _local[job_id] = job

    for k, v in kwargs.items():
        setattr(job, k, v)

    await _write_state(job_id, job)


async def get_job(job_id: str) -> JobResultResponse | None:
    """Return current job state (local cache → Blob fallback)."""
    job = _local.get(job_id)
    if job is not None:
        return job
    # Cross-replica or post-restart: read from Blob.
    job = await _read_state(job_id)
    if job is not None:
        _local[job_id] = job
        _evict()
    return job
