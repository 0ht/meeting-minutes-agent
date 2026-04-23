"""Audio transcription agent using Azure Speech Fast Transcription API.

Uses the Azure Cognitive Services Speech endpoint (available on CognitiveServices
multi-service accounts) to transcribe audio with speaker diarization.
Authentication is via Managed Identity (no keys, no SAS).

Fast Transcription reference:
  POST {endpoint}/speechtotext/transcriptions:transcribe?api-version=2024-11-15

.. note::
   This file was previously named ``content_understanding.py`` — renamed to
   match the actual Azure service (Speech Fast Transcription, not Content
   Understanding).
"""
from __future__ import annotations

import json
import logging
import re
from typing import Any, Dict, List

import httpx
from azure.identity.aio import DefaultAzureCredential

from app.config import get_settings
from app.models.schemas import ContentAnalysisResult

logger = logging.getLogger(__name__)


class SpeechTranscriptionAgent:
    """Transcribes audio using Azure Speech Fast Transcription API."""

    SPEECH_API_VERSION = "2024-11-15"

    def __init__(self) -> None:
        self.settings = get_settings()

    async def analyze(self, audio_bytes: bytes, filename: str) -> ContentAnalysisResult:
        """Transcribe *audio_bytes* and return structured content."""
        endpoint = self.settings.azure_speech_endpoint.rstrip("/")

        if not endpoint:
            logger.warning(
                "Azure Speech endpoint not configured — returning mock transcript."
            )
            return self._mock_result()

        credential = DefaultAzureCredential()
        try:
            token = await credential.get_token(
                "https://cognitiveservices.azure.com/.default"
            )
            headers = {
                "Authorization": f"Bearer {token.token}",
            }

            url = (
                f"{endpoint}/speechtotext/transcriptions:transcribe"
                f"?api-version={self.SPEECH_API_VERSION}"
            )

            # Fast Transcription accepts multipart/form-data:
            #   - audio: binary audio file
            #   - definition: JSON config for locale and diarization
            definition: dict[str, Any] = {
                "locales": ["ja-JP"],
                "diarization": {
                    "maxSpeakers": 10,
                },
            }

            # NOTE: Fast Transcription's `definition` payload does not accept
            # a `phraseList` field — supplying one returns HTTP 400
            # ``{"Definition": ["Invalid JSON format."]}``. Phrase-list style
            # biasing requires a Custom Speech model. We therefore rely on the
            # downstream LLM agents (script / minutes / terminology) to apply
            # terminology canonicalization instead.

            mime_type = self._mime_type(filename)
            files = {
                "audio": (filename, audio_bytes, mime_type),
                "definition": (None, json.dumps(definition), "application/json"),
            }

            # Long audio (e.g. 1+ hour Teams recordings) can take many minutes
            # for Fast Transcription to return. Allow up to 30 min total, with a
            # generous read timeout. Connect timeout stays short so we fail fast
            # on networking issues.
            timeout = httpx.Timeout(connect=30.0, read=1800.0, write=600.0, pool=60.0)
            async with httpx.AsyncClient(timeout=timeout) as client:
                resp = await client.post(url, files=files, headers=headers)
                if resp.status_code >= 400:
                    logger.error(
                        "Speech API error %s: %s", resp.status_code, resp.text
                    )
                resp.raise_for_status()
                data = resp.json()

        finally:
            await credential.close()

        return self._parse_result(data)

    # ── response parsing ──────────────────────────────────────────────────────

    def _parse_result(self, data: Dict[str, Any]) -> ContentAnalysisResult:
        """Parse Speech Fast Transcription response.

        Response shape:
          {
            "duration": "PT32.18S",
            "combinedPhrases": [{"text": "...", "speaker": 0}, ...],
            "phrases": [
              {"speaker": 0, "text": "...", "offset": "PT0.08S", ...},
              ...
            ]
          }
        """
        phrases: List[Dict[str, Any]] = data.get("phrases", [])

        # Build transcript with speaker labels
        transcript_lines = []
        speaker_set: dict[int, str] = {}
        for p in phrases:
            speaker_id = p.get("speaker", 0)
            if speaker_id not in speaker_set:
                speaker_set[speaker_id] = f"話者{speaker_id + 1}"
            label = speaker_set[speaker_id]
            text = p.get("text", "")
            transcript_lines.append(f"{label}：{text}")

        transcript = "\n".join(transcript_lines)
        speakers = list(speaker_set.values())

        # Parse duration from ISO 8601 format (e.g., "PT32.18S")
        duration = self._parse_iso_duration(data.get("duration", ""))

        # No topics from Speech API — the downstream agents will handle this
        return ContentAnalysisResult(
            raw_transcript=transcript or "(transcript not available)",
            speakers=speakers,
            topics=[],
            language="ja",
            duration_seconds=duration,
        )

    @staticmethod
    def _parse_iso_duration(duration_str: str) -> float | None:
        """Parse PT{hours}H{minutes}M{seconds}S format to seconds."""
        if not duration_str:
            return None
        match = re.match(
            r"PT(?:(\d+)H)?(?:(\d+)M)?(?:([\d.]+)S)?", duration_str
        )
        if not match:
            return None
        hours = float(match.group(1) or 0)
        minutes = float(match.group(2) or 0)
        seconds = float(match.group(3) or 0)
        return hours * 3600 + minutes * 60 + seconds

    @staticmethod
    def _mime_type(filename: str) -> str:
        ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else "wav"
        mapping = {
            "wav": "audio/wav",
            "mp3": "audio/mpeg",
            "mp4": "audio/mp4",
            "m4a": "audio/mp4",
            "ogg": "audio/ogg",
            "webm": "audio/webm",
            "flac": "audio/flac",
        }
        return mapping.get(ext, "audio/wav")

    @staticmethod
    def _mock_result() -> ContentAnalysisResult:
        """Return a plausible mock when credentials are not configured."""
        return ContentAnalysisResult(
            raw_transcript=(
                "話者1：本日はお集まりいただきありがとうございます。"
                "本日の議題は、新製品のロードマップと、Q3の売上目標についてです。\n"
                "話者1：田中さんより新機能のご説明をお願いします。\n"
                "話者2：はい、新機能はAIを活用した自動要約機能です。"
                "来月末のリリースを目指しています。\n"
                "話者3：スケジュールについて確認させてください。テストはいつ開始しますか？\n"
                "話者2：テストは2週間後から開始する予定です。\n"
                "話者1：ありがとうございます。次回の会議は来月15日に設定しましょう。"
            ),
            speakers=["話者1", "話者2", "話者3"],
            topics=[],
            language="ja",
            duration_seconds=300.0,
        )
