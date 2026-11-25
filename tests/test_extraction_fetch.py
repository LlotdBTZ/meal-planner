from pathlib import Path

import httpx2
import pytest
from yt_dlp.utils import DownloadError

from app.extraction.fetch import PostFetcher, PostMetadata, detect_platform, is_url
from app.extraction.schema import ExtractionError


@pytest.mark.parametrize(
    "url, platform",
    [
        ("https://www.tiktok.com/@chef/video/123", "tiktok"),
        ("https://vm.tiktok.com/ZMabc/", "tiktok"),
        ("https://www.instagram.com/reel/Cabc/", "instagram"),
        ("https://youtu.be/abc", "youtube"),
        ("https://www.youtube.com/shorts/abc", "youtube"),
        ("https://www.seriouseats.com/birria", "web"),
        ("https://nottiktok.com/x", "web"),
    ],
)
def test_detect_platform(url, platform):
    assert detect_platform(url) == platform


@pytest.mark.parametrize(
    "text, expected",
    [
        ("https://x.com/a", True),
        ("  http://x.com  ", True),
        ("2 cups rice", False),
        ("ftp://x.com", False),
        ("https://x.com/a and more text", False),
    ],
)
def test_is_url(text, expected):
    assert is_url(text) is expected


def test_caption_dedupes_title_and_description():
    m = PostMetadata(url="u", platform="tiktok", title="Tacos!", description="Tacos!")
    assert m.caption == "Tacos!"
    m = PostMetadata(url="u", platform="tiktok", title="Tacos", description="2 lb beef")
    assert m.caption == "Tacos\n\n2 lb beef"


class FakeYDL:
    """Stands in for yt_dlp.YoutubeDL."""

    instances: list["FakeYDL"] = []

    def __init__(self, opts, info=None, error=None, write_file=True):
        self.opts, self.info, self.error, self.write_file = opts, info, error, write_file
        FakeYDL.instances.append(self)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def extract_info(self, url, download):
        if self.error:
            raise self.error
        if download and self.write_file:
            Path(self.prepare_filename(self.info)).write_bytes(b"audio")
        return self.info

    def prepare_filename(self, info):
        return self.opts["outtmpl"].replace("%(ext)s", info["ext"])


def factory(**kw):
    return lambda opts: FakeYDL(opts, **kw)


INFO = {
    "title": "Garlic shrimp",
    "description": "1 lb shrimp\n4 cloves garlic",
    "uploader": "chef",
    "thumbnail": "https://cdn/x.jpg",
    "ext": "m4a",
}


def test_get_metadata():
    f = PostFetcher(ydl_factory=factory(info=INFO))
    m = f.get_metadata("https://www.tiktok.com/@c/video/1")
    assert (m.platform, m.title, m.uploader, m.thumbnail_url) == (
        "tiktok",
        "Garlic shrimp",
        "chef",
        "https://cdn/x.jpg",
    )
    assert "4 cloves garlic" in m.caption
    assert FakeYDL.instances[-1].opts["skip_download"] is True


def test_metadata_takes_first_playlist_entry():
    info = {"_type": "playlist", "entries": [INFO]}
    m = PostFetcher(ydl_factory=factory(info=info)).get_metadata("https://instagram.com/p/x")
    assert m.title == "Garlic shrimp"


def test_cookies_passed_when_configured(tmp_path):
    PostFetcher(cookies=tmp_path / "c.txt", ydl_factory=factory(info=INFO)).get_metadata("u")
    assert FakeYDL.instances[-1].opts["cookiefile"] == str(tmp_path / "c.txt")
    PostFetcher(ydl_factory=factory(info=INFO)).get_metadata("u")
    assert "cookiefile" not in FakeYDL.instances[-1].opts


@pytest.mark.parametrize(
    "message, expected",
    [
        ("This content is only available for registered users. Use --cookies", "login"),
        ("Private video", "login"),
        ("Unsupported URL: https://x", "isn't supported"),
        ("HTTP Error 404: Not Found", "couldn't be found"),
        ("something odd", "Couldn't fetch"),
    ],
)
def test_download_errors_are_friendly(message, expected):
    f = PostFetcher(ydl_factory=factory(error=DownloadError(message)))
    with pytest.raises(ExtractionError, match=expected):
        f.get_metadata("u")


def test_download_audio(tmp_path):
    f = PostFetcher(ydl_factory=factory(info=INFO))
    path = f.download_audio("u", tmp_path / "work")
    assert path == tmp_path / "work" / "audio.m4a"
    assert path.read_bytes() == b"audio"
    assert "bestaudio" in FakeYDL.instances[-1].opts["format"]


def test_download_audio_missing_file(tmp_path):
    f = PostFetcher(ydl_factory=factory(info=INFO, write_file=False))
    with pytest.raises(ExtractionError, match="audio"):
        f.download_audio("u", tmp_path)


def http(handler):
    return httpx2.Client(transport=httpx2.MockTransport(handler))


def test_save_thumbnail(tmp_path):
    def handler(request):
        return httpx2.Response(200, content=b"jpg!", headers={"content-type": "image/jpeg"})

    name = PostFetcher(http=http(handler)).save_thumbnail("https://cdn/x.jpg", tmp_path)
    assert name.endswith(".jpg")
    assert (tmp_path / name).read_bytes() == b"jpg!"


@pytest.mark.parametrize(
    "response",
    [
        httpx2.Response(404, headers={"content-type": "image/jpeg"}),
        httpx2.Response(200, content=b"<html>", headers={"content-type": "text/html"}),
    ],
)
def test_save_thumbnail_rejects_bad_responses(tmp_path, response):
    assert PostFetcher(http=http(lambda r: response)).save_thumbnail("u", tmp_path) is None


def test_save_thumbnail_network_error(tmp_path):
    def handler(request):
        raise httpx2.ConnectError("down")

    assert PostFetcher(http=http(handler)).save_thumbnail("https://cdn/x", tmp_path) is None
