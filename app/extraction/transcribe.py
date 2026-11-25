"""Speech-to-text for videos whose recipe is spoken, not written.

Kept behind a small protocol so the provider can be swapped (design §7).
"""

from __future__ import annotations

from pathlib import Path
from typing import Protocol

import httpx2

from app.extraction.schema import ExtractionError

MAX_AUDIO_BYTES = 25 * 1024 * 1024  # OpenAI's upload limit
DEFAULT_MODEL = "whisper-1"
OPENAI_URL = "https://api.openai.com/v1/audio/transcriptions"


class Transcriber(Protocol):
    def transcribe(self, audio_path: Path) -> str: ...


class OpenAITranscriber:
    def __init__(
        self,
        api_key: str,
        model: str = DEFAULT_MODEL,
        http: httpx2.Client | None = None,
    ) -> None:
        self.api_key = api_key
        self.model = model or DEFAULT_MODEL
        self.http = http or httpx2.Client(timeout=180.0)

    def transcribe(self, audio_path: Path) -> str:
        size = audio_path.stat().st_size
        if size > MAX_AUDIO_BYTES:
            raise ExtractionError("This video is too long to transcribe. Paste the recipe instead.")
        try:
            with audio_path.open("rb") as fh:
                resp = self.http.post(
                    OPENAI_URL,
                    headers={"Authorization": f"Bearer {self.api_key}"},
                    data={"model": self.model, "response_format": "text"},
                    files={"file": (audio_path.name, fh)},
                )
        except httpx2.HTTPError as e:
            raise ExtractionError("Couldn't reach the transcription service.") from e
        if resp.status_code == 401:
            raise ExtractionError("The transcription API key is missing or invalid.")
        if resp.status_code >= 400:
            raise ExtractionError(f"Transcription failed ({resp.status_code}).")
        return resp.text.strip()
