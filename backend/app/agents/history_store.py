"""Persistent history store for completed meeting-minutes jobs.

Each completed job is archived to Azure Blob Storage under a dedicated
``history`` container so that users can revisit and download past minutes
later. Authentication is via Managed Identity (``DefaultAzureCredential``);
no keys.

Layout per job::

    {container}/{job_id}/job.json     # full JobResultResponse + meta
    {container}/{job_id}/input.<ext>  # original audio file or transcript text

When Blob Storage is not configured the module degrades to a no-op so the
pipeline still works locally.
"""
from __future__ import annotations

import base64
import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Optional

from azure.core.exceptions import AzureError, ResourceExistsError, ResourceNotFoundError
from azure.storage.blob.aio import BlobServiceClient

from app.agents._credential import get_async_credential
from app.config import get_settings

logger = logging.getLogger(__name__)


_JOB_BLOB = "job.json"


def _encode_meta_value(value: str) -> str:
    """Encode a metadata value to Base64 so non-ASCII chars survive HTTP headers."""
    return base64.b64encode(value.encode("utf-8")).decode("ascii")


def _decode_meta_value(value: str) -> str:
    """Decode a Base64-encoded metadata value back to a string."""
    try:
        return base64.b64decode(value.encode("ascii")).decode("utf-8")
    except Exception:
        return value  # not encoded — return as-is for backward compat


@dataclass
class HistoryEntry:
    job_id: str
    title: str
    created_at: str          # ISO 8601 UTC
    input_kind: str          # "audio" | "transcript"
    input_filename: str
    input_blob: str          # e.g. "{job_id}/input.wav"
    has_result: bool
    transcription_mode: str = ""   # "fast" | "batch" | ""
    step_durations: dict | None = None  # {"step1": 12.3, ...}
    transcription_url: str = ""    # Batch Transcription URL (for resume)


def _container() -> str:
    return get_settings().azure_history_container or "history"


def _enabled() -> bool:
    s = get_settings()
    return bool(s.azure_storage_account_url and s.azure_history_container)


def _service() -> BlobServiceClient:
    return BlobServiceClient(
        account_url=get_settings().azure_storage_account_url,
        credential=get_async_credential(),
    )


async def _ensure_container(svc: BlobServiceClient) -> None:
    try:
        await svc.create_container(_container())
    except ResourceExistsError:
        pass
    except AzureError as exc:
        logger.warning("create_container failed (%s) — assuming it exists.", exc)


async def save_job(
    *,
    job_id: str,
    job_payload: dict[str, Any],
    input_kind: str,
    input_filename: str,
    input_bytes: bytes,
    title: str,
    transcription_mode: str = "",
    step_durations: dict[str, float] | None = None,
    transcription_url: str = "",
) -> Optional[HistoryEntry]:
    """Persist a completed job and its original input to Blob Storage."""
    if not _enabled():
        logger.info("History storage disabled — skipping save for %s.", job_id)
        return None

    created_at = datetime.now(timezone.utc).isoformat()
    ext = input_filename.rsplit(".", 1)[-1].lower() if "." in input_filename else "bin"
    input_blob_name = f"{job_id}/input.{ext}"
    job_blob_name = f"{job_id}/{_JOB_BLOB}"

    meta = {
        "job_id": job_id,
        "title": title,
        "created_at": created_at,
        "input_kind": input_kind,
        "input_filename": input_filename,
        "input_blob": input_blob_name,
        "transcription_mode": transcription_mode,
        "step_durations": step_durations,
        "transcription_url": transcription_url,
        "result": job_payload,
    }

    try:
        async with _service() as svc:
            await _ensure_container(svc)
            container = svc.get_container_client(_container())

            # Blob custom metadata for fast listing (avoids downloading job.json).
            # Values are Base64-encoded because Azure Blob metadata is sent as
            # HTTP headers which only support ASCII.
            blob_metadata = {
                "job_id": job_id,
                "title": _encode_meta_value(title[:256]),
                "created_at": created_at,
                "input_kind": input_kind,
                "input_filename": _encode_meta_value(input_filename[:256]),
                "transcription_mode": transcription_mode,
            }
            if step_durations:
                blob_metadata["step_durations"] = _encode_meta_value(
                    json.dumps(step_durations, default=str)
                )
            if transcription_url:
                blob_metadata["transcription_url"] = _encode_meta_value(transcription_url)

            # 1. Upload input.
            await container.upload_blob(
                name=input_blob_name,
                data=input_bytes,
                overwrite=True,
            )
            # 2. Upload job.json with custom metadata.
            await container.upload_blob(
                name=job_blob_name,
                data=json.dumps(meta, ensure_ascii=False, default=str).encode("utf-8"),
                overwrite=True,
                metadata=blob_metadata,
            )
        logger.info("History saved for job %s (%s).", job_id, input_filename)
        return HistoryEntry(
            job_id=job_id,
            title=title,
            created_at=created_at,
            input_kind=input_kind,
            input_filename=input_filename,
            input_blob=input_blob_name,
            has_result=not bool(transcription_url),
            transcription_mode=transcription_mode,
            step_durations=step_durations,
            transcription_url=transcription_url,
        )
    except AzureError as exc:
        logger.exception("Failed to save history for %s: %s", job_id, exc)
        return None


