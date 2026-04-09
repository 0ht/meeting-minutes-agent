"""Application configuration — loaded from environment variables."""
from functools import lru_cache
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # ── Azure AI Content Understanding ──────────────────────────────────────
    azure_cu_endpoint: str = ""
    azure_cu_key: str = ""
    # Pre-built analyzer for audio. Use "prebuilt-audioAnalyzer" or a custom one.
    azure_cu_analyzer_id: str = "prebuilt-audioAnalyzer"

    # ── Azure OpenAI ─────────────────────────────────────────────────────────
    azure_openai_endpoint: str = ""
    azure_openai_key: str = ""
    azure_openai_deployment: str = "gpt-4o"
    azure_openai_api_version: str = "2024-02-01"

    # ── Azure Blob Storage ───────────────────────────────────────────────────
    azure_storage_connection_string: str = ""
    azure_storage_container: str = "audio-files"

    # ── App ──────────────────────────────────────────────────────────────────
    max_audio_size_mb: int = 100
    # How long (seconds) to poll Content Understanding before giving up
    cu_poll_timeout_seconds: int = 300
    cu_poll_interval_seconds: int = 5

    class Config:
        env_file = ".env"


@lru_cache()
def get_settings() -> Settings:
    return Settings()
