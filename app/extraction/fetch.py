"""Fetch social posts with yt-dlp: caption metadata, audio, and thumbnails."""

from __future__ import annotations

import uuid
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import httpx2
import yt_dlp
from yt_dlp.utils import DownloadError

from app.extraction.schema import ExtractionError

MAX_THUMBNAIL_BYTES = 5 * 1024 * 1024
SOCIAL_PLATFORMS = {"tiktok", "instagram", "youtube"}

_PLATFORM_HOSTS = {
    "tiktok": ("tiktok.com",),
    "instagram": ("instagram.com",),
    "youtube": ("youtube.com", "youtu.be"),
}

_IMAGE_EXTENSIONS = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp"}


def detect_platform(url: str) -> str:
    host = (urlparse(url).hostname or "").lower()
    for platform, domains in _PLATFORM_HOSTS.items():
        if any(host == d or host.endswith("." + d) for d in domains):
            return platform
    return "web"


def is_url(text: str) -> bool:
    parsed = urlparse(text.strip())
    return parsed.scheme in ("http", "https") and bool(parsed.hostname) and " " not in text.strip()


@dataclass
class PostMetadata:
    url: str
    platform: str
    title: str = ""
    description: str = ""
    uploader: str = ""
    thumbnail_url: str | None = None

    @property
    def caption(self) -> str:
        parts = [self.title, self.description]
        # TikTok often repeats the description as the title
        unique = [p.strip() for i, p in enumerate(parts) if p and p.strip() not in parts[:i]]
        return "\n\n".join(unique)


def friendly_download_error(err: Exception) -> ExtractionError:
    msg = str(err).lower()
    if any(w in msg for w in ("login", "private", "cookies", "sign in", "age")):
        return ExtractionError(
            "This post needs a login (it may be private). "
            "Paste the caption instead, or set up Instagram cookies (see README)."
        )
    if "unsupported url" in msg:
        return ExtractionError("That link isn't supported. Paste the recipe text instead.")
    if any(w in msg for w in ("404", "not found", "unavailable", "removed")):
        return ExtractionError("That post couldn't be found. It may have been removed.")
    return ExtractionError("Couldn't fetch that post. Try again, or paste the caption instead.")


YdlFactory = Callable[[dict[str, Any]], Any]


class PostFetcher:
    def __init__(
        self,
        cookies: Path | None = None,
        ydl_factory: YdlFactory = yt_dlp.YoutubeDL,
        http: httpx2.Client | None = None,
    ) -> None:
        self.cookies = cookies
        self.ydl_factory = ydl_factory
        self.http = http or httpx2.Client(timeout=20.0, follow_redirects=True)

    def _options(self, **extra: Any) -> dict[str, Any]:
        opts: dict[str, Any] = {
            "quiet": True,
            "no_warnings": True,
            "noplaylist": True,
            "socket_timeout": 30,
            **extra,
        }
        if self.cookies:
            opts["cookiefile"] = str(self.cookies)
        return opts

    def get_metadata(self, url: str) -> PostMetadata:
        try:
            with self.ydl_factory(self._options(skip_download=True)) as ydl:
                info = ydl.extract_info(url, download=False)
        except DownloadError as e:
            raise friendly_download_error(e) from e
        if info.get("_type") == "playlist" and info.get("entries"):
            info = next(iter(info["entries"]))
        return PostMetadata(
            url=url,
            platform=detect_platform(url),
            title=info.get("title") or "",
            description=info.get("description") or "",
            uploader=info.get("uploader") or "",
            thumbnail_url=info.get("thumbnail"),
        )

    def download_audio(self, url: str, dest_dir: Path) -> Path:
        """Download the smallest usable audio (or video, if no audio-only stream)."""
        dest_dir.mkdir(parents=True, exist_ok=True)
        opts = self._options(
            format="bestaudio[filesize<25M]/bestaudio/worst[ext=mp4]/worst",
            outtmpl=str(dest_dir / "audio.%(ext)s"),
        )
        try:
            with self.ydl_factory(opts) as ydl:
                info = ydl.extract_info(url, download=True)
                path = Path(ydl.prepare_filename(info))
        except DownloadError as e:
            raise friendly_download_error(e) from e
        if not path.is_file():
            raise ExtractionError("Couldn't download the video's audio.")
        return path

    def save_thumbnail(self, image_url: str, dest_dir: Path) -> str | None:
        """Save an image locally (CDN links expire). Returns the filename, or None."""
        try:
            resp = self.http.get(image_url)
        except httpx2.HTTPError:
            return None
        content_type = resp.headers.get("content-type", "").split(";")[0].strip()
        ext = _IMAGE_EXTENSIONS.get(content_type)
        if resp.status_code != 200 or not ext or len(resp.content) > MAX_THUMBNAIL_BYTES:
            return None
        dest_dir.mkdir(parents=True, exist_ok=True)
        name = f"{uuid.uuid4().hex}{ext}"
        (dest_dir / name).write_bytes(resp.content)
        return name
