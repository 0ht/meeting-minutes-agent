"""Shared async credential singleton for Azure SDK clients.

All modules that access Azure Blob Storage, Speech API, etc. should use
:func:`get_async_credential` instead of creating their own
``DefaultAzureCredential`` instances. This avoids leaking aiohttp sessions
and redundant IMDS / MSI discovery on every call.
"""
from __future__ import annotations

from azure.identity.aio import DefaultAzureCredential

_credential: DefaultAzureCredential | None = None


def get_async_credential() -> DefaultAzureCredential:
    """Return a process-wide async ``DefaultAzureCredential`` singleton.

    The credential is never closed — it lives for the lifetime of the
    process and is reused across all async Blob / Speech / AI calls.
    """
    global _credential  # noqa: PLW0603
    if _credential is None:
        _credential = DefaultAzureCredential()
    return _credential