async def list_entries(limit: int = 100) -> list[HistoryEntry]:
    """Return up to *limit* history entries, newest first."""
    if not _enabled():
        return []

    entries: list[HistoryEntry] = []
    try:
        async with _service() as svc:
            container = svc.get_container_client(_container())
            try:
                async for blob in container.list_blobs(
                    name_starts_with="", include=["metadata"],
                ):
                    if not blob.name.endswith("/" + _JOB_BLOB):
                        continue
                    job_id = blob.name.split("/", 1)[0]
                    md = blob.metadata or {}

                    # Fast path: use blob metadata if present (new jobs).
                    if md.get("job_id"):
                        # Restore step_durations from metadata if present.
                        _sd_raw = md.get("step_durations")
                        _sd: dict | None = None
                        if _sd_raw:
                            try:
                                _sd = json.loads(_decode_meta_value(_sd_raw))
                            except (json.JSONDecodeError, Exception):
                                pass
                        # Restore transcription_url from metadata if present.
                        _tu_raw = md.get("transcription_url", "")
                        _tu = _decode_meta_value(_tu_raw) if _tu_raw else ""
                        entries.append(
                            HistoryEntry(
                                job_id=md.get("job_id", job_id),
                                title=_decode_meta_value(md.get("title", "(無題)")),
                                created_at=md.get("created_at", ""),
                                input_kind=md.get("input_kind", "audio"),
                                input_filename=_decode_meta_value(md.get("input_filename", "")),
                                input_blob=f"{job_id}/input.bin",
                                has_result=not bool(_tu),
                                transcription_mode=md.get("transcription_mode", ""),
                                step_durations=_sd,
                                transcription_url=_tu,
                            )
                        )
                        continue

                    # Fallback: download job.json for legacy entries.
                    try:
                        meta = await _load_job_meta(container, job_id)
                    except Exception as exc:  # noqa: BLE001
                        logger.warning("Skip corrupt history entry %s: %s", job_id, exc)
                        continue
                    entries.append(
                        HistoryEntry(
                            job_id=meta.get("job_id", job_id),
                            title=meta.get("title", "(無題)"),
                            created_at=meta.get("created_at", ""),
                            input_kind=meta.get("input_kind", "audio"),
                            input_filename=meta.get("input_filename", ""),
                            input_blob=meta.get("input_blob", ""),
                            has_result=bool(meta.get("result")) and not meta.get("transcription_url"),
                            transcription_mode=meta.get("transcription_mode", ""),
                            step_durations=meta.get("step_durations"),
                            transcription_url=meta.get("transcription_url", ""),
                        )
                    )
            except ResourceNotFoundError:
                return []
    except AzureError as exc:
        logger.warning("list_entries failed: %s", exc)
        return []

    entries.sort(key=lambda e: e.created_at, reverse=True)
    return entries[:limit]


async def _load_job_meta(container, job_id: str) -> dict[str, Any]:
    blob = container.get_blob_client(f"{job_id}/{_JOB_BLOB}")
    stream = await blob.download_blob()
    payload = await stream.readall()
    return json.loads(payload)


async def load_job(job_id: str) -> Optional[dict[str, Any]]:
    """Return the full archived job meta for *job_id* (or None)."""
    if not _enabled():
        return None
    try:
        async with _service() as svc:
            container = svc.get_container_client(_container())
            try:
                return await _load_job_meta(container, job_id)
            except ResourceNotFoundError:
                return None
    except AzureError as exc:
        logger.warning("load_job(%s) failed: %s", job_id, exc)
        return None


async def delete_job(job_id: str) -> bool:
    """Delete all blobs under ``{job_id}/``. Returns True if anything was deleted."""
    if not _enabled():
        return False
    deleted = False
    try:
        async with _service() as svc:
            container = svc.get_container_client(_container())
            try:
                async for blob in container.list_blobs(name_starts_with=f"{job_id}/"):
                    try:
                        await container.delete_blob(blob.name)
                        deleted = True
                    except ResourceNotFoundError:
                        pass
            except ResourceNotFoundError:
                return False
    except AzureError as exc:
        logger.warning("delete_job(%s) failed: %s", job_id, exc)
        return False
    return deleted


async def load_input(job_id: str) -> Optional[tuple[bytes, str]]:
    """Return ``(bytes, filename)`` of the original input for *job_id*."""
    meta = await load_job(job_id)
    if not meta:
        return None
    input_blob = meta.get("input_blob")
    filename = meta.get("input_filename") or "input.bin"
    if not input_blob:
        return None

    try:
        async with _service() as svc:
            container = svc.get_container_client(_container())
            blob = container.get_blob_client(input_blob)
            try:
                stream = await blob.download_blob()
                data = await stream.readall()
            except ResourceNotFoundError:
                return None
        return data, filename
    except AzureError as exc:
        logger.warning("load_input(%s) failed: %s", job_id, exc)
        return None
