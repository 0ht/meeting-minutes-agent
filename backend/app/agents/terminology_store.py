"""Terminology dictionary store — Blob-first with local fallback (3-A).

Loads ``terminology.json`` from Azure Blob Storage using Managed Identity,
caches it in-process for ``terminology_cache_ttl_seconds`` (default 5 min),
and falls back to the bundled local file when Blob is unavailable or
unconfigured.

Schema::

    {
      "phrase_list": ["MCP", "Azure OpenAI", ...],
      "term_mappings": [
        {
          "variants": ["えむしーぴー", "MCP"],
          "canonical": "MCP",
          "definition": "Model Context Protocol ...",
          "category": "tech"
        },
        ...
      ]
    }

The same data is intended to feed (1) Speech Phrase List, (2) the
``lookup_terminology`` tool used by the agents, and (3) inline annotation in
the minutes — implementing the "single source of truth" pattern from
``docs/custom-terminology-options.md``.
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
from pathlib import Path
from typing import Any

from azure.core.exceptions import AzureError
from azure.storage.blob.aio import BlobServiceClient

from app.agents._credential import get_async_credential
from app.config import get_settings

logger = logging.getLogger(__name__)

_LOCAL_PATH = Path(__file__).parent.parent / "data" / "terminology.json"


class _Cache:
    data: dict[str, Any] | None = None
    expires_at: float = 0.0


_cache = _Cache()
_lock = asyncio.Lock()


def _load_local() -> dict[str, Any]:
    try:
        with _LOCAL_PATH.open(encoding="utf-8") as f:
            return _normalize(json.load(f))
    except FileNotFoundError:
        logger.warning("Local terminology.json not found.")
        return {"phrase_list": [], "term_mappings": []}


def _normalize(raw: dict[str, Any]) -> dict[str, Any]:
    """Accept both the new schema and the legacy {industry: {...}} schema."""
    if "term_mappings" in raw or "phrase_list" in raw:
        return {
            "phrase_list": list(raw.get("phrase_list", [])),
            "term_mappings": list(raw.get("term_mappings", [])),
        }
    # Legacy: {category: {term: definition, ...}}
    mappings: list[dict[str, Any]] = []
    for category, terms in raw.items():
        if not isinstance(terms, dict):
            continue
        for term, definition in terms.items():
            mappings.append(
                {
                    "variants": [term],
                    "canonical": term,
                    "definition": definition,
                    "category": category,
                }
            )
    return {"phrase_list": [m["canonical"] for m in mappings], "term_mappings": mappings}


async def _load_from_blob() -> dict[str, Any] | None:
    settings = get_settings()
    if not (settings.azure_storage_account_url and settings.azure_terms_container):
        return None

    try:
        async with BlobServiceClient(
            account_url=settings.azure_storage_account_url,
            credential=get_async_credential(),
        ) as svc:
            blob = svc.get_blob_client(
                container=settings.azure_terms_container,
                blob=settings.azure_terms_blob,
            )
            stream = await blob.download_blob()
            payload = await stream.readall()
        return _normalize(json.loads(payload))
    except AzureError as exc:
        logger.warning("Failed to load terminology from Blob (%s) — using local copy.", exc)
        return None


async def get_terminology() -> dict[str, Any]:
    """Return the (cached) terminology dictionary."""
    now = time.monotonic()
    if _cache.data is not None and now < _cache.expires_at:
        return _cache.data

    async with _lock:
        # Re-check inside the lock to avoid duplicate fetches.
        now = time.monotonic()
        if _cache.data is not None and now < _cache.expires_at:
            return _cache.data

        data = await _load_from_blob()
        if data is None:
            data = _load_local()

        _cache.data = data
        _cache.expires_at = now + get_settings().terminology_cache_ttl_seconds
        logger.info(
            "Terminology loaded: %d mappings, %d phrase-list entries.",
            len(data.get("term_mappings", [])),
            len(data.get("phrase_list", [])),
        )
        return data


def lookup(terms: list[str]) -> list[dict[str, Any]]:
    """Look up *terms* against the cached dictionary.

    Matches by exact (case-insensitive) hit against any variant or the
    canonical name. Returns one result per matched mapping with the field
    set ``{requested, canonical, definition, variants, category}``.
    """
    data = _cache.data or {"term_mappings": []}
    mappings = data.get("term_mappings", [])

    # Build a lookup index once per cache refresh would be ideal; but this
    # path runs at most a handful of times per request so a linear scan is
    # acceptable for dictionaries up to a few thousand entries.
    results: list[dict[str, Any]] = []
    seen: set[str] = set()
    for term in terms:
        needle = term.strip().lower()
        if not needle:
            continue
        for mapping in mappings:
            haystack = {mapping["canonical"].lower()} | {
                v.lower() for v in mapping.get("variants", [])
            }
            if needle in haystack and mapping["canonical"] not in seen:
                results.append(
                    {
                        "requested": term,
                        "canonical": mapping["canonical"],
                        "definition": mapping["definition"],
                        "variants": mapping.get("variants", []),
                        "category": mapping.get("category"),
                    }
                )
                seen.add(mapping["canonical"])
                break
    return results


async def get_phrase_list() -> list[str]:
    """Return the Speech Phrase List slice of the dictionary."""
    data = await get_terminology()
    return list(data.get("phrase_list", []))
