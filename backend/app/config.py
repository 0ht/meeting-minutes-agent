"""Application configuration — loaded from environment variables."""
from functools import lru_cache
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # ── Azure Speech (Fast Transcription) ───────────────────────────────────
    azure_speech_endpoint: str = ""

    # ── Azure AI Foundry (project endpoint + model deployment) ──────────────
    # Preferred: AIProjectClient connects to a Foundry project endpoint and
    # exposes get_openai_client() for chat.completions calls.
    foundry_project_endpoint: str = ""
    foundry_model_deployment: str = "gpt-5.4"

    # ── Azure OpenAI (legacy / fallback) ────────────────────────────
    # Kept for backwards compatibility. When foundry_project_endpoint is set
    # the agents use the Foundry project; otherwise they fall back to these.
    azure_openai_endpoint: str = ""
    azure_openai_deployment: str = "gpt-5.4"
    azure_openai_api_version: str = "2025-04-01-preview"

    # ── Azure Blob Storage (Managed Identity) ───────────────────────────────
    azure_storage_account_url: str = ""
    azure_storage_container: str = "audio-files"
    # Terminology dictionary in Blob (3-A): single source of truth consumed
    # by the lookup_terminology tool used by the script / minutes agents.
    azure_terms_container: str = "terms"
    azure_terms_blob: str = "terminology.json"
    # Persistent history of completed jobs (input file + result JSON).
    azure_history_container: str = "history"
    # Cache TTL for the terminology dictionary fetched from Blob.
    terminology_cache_ttl_seconds: int = 300

    # ── App ──────────────────────────────────────────────────────────────────
    max_audio_size_mb: int = 100
    # Comma-separated list of allowed CORS origins.
    cors_allowed_origins: str = "http://localhost:8501"
    # How long (seconds) to poll the Batch Transcription job before giving up.
    # Batch Transcription is asynchronous and can take several minutes for long
    # audio files.  Default 1800 s (30 min) covers recordings up to ~2 hours.
    speech_poll_timeout_seconds: int = 1800
    speech_poll_interval_seconds: int = 10

    class Config:
        env_file = ".env"


@lru_cache()
def get_settings() -> Settings:
    return Settings()
