"""Link (or pasted text) -> RecipeDraft (design §6.2).

Order for social posts: caption first (cheap), and only if that has no recipe,
download the audio, transcribe it, and read caption + transcript together.
"""

from __future__ import annotations

import shutil
import tempfile
from collections.abc import Callable
from pathlib import Path

import httpx2

from app.config import Settings
from app.extraction.fetch import SOCIAL_PLATFORMS, PostFetcher, detect_platform, is_url
from app.extraction.llm import ClaudeExtractor, RecipeExtractor
from app.extraction.schema import ExtractionError, RecipeDraft
from app.extraction.transcribe import OpenAITranscriber, Transcriber
from app.extraction.web import fetch_page

StageCallback = Callable[[str], None]

NO_RECIPE = "Couldn't find a recipe in this post. Paste the ingredients instead."


class Pipeline:
    def __init__(
        self,
        fetcher: PostFetcher,
        extractor: RecipeExtractor,
        transcriber: Transcriber | None,
        thumbnails_dir: Path,
        work_dir: Path,
        http: httpx2.Client | None = None,
    ) -> None:
        self.fetcher = fetcher
        self.extractor = extractor
        self.transcriber = transcriber
        self.thumbnails_dir = thumbnails_dir
        self.work_dir = work_dir
        self.http = http or httpx2.Client(timeout=20.0, follow_redirects=True)

    def run(self, url_or_text: str, on_stage: StageCallback = lambda _: None) -> RecipeDraft:
        source = url_or_text.strip()
        if not source:
            raise ExtractionError("Paste a link or some recipe text first.")
        if not is_url(source):
            on_stage("Reading your text…")
            return self._require_recipe(
                self.extractor.extract(source), "No recipe found in that text."
            )

        platform = detect_platform(source)
        if platform in SOCIAL_PLATFORMS:
            draft = self._from_social(source, on_stage)
        else:
            draft = self._from_web(source, on_stage)
        draft.source_url = source
        draft.platform = platform
        return draft

    @staticmethod
    def _require_recipe(draft: RecipeDraft, message: str = NO_RECIPE) -> RecipeDraft:
        if not draft.found_recipe:
            raise ExtractionError(message)
        return draft

    def _thumbnail(self, image_url: str | None) -> str | None:
        if not image_url:
            return None
        return self.fetcher.save_thumbnail(image_url, self.thumbnails_dir)

    def _from_social(self, url: str, on_stage: StageCallback) -> RecipeDraft:
        on_stage("Fetching the post…")
        meta = self.fetcher.get_metadata(url)
        caption = meta.caption

        draft = RecipeDraft(found_recipe=False)
        if caption:
            on_stage("Reading the caption…")
            draft = self.extractor.extract(caption)

        if not draft.found_recipe:
            if self.transcriber is None:
                raise ExtractionError(
                    "No recipe in the caption, and video transcription isn't set up "
                    "(TRANSCRIBE_API_KEY). Paste the ingredients instead."
                )
            transcript = self._transcribe(url, on_stage)
            on_stage("Reading the transcript…")
            text = f"Caption:\n{caption}\n\nSpoken in the video:\n{transcript}"
            draft = self._require_recipe(self.extractor.extract(text))

        draft.thumbnail_path = self._thumbnail(meta.thumbnail_url)
        return draft

    def _transcribe(self, url: str, on_stage: StageCallback) -> str:
        on_stage("Listening to the video…")
        self.work_dir.mkdir(parents=True, exist_ok=True)
        tmp = Path(tempfile.mkdtemp(prefix="audio-", dir=self.work_dir))
        try:
            audio = self.fetcher.download_audio(url, tmp)
            assert self.transcriber is not None
            return self.transcriber.transcribe(audio)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def _from_web(self, url: str, on_stage: StageCallback) -> RecipeDraft:
        on_stage("Reading the page…")
        page = fetch_page(url, self.http)
        on_stage("Finding the recipe…")
        draft = self._require_recipe(
            self.extractor.extract(page.text), "No recipe found on that page."
        )
        if page.truncated:
            draft.warnings.append("The page was very long; only the first part was read.")
        draft.thumbnail_path = self._thumbnail(page.image_url)
        return draft


def build_pipeline(settings: Settings) -> Pipeline:
    """Wire the real fetcher, Claude, and (if a key is set) transcription."""
    transcriber = (
        OpenAITranscriber(settings.transcribe_api_key, settings.transcribe_model)
        if settings.transcribe_api_key
        else None
    )
    return Pipeline(
        fetcher=PostFetcher(cookies=settings.ytdlp_cookies),
        extractor=ClaudeExtractor(settings.anthropic_api_key, settings.claude_model),
        transcriber=transcriber,
        thumbnails_dir=settings.thumbnails_dir,
        work_dir=settings.work_dir,
    )
