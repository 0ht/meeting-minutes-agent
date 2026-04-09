"""Azure AI Content Understanding agent.

Uploads the audio file to Azure Blob Storage (or sends it as a URL) and
invokes the Azure AI Content Understanding REST API to get a raw transcript,
speaker list, and topic list.

Azure AI Content Understanding API reference:
  https://learn.microsoft.com/azure/ai-services/content-understanding/
  POST {endpoint}/contentunderstanding/analyzers/{analyzerId}:analyze
       ?api-version=2024-12-01-preview
"""
from __future__ import annotations

import asyncio
import base64
import logging
import time
from pathlib import Path
from typing import Any, Dict

import httpx

from app.config import get_settings
from app.models.schemas import ContentAnalysisResult

logger = logging.getLogger(__name__)


class ContentUnderstandingAgent:
    """Calls Azure AI Content Understanding to transcribe and structure audio."""

    API_VERSION = "2024-12-01-preview"

    def __init__(self) -> None:
        self.settings = get_settings()

    # ── public interface ──────────────────────────────────────────────────────

    async def analyze(self, audio_bytes: bytes, filename: str) -> ContentAnalysisResult:
        """Analyze *audio_bytes* and return structured content."""
        endpoint = self.settings.azure_cu_endpoint.rstrip("/")
        key = self.settings.azure_cu_key
        analyzer_id = self.settings.azure_cu_analyzer_id

        if not endpoint or not key:
            logger.warning(
                "Azure Content Understanding credentials not configured — "
                "returning mock transcript."
            )
            return self._mock_result(filename)

        # Encode audio as base64 and submit inline
        b64_audio = base64.b64encode(audio_bytes).decode()
        mime_type = self._mime_type(filename)

        url = (
            f"{endpoint}/contentunderstanding/analyzers"
            f"/{analyzer_id}:analyze?api-version={self.API_VERSION}"
        )
        headers = {
            "Ocp-Apim-Subscription-Key": key,
            "Content-Type": "application/json",
        }
        body: Dict[str, Any] = {
            "url": None,  # we use inline content
            "content": b64_audio,
            "mimeType": mime_type,
        }

        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.post(url, json=body, headers=headers)
            resp.raise_for_status()
            operation_location = resp.headers.get("Operation-Location") or resp.headers.get(
                "operation-location"
            )
            if not operation_location:
                # Synchronous result returned directly
                return self._parse_result(resp.json())
            # Poll until done
            result = await self._poll(client, operation_location, headers)

        return self._parse_result(result)

    # ── helpers ───────────────────────────────────────────────────────────────

    async def _poll(
        self,
        client: httpx.AsyncClient,
        operation_url: str,
        headers: Dict[str, str],
    ) -> Dict[str, Any]:
        timeout = self.settings.cu_poll_timeout_seconds
        interval = self.settings.cu_poll_interval_seconds
        deadline = time.monotonic() + timeout

        while time.monotonic() < deadline:
            resp = await client.get(operation_url, headers=headers)
            resp.raise_for_status()
            data = resp.json()
            status = data.get("status", "").lower()
            if status == "succeeded":
                return data
            if status in {"failed", "canceled"}:
                raise RuntimeError(
                    f"Content Understanding job failed: {data.get('error', data)}"
                )
            await asyncio.sleep(interval)

        raise TimeoutError(
            f"Content Understanding job did not finish within {timeout}s"
        )

    def _parse_result(self, data: Dict[str, Any]) -> ContentAnalysisResult:
        """Extract the fields we care about from the API response."""
        # The response shape for audio analyzers:
        # result.contents[0].fields.transcript.valueString
        # result.contents[0].fields.speakers.valueArray[].valueString
        # result.contents[0].fields.topics.valueArray[].valueString
        try:
            fields = (
                data.get("result", data)
                .get("contents", [{}])[0]
                .get("fields", {})
            )
        except (AttributeError, IndexError):
            fields = {}

        transcript = fields.get("transcript", {}).get("valueString", "")
        speakers_raw = fields.get("speakers", {}).get("valueArray", [])
        topics_raw = fields.get("topics", {}).get("valueArray", [])
        language = fields.get("language", {}).get("valueString")
        duration = fields.get("durationSeconds", {}).get("valueNumber")

        speakers = [s.get("valueString", "") for s in speakers_raw if s.get("valueString")]
        topics = [t.get("valueString", "") for t in topics_raw if t.get("valueString")]

        if not transcript:
            # Try alternate paths (e.g., transcription-only analyzers)
            transcript = data.get("result", {}).get("transcript", "")

        return ContentAnalysisResult(
            raw_transcript=transcript or "(transcript not available)",
            speakers=speakers,
            topics=topics,
            language=language,
            duration_seconds=duration,
        )

    @staticmethod
    def _mime_type(filename: str) -> str:
        ext = Path(filename).suffix.lower()
        mapping = {
            ".wav": "audio/wav",
            ".mp3": "audio/mpeg",
            ".mp4": "audio/mp4",
            ".m4a": "audio/mp4",
            ".ogg": "audio/ogg",
            ".webm": "audio/webm",
            ".flac": "audio/flac",
        }
        return mapping.get(ext, "audio/wav")

    @staticmethod
    def _mock_result(filename: str) -> ContentAnalysisResult:
        """Return a plausible mock when credentials are not configured."""
        return ContentAnalysisResult(
            raw_transcript=(
                "[MOCK] 本日はお集まりいただきありがとうございます。"
                "本日の議題は、新製品のロードマップと、Q3の売上目標についてです。"
                "田中さんより新機能のご説明をお願いします。"
                "田中：はい、新機能はAIを活用した自動要約機能です。"
                "来月末のリリースを目指しています。"
                "鈴木：スケジュールについて確認させてください。テストはいつ開始しますか？"
                "田中：テストは2週間後から開始する予定です。"
                "司会：ありがとうございます。次回の会議は来月15日に設定しましょう。"
            ),
            speakers=["司会", "田中", "鈴木"],
            topics=["新製品ロードマップ", "Q3売上目標", "AI自動要約機能", "リリーススケジュール"],
            language="ja",
            duration_seconds=300.0,
        )
