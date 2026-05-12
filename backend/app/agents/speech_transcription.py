"""Audio transcription agent supporting Fast and Batch Transcription APIs.

Both modes share the same flow:
  1. Upload audio to Azure Blob Storage
  2. Pass the Blob URL to the Speech API

- **Fast Transcription** (default): synchronous — passes ``audioUrl`` in the
  definition JSON; result is returned in the same HTTP response.
- **Batch Transcription**: asynchronous — passes ``contentUrls`` in the
  submit body; poll until complete, then download the result.

Authentication is via Managed Identity (no keys, no SAS).

References:
  Fast:  POST {endpoint}/speechtotext/transcriptions:transcribe?api-version=2025-10-15
  Batch: POST {endpoint}/speechtotext/transcriptions:submit?api-version=2025-10-15
"""
from __future__ import annotations

import asyncio
import io
import json
import logging
import re
import uuid
from typing import Any, Awaitable, Callable, Dict, List

import httpx
from azure.storage.blob.aio import BlobServiceClient
from pydub import AudioSegment

from app.agents._credential import get_async_credential
from app.config import get_settings
from app.models.schemas import ContentAnalysisResult

logger = logging.getLogger(__name__)


class BatchTranscriptionTimeout(TimeoutError):
    """Raised when Batch Transcription polling exceeds the configured timeout.

    Carries the ``transcription_url`` so callers can resume polling later.
    """

    def __init__(self, message: str, transcription_url: str) -> None:
        super().__init__(message)
        self.transcription_url = transcription_url


