"""Shared Microsoft Foundry client for the agent pipeline.

All chat-completion-based agents (script, minutes, terminology) go through
this module so we have a single, cached connection to the Foundry project.

Authentication is via Managed Identity (DefaultAzureCredential). No keys.

Resolution order:
1. If ``foundry_project_endpoint`` is configured — connect via AIProjectClient
   and return its OpenAI client (recommended path).
2. Otherwise fall back to ``azure_openai_endpoint`` (legacy direct Azure OpenAI).
"""
from __future__ import annotations

import logging
from functools import lru_cache

from openai import AsyncAzureOpenAI, AsyncOpenAI
from azure.identity.aio import DefaultAzureCredential, get_bearer_token_provider
from azure.identity import DefaultAzureCredential as SyncDefaultAzureCredential
from azure.identity import get_bearer_token_provider as sync_get_bearer_token_provider

from app.config import Settings, get_settings

try:
    # azure-ai-projects (sync) — used to derive OpenAI client / project metadata.
    from azure.ai.projects import AIProjectClient
except ImportError:  # pragma: no cover
    AIProjectClient = None  # type: ignore

try:
    # azure-ai-agents (sync) — used directly for Foundry Agent / Tool API.
    # In azure-ai-projects 2.x, AIProjectClient no longer exposes ``.agents``;
    # callers must construct an AgentsClient against the project endpoint.
    from azure.ai.agents import AgentsClient
except ImportError:  # pragma: no cover
    AgentsClient = None  # type: ignore

logger = logging.getLogger(__name__)

# Cognitive Services scope — used for direct Azure OpenAI fallback.
_COGNITIVE_SCOPE = "https://cognitiveservices.azure.com/.default"
# Azure AI scope — required for Foundry project-scoped OpenAI Responses API
# (where the agent_reference parameter is recognized).
_AI_AZURE_SCOPE = "https://ai.azure.com/.default"


@lru_cache(maxsize=1)
def _credential() -> DefaultAzureCredential:
    return DefaultAzureCredential()


@lru_cache(maxsize=1)
def _token_provider():
    return get_bearer_token_provider(_credential(), _COGNITIVE_SCOPE)


@lru_cache(maxsize=1)
def _ai_token_provider():
    # AsyncOpenAI awaits the api_key callable, so use the async provider.
    return get_bearer_token_provider(_credential(), _AI_AZURE_SCOPE)


def _foundry_account_endpoint(project_endpoint: str) -> str:
    """Derive the underlying account endpoint from a Foundry project endpoint.

    Foundry project endpoint format:
        https://<account>.services.ai.azure.com/api/projects/<project>

    Azure OpenAI / chat.completions calls go to:
        https://<account>.services.ai.azure.com/
    (the AsyncAzureOpenAI client appends /openai/... itself).
    """
    # Strip the "/api/projects/<project>" suffix.
    base = project_endpoint.split("/api/projects/")[0].rstrip("/")
    return base


@lru_cache(maxsize=1)
def get_chat_client():
    """Return a cached async OpenAI client for chat / Responses API.

    When ``foundry_project_endpoint`` is set we return an :class:`AsyncOpenAI`
    pointed at ``<project_endpoint>/openai/v1/`` — this is required so the
    Responses API recognizes the ``agent`` (agent_reference) parameter.

    Otherwise we fall back to :class:`AsyncAzureOpenAI` against the legacy
    Azure OpenAI endpoint. Returns ``None`` when nothing is configured.
    """
    settings: Settings = get_settings()

    if settings.foundry_project_endpoint:
        base_url = settings.foundry_project_endpoint.rstrip("/") + "/openai/v1/"
        logger.info("Foundry chat client wired to project base_url=%s", base_url)
        return AsyncOpenAI(
            base_url=base_url,
            api_key=_ai_token_provider(),  # callable -> bearer token
        )

    if settings.azure_openai_endpoint:
        endpoint = settings.azure_openai_endpoint
        logger.info("Foundry not configured — falling back to Azure OpenAI %s", endpoint)
        return AsyncAzureOpenAI(
            azure_endpoint=endpoint,
            azure_ad_token_provider=_token_provider(),
            api_version=settings.azure_openai_api_version,
        )

    logger.warning("Neither Foundry nor Azure OpenAI endpoint configured.")
    return None


def get_chat_deployment() -> str:
    """Return the model deployment name to use for chat.completions."""
    settings = get_settings()
    return (
        settings.foundry_model_deployment
        or settings.azure_openai_deployment
        or "gpt-5.4"
    )


# ── Foundry Agents / Tools (sync AIProjectClient) ────────────────────────────


@lru_cache(maxsize=1)
def _sync_credential() -> "SyncDefaultAzureCredential":
    return SyncDefaultAzureCredential()


@lru_cache(maxsize=1)
def get_project_client():
    """Return a cached sync ``AIProjectClient`` bound to the Foundry project.

    Used for Foundry-native Agent / FunctionTool flows. Returns ``None`` when
    Foundry is not configured (callers should fall back to mock behavior).
    """
    settings: Settings = get_settings()
    if not settings.foundry_project_endpoint:
        logger.warning("FOUNDRY_PROJECT_ENDPOINT not set — AIProjectClient unavailable.")
        return None
    if AIProjectClient is None:
        logger.error("azure-ai-projects is not installed.")
        return None

    logger.info(
        "AIProjectClient bound to Foundry project %s",
        settings.foundry_project_endpoint,
    )
    return AIProjectClient(
        endpoint=settings.foundry_project_endpoint,
        credential=_sync_credential(),
    )


@lru_cache(maxsize=1)
def get_agents_client():
    """Return a cached sync ``AgentsClient`` bound to the Foundry project.

    In azure-ai-projects 2.x the project client no longer exposes ``.agents``;
    Foundry Agent / FunctionTool flows must use ``AgentsClient`` directly
    against the project endpoint. Returns ``None`` when Foundry is not
    configured (callers should fall back to mock behavior).
    """
    settings: Settings = get_settings()
    if not settings.foundry_project_endpoint:
        logger.warning("FOUNDRY_PROJECT_ENDPOINT not set — AgentsClient unavailable.")
        return None
    if AgentsClient is None:
        logger.error("azure-ai-agents is not installed.")
        return None

    logger.info(
        "AgentsClient bound to Foundry project %s",
        settings.foundry_project_endpoint,
    )
    return AgentsClient(
        endpoint=settings.foundry_project_endpoint,
        credential=_sync_credential(),
    )
