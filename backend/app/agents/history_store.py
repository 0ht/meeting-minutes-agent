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

import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Optional

from azure.core.exceptions import AzureError, ResourceExistsError, ResourceNotFoundError
from azure.identity.aio import DefaultAzureCredential
from azure.storage.blob.aio import BlobServiceClient

from app.config import get_settings

logger = logging.getLogger(__name__)


_JOB_BLOB = "job.json"


@dataclass
class HistoryEntry:
    job_id: str
    title: str
    created_at: str          # ISO 8601 UTC
    input_kind: str          # "audio" | "transcript"
    input_filename: str
    input_blob: str          # e.g. "{job_id}/input.wav"
    has_result: bool


def _container() -> str:
    return get_settings().azure_history_container or "history"


def _enabled() -> bool:
    s = get_settings()
    return bool(s.azure_storage_account_url and s.azure_history_container)


async def _service() -> tuple[BlobServiceClient, DefaultAzureCredential]:
    cred = DefaultAzureCredential()
    svc = BlobServiceClient(
        account_url=get_settings().azure_storage_account_url, credential=cred
    )
    return svc, cred


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
        "result": job_payload,
    }

    svc, cred = await _service()
    try:
        async with svc:
            await _ensure_container(svc)
            container = svc.get_container_client(_container())

            # 1. Upload input.
            await container.upload_blob(
                name=input_blob_name,
                data=input_bytes,
                overwrite=True,
            )
            # 2. Upload job.json.
            await container.upload_blob(
                name=job_blob_name,
                data=json.dumps(meta, ensure_ascii=False, default=str).encode("utf-8"),
                overwrite=True,
            )
        logger.info("History saved for job %s (%s).", job_id, input_filename)
        return HistoryEntry(
            job_id=job_id,
            title=title,
            created_at=created_at,
            input_kind=input_kind,
            input_filename=input_filename,
            input_blob=input_blob_name,
            has_result=True,
        )
    except AzureError as exc:
        logger.exception("Failed to save history for %s: %s", job_id, exc)
        return None
    finally:
        await cred.close()


async def list_entries(limit: int = 100) -> list[HistoryEntry]:
    """Return up to *limit* history entries, newest first."""
    if not _enabled():
        return []

    svc, cred = await _service()
    entries: list[HistoryEntry] = []
    try:
        async with svc:
            container = svc.get_container_client(_container())
            try:
                async for blob in container.list_blobs(name_starts_with=""):
                    if not blob.name.endswith("/" + _JOB_BLOB):
                        continue
                    job_id = blob.name.split("/", 1)[0]
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
                            has_result=bool(meta.get("result")),
                        )
                    )
            except ResourceNotFoundError:
                return []
    except AzureError as exc:
        logger.warning("list_entries failed: %s", exc)
        return []
    finally:
        await cred.close()

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
    svc, cred = await _service()
    try:
        async with svc:
            container = svc.get_container_client(_container())
            try:
                return await _load_job_meta(container, job_id)
            except ResourceNotFoundError:
                return None
    except AzureError as exc:
        logger.warning("load_job(%s) failed: %s", job_id, exc)
        return None
    finally:
        await cred.close()


async def delete_job(job_id: str) -> bool:
    """Delete all blobs under ``{job_id}/``. Returns True if anything was deleted."""
    if not _enabled():
        return False
    svc, cred = await _service()
    deleted = False
    try:
        async with svc:
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
    finally:
        await cred.close()
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

    svc, cred = await _service()
    try:
        async with svc:
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
    finally:
        await cred.close()