class SpeechTranscriptionAgent:
    """Transcribes audio via Fast or Batch Transcription API."""

    API_VERSION = "2025-10-15"

    def __init__(self) -> None:
        self.settings = get_settings()

    # ── public API ────────────────────────────────────────────────────────────

    async def analyze(
        self,
        audio_bytes: bytes,
        filename: str,
        *,
        job_id: str | None = None,
        mode: str = "fast",
    ) -> ContentAnalysisResult:
        """Upload audio to Blob, then transcribe via Fast or Batch API.

        Both modes first upload to Blob and pass the Blob URL to the API.

        Args:
            mode: ``"fast"`` (default) or ``"batch"``.
        """
        endpoint = self.settings.azure_speech_endpoint.rstrip("/")

        if not endpoint:
            logger.warning(
                "Azure Speech endpoint not configured — returning mock transcript."
            )
            return self._mock_result()

        # Normalize audio to 16 kHz / 16-bit / mono WAV
        audio_bytes, filename = self._normalize_audio(audio_bytes, filename)

        # 1. Upload audio to Blob Storage (required for both modes)
        blob_url = await self._upload_to_blob(audio_bytes, filename, job_id=job_id)
        if not blob_url:
            raise RuntimeError(
                "Blob upload failed. AZURE_STORAGE_ACCOUNT_URL must be configured."
            )

        # 2. Transcribe via the selected mode
        if mode == "batch":
            return await self._transcribe_batch(endpoint, blob_url, job_id)
        else:
            return await self._transcribe_fast(endpoint, blob_url)

    async def analyze_from_blob(
        self,
        blob_name: str,
        filename: str,
        *,
        job_id: str | None = None,
        mode: str = "fast",
    ) -> ContentAnalysisResult:
        """Transcribe audio that is already uploaded to Blob Storage.

        The blob is downloaded, normalized to WAV, re-uploaded, and then
        transcribed via the Speech API — same as ``analyze`` but skips the
        initial upload from the caller's memory.
        """
        endpoint = self.settings.azure_speech_endpoint.rstrip("/")
        if not endpoint:
            logger.warning("Azure Speech endpoint not configured — returning mock transcript.")
            return self._mock_result()

        account_url = self.settings.azure_storage_account_url
        container = self.settings.azure_storage_container
        if not account_url:
            raise RuntimeError("AZURE_STORAGE_ACCOUNT_URL is not configured.")

        # Download from Blob
        cred = get_async_credential()
        svc = BlobServiceClient(account_url=account_url, credential=cred)
        async with svc:
            blob_client = svc.get_blob_client(container=container, blob=blob_name)
            download = await blob_client.download_blob()
            audio_bytes = await download.readall()

        logger.info("Downloaded blob %s (%d bytes) for transcription", blob_name, len(audio_bytes))

        # Normalize to WAV and re-upload
        audio_bytes, filename = self._normalize_audio(audio_bytes, filename)
        blob_url = await self._upload_to_blob(audio_bytes, filename, job_id=job_id)
        if not blob_url:
            raise RuntimeError("Blob re-upload failed after normalization.")

        if mode == "batch":
            return await self._transcribe_batch(endpoint, blob_url, job_id)
        else:
            return await self._transcribe_fast(endpoint, blob_url)

    # ── Blob upload (archival) ────────────────────────────────────────────────

    async def _upload_to_blob(
        self,
        audio_bytes: bytes,
        filename: str,
        *,
        job_id: str | None = None,
    ) -> str:
        """Upload audio to the audio-files container and return the blob URL.

        Raises ``RuntimeError`` if the storage account is not configured.
        """
        account_url = self.settings.azure_storage_account_url
        container = self.settings.azure_storage_container  # "audio-files"
        if not account_url:
            raise RuntimeError("AZURE_STORAGE_ACCOUNT_URL is not configured.")

        ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else "wav"
        blob_name = f"{job_id or uuid.uuid4()}/input.{ext}"

        cred = get_async_credential()
        svc = BlobServiceClient(account_url=account_url, credential=cred)
        async with svc:
            blob_client = svc.get_blob_client(container=container, blob=blob_name)
            await blob_client.upload_blob(audio_bytes, overwrite=True)
            blob_url = blob_client.url
            logger.info("Audio uploaded to Blob: %s", blob_url)
            return blob_url

    # ── Fast Transcription ────────────────────────────────────────────────────

    async def _transcribe_fast(
        self,
        endpoint: str,
        blob_url: str,
    ) -> ContentAnalysisResult:
        """Synchronous Fast Transcription using ``audioUrl`` (Blob URL)."""
        credential = get_async_credential()
        token = await credential.get_token(
            "https://cognitiveservices.azure.com/.default"
        )

        url = (
            f"{endpoint}/speechtotext/transcriptions:transcribe"
            f"?api-version={self.API_VERSION}"
        )

        definition = json.dumps({
            "locales": ["ja-JP"],
            "diarization": {"maxSpeakers": 10, "enabled": True},
            "audioUrl": blob_url,
        })

        # multipart/form-data — "definition" as a form field (no audio part)
        # httpx sends correct Content-Type with boundary when using `files=`
        timeout = httpx.Timeout(connect=30.0, read=1800.0, write=60.0, pool=60.0)
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post(
                url,
                files={"definition": (None, definition, "application/json")},
                headers={"Authorization": f"Bearer {token.token}"},
            )
            if resp.status_code >= 400:
                logger.error("Fast Transcription error %s: %s", resp.status_code, resp.text)
            resp.raise_for_status()
            data = resp.json()

        return self._parse_fast_result(data)

    # ── Batch Transcription ───────────────────────────────────────────────────

    async def _transcribe_batch(
        self,
        endpoint: str,
        blob_url: str,
        job_id: str | None,
    ) -> ContentAnalysisResult:
        """Asynchronous Batch Transcription (submit → poll → fetch)."""
        credential = get_async_credential()

        async def _get_headers() -> dict[str, str]:
            token = await credential.get_token(
                "https://cognitiveservices.azure.com/.default"
            )
            return {
                "Authorization": f"Bearer {token.token}",
                "Content-Type": "application/json",
            }

        headers = await _get_headers()

        # Submit
        transcription_url = await self._batch_submit(endpoint, headers, blob_url, job_id)

        # Poll (refreshes token periodically)
        result_data = await self._batch_poll(_get_headers, transcription_url)

        # Best-effort cleanup
        headers = await _get_headers()
        await self._batch_delete(headers, transcription_url)

        return self._parse_batch_result(result_data)

    async def _batch_submit(
        self, endpoint: str, headers: dict, blob_url: str, job_id: str | None,
    ) -> str:
        """POST /speechtotext/transcriptions:submit → return ``self`` URL."""
        url = (
            f"{endpoint}/speechtotext/transcriptions:submit"
            f"?api-version={self.API_VERSION}"
        )
        body = {
            "contentUrls": [blob_url],
            "locale": "ja-JP",
            "displayName": f"meeting-minutes-{job_id or 'unknown'}",
            "properties": {
                "diarizationEnabled": True,
                "diarization": {
                    "minCount": 1,
                    "maxCount": 10,
                },
                "wordLevelTimestampsEnabled": False,
                "timeToLiveHours": 6,
            },
        }
        timeout = httpx.Timeout(connect=30.0, read=60.0, write=30.0, pool=30.0)
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post(url, json=body, headers=headers)
            if resp.status_code >= 400:
                logger.error("Batch submit error %s: %s", resp.status_code, resp.text)
            resp.raise_for_status()
            data = resp.json()
        self_url: str = data.get("self", "")
        logger.info("Batch Transcription submitted: %s (status=%s)", self_url, data.get("status"))
        return self_url

    async def _batch_poll(
        self,
        get_headers: Callable[[], Awaitable[dict[str, str]]],
        transcription_url: str,
    ) -> dict[str, Any]:
        """Poll until Succeeded/Failed, then fetch result file.

        *get_headers* is called every 5 minutes to refresh the Bearer token.
        """
        poll_timeout = self.settings.speech_poll_timeout_seconds
        poll_interval = self.settings.speech_poll_interval_seconds
        elapsed = 0
        _TOKEN_REFRESH_INTERVAL = 300  # refresh token every 5 min

        headers = await get_headers()
        last_refresh = 0

        timeout = httpx.Timeout(connect=30.0, read=60.0, write=30.0, pool=30.0)
        async with httpx.AsyncClient(timeout=timeout) as client:
            while elapsed < poll_timeout:
                # Refresh token periodically to avoid expiration.
                if elapsed - last_refresh >= _TOKEN_REFRESH_INTERVAL:
                    headers = await get_headers()
                    last_refresh = elapsed

                resp = await client.get(transcription_url, headers=headers)
                resp.raise_for_status()
                data = resp.json()
                status = data.get("status", "")

                if status == "Succeeded":
                    logger.info("Batch Transcription succeeded after %ds.", elapsed)
                    return await self._batch_fetch_result(client, headers, data)

                if status == "Failed":
                    error_detail = json.dumps(data.get("properties", {}).get("error", {}))
                    raise RuntimeError(f"Batch Transcription failed: {error_detail}")

                logger.debug("Batch status: %s (elapsed %ds)", status, elapsed)
                await asyncio.sleep(poll_interval)
                elapsed += poll_interval

        raise BatchTranscriptionTimeout(
            f"Batch Transcription did not complete within {poll_timeout}s.",
            transcription_url=transcription_url,
        )

    async def _batch_fetch_result(
        self, client: httpx.AsyncClient, headers: dict, data: dict[str, Any],
    ) -> dict[str, Any]:
        """Download the transcription result JSON from the files link."""
        files_url = data.get("links", {}).get("files", "")
        resp = await client.get(files_url, headers=headers)
        resp.raise_for_status()
        for f in resp.json().get("values", []):
            if f.get("kind") == "Transcription":
                content_url = f.get("links", {}).get("contentUrl", "")
                if content_url:
                    # contentUrl is a SAS URL — do NOT send the Bearer token
                    rc = await client.get(content_url)
                    rc.raise_for_status()
                    return rc.json()
        raise RuntimeError("No transcription result file found in batch response.")

    async def _batch_delete(self, headers: dict, transcription_url: str) -> None:
        """Best-effort delete of the transcription resource."""
        try:
            timeout = httpx.Timeout(connect=10.0, read=30.0)
            async with httpx.AsyncClient(timeout=timeout) as client:
                await client.delete(transcription_url, headers=headers)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Failed to delete batch transcription %s: %s", transcription_url, exc)

    async def check_batch_status(self, transcription_url: str) -> str:
        """Check the current status of a Batch Transcription job.

        Returns one of: ``"Running"``, ``"NotStarted"``, ``"Succeeded"``,
        ``"Failed"``, or the raw status string from the API.
        """
        credential = get_async_credential()
        token = await credential.get_token("https://cognitiveservices.azure.com/.default")
        headers = {"Authorization": f"Bearer {token.token}"}
        timeout = httpx.Timeout(connect=30.0, read=60.0, write=30.0, pool=30.0)
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.get(transcription_url, headers=headers)
            resp.raise_for_status()
            return resp.json().get("status", "Unknown")

    async def resume_batch(self, transcription_url: str) -> ContentAnalysisResult:
        """Resume a previously timed-out Batch Transcription.

        Polls until complete, fetches the result, and cleans up.
        """
        credential = get_async_credential()

        async def _get_headers() -> dict[str, str]:
            token = await credential.get_token("https://cognitiveservices.azure.com/.default")
            return {"Authorization": f"Bearer {token.token}", "Content-Type": "application/json"}

        result_data = await self._batch_poll(_get_headers, transcription_url)
        headers = await _get_headers()
        await self._batch_delete(headers, transcription_url)
        return self._parse_batch_result(result_data)

    # ── response parsing (Fast Transcription format) ──────────────────────────

    def _parse_fast_result(self, data: Dict[str, Any]) -> ContentAnalysisResult:
        """Parse Speech Fast Transcription response.

        Response shape::

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

        duration = self._parse_iso_duration(data.get("duration", ""))

        return ContentAnalysisResult(
            raw_transcript=transcript or "(transcript not available)",
            speakers=speakers,
            topics=[],
            language="ja",
            duration_seconds=duration,
        )

    # ── response parsing (Batch Transcription format) ─────────────────────────

    def _parse_batch_result(self, data: Dict[str, Any]) -> ContentAnalysisResult:
        """Parse Batch Transcription result.

        Response shape::

            {
              "source": "...",
              "duration": "PT32.18S",
              "combinedRecognizedPhrases": [...],
              "recognizedPhrases": [
                {"speaker": 1, "nBest": [{"display": "..."}], ...}
              ]
            }

        Speaker IDs in Batch Transcription are **1-indexed**.
        """
        phrases: List[Dict[str, Any]] = data.get("recognizedPhrases", [])

        transcript_lines: list[str] = []
        speaker_set: dict[int, str] = {}
        for p in phrases:
            speaker_id = p.get("speaker", 1)
            if speaker_id not in speaker_set:
                speaker_set[speaker_id] = f"話者{speaker_id}"
            label = speaker_set[speaker_id]
            n_best = p.get("nBest", [])
            text = n_best[0].get("display", "") if n_best else ""
            if text:
                transcript_lines.append(f"{label}：{text}")

        transcript = "\n".join(transcript_lines)
        speakers = list(speaker_set.values())
        duration = self._parse_iso_duration(data.get("duration", ""))

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
    def _normalize_audio(audio_bytes: bytes, filename: str) -> tuple[bytes, str]:
        """Normalize audio to 16 kHz / 16-bit / mono WAV.

        Different microphone devices may record at varying sample rates
        (e.g. 44.1 kHz, 48 kHz). When the browser's MediaRecorder writes
        a WAV header with an incorrect sample rate, playback and
        transcription produce garbled (slow/fast pitched) results.

        Re-encoding through pydub/ffmpeg fixes the sample rate metadata
        and resamples to 16 kHz mono — the format Azure Speech works
        best with.
        """
        try:
            ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else "wav"
            audio = AudioSegment.from_file(io.BytesIO(audio_bytes), format=ext)
            audio = audio.set_frame_rate(16000).set_channels(1).set_sample_width(2)
            buf = io.BytesIO()
            audio.export(buf, format="wav")
            normalized = buf.getvalue()
            logger.info(
                "Audio normalized: %s → 16kHz/16bit/mono WAV (%d → %d bytes)",
                filename,
                len(audio_bytes),
                len(normalized),
            )
            return normalized, "recording.wav"
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "Audio normalization failed (%s) — using original bytes.", exc
            )
            return audio_bytes, filename

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
