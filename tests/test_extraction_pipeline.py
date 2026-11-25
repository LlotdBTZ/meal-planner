import httpx2
import pytest

from app.extraction.fetch import PostMetadata
from app.extraction.pipeline import Pipeline
from app.extraction.schema import ExtractionError, RecipeDraft
from app.recipes import Ingredient

FOUND = RecipeDraft(found_recipe=True, name="Shrimp", ingredients=[Ingredient(item="shrimp")])


class FakeExtractor:
    def __init__(self, *results):
        self.results, self.inputs = list(results), []

    def extract(self, text):
        self.inputs.append(text)
        result = self.results.pop(0)
        return RecipeDraft.from_dict(result.to_dict())  # fresh copy


class FakeFetcher:
    def __init__(self, caption="1 lb shrimp", thumbnail="https://cdn/t.jpg", error=None):
        self.meta = PostMetadata(
            url="u", platform="tiktok", description=caption, thumbnail_url=thumbnail
        )
        self.error = error
        self.audio_dirs = []
        self.thumbnail_requests = []

    def get_metadata(self, url):
        if self.error:
            raise self.error
        return self.meta

    def download_audio(self, url, dest_dir):
        self.audio_dirs.append(dest_dir)
        path = dest_dir / "audio.m4a"
        path.write_bytes(b"a")
        return path

    def save_thumbnail(self, image_url, dest_dir):
        self.thumbnail_requests.append(image_url)
        return "thumb.jpg"


class FakeTranscriber:
    def __init__(self, text="add two cups of rice", error=None):
        self.text, self.error, self.paths = text, error, []

    def transcribe(self, path):
        self.paths.append(path)
        assert path.is_file()
        if self.error:
            raise self.error
        return self.text


TIKTOK = "https://www.tiktok.com/@chef/video/1"


def make(tmp_path, extractor, fetcher=None, transcriber=None, http=None):
    return Pipeline(
        fetcher=fetcher or FakeFetcher(),
        extractor=extractor,
        transcriber=transcriber,
        thumbnails_dir=tmp_path / "thumbs",
        work_dir=tmp_path / "work",
        http=http,
    )


def test_pasted_text(tmp_path):
    ex = FakeExtractor(FOUND)
    stages = []
    draft = make(tmp_path, ex).run("1 lb shrimp\n2 cloves garlic", stages.append)
    assert draft.name == "Shrimp"
    assert draft.source_url is None and draft.platform is None
    assert ex.inputs == ["1 lb shrimp\n2 cloves garlic"]
    assert stages == ["Reading your text…"]


def test_pasted_text_without_recipe(tmp_path):
    with pytest.raises(ExtractionError, match="No recipe found in that text"):
        make(tmp_path, FakeExtractor(RecipeDraft(found_recipe=False))).run("hello")


def test_empty_input(tmp_path):
    with pytest.raises(ExtractionError, match="Paste a link"):
        make(tmp_path, FakeExtractor()).run("   ")


def test_recipe_in_caption_skips_audio(tmp_path):
    fetcher, tr = FakeFetcher(), FakeTranscriber()
    stages = []
    draft = make(tmp_path, FakeExtractor(FOUND), fetcher, tr).run(TIKTOK, stages.append)
    assert draft.found_recipe
    assert (draft.source_url, draft.platform, draft.thumbnail_path) == (
        TIKTOK,
        "tiktok",
        "thumb.jpg",
    )
    assert fetcher.audio_dirs == [] and tr.paths == []
    assert stages == ["Fetching the post…", "Reading the caption…"]


def test_spoken_recipe_uses_transcript_and_cleans_up(tmp_path):
    ex = FakeExtractor(RecipeDraft(found_recipe=False), FOUND)
    fetcher, tr = FakeFetcher(caption="so good!! #dinner"), FakeTranscriber()
    stages = []
    draft = make(tmp_path, ex, fetcher, tr).run(TIKTOK, stages.append)
    assert draft.found_recipe and draft.thumbnail_path == "thumb.jpg"
    assert ex.inputs[1] == (
        "Caption:\nso good!! #dinner\n\nSpoken in the video:\nadd two cups of rice"
    )
    assert stages == [
        "Fetching the post…",
        "Reading the caption…",
        "Listening to the video…",
        "Reading the transcript…",
    ]
    assert not fetcher.audio_dirs[0].exists()  # temp audio deleted


def test_empty_caption_goes_straight_to_audio(tmp_path):
    ex = FakeExtractor(FOUND)
    make(tmp_path, ex, FakeFetcher(caption=""), FakeTranscriber()).run(TIKTOK)
    assert len(ex.inputs) == 1 and "Spoken in the video" in ex.inputs[0]


def test_no_recipe_anywhere(tmp_path):
    ex = FakeExtractor(RecipeDraft(found_recipe=False), RecipeDraft(found_recipe=False))
    with pytest.raises(ExtractionError, match="Couldn't find a recipe"):
        make(tmp_path, ex, FakeFetcher(), FakeTranscriber()).run(TIKTOK)


def test_no_transcriber_configured(tmp_path):
    with pytest.raises(ExtractionError, match="TRANSCRIBE_API_KEY"):
        make(tmp_path, FakeExtractor(RecipeDraft(found_recipe=False))).run(TIKTOK)


def test_transcription_error_still_cleans_up(tmp_path):
    fetcher = FakeFetcher(caption="")
    tr = FakeTranscriber(error=ExtractionError("Transcription failed (500)."))
    with pytest.raises(ExtractionError, match="500"):
        make(tmp_path, FakeExtractor(), fetcher, tr).run(TIKTOK)
    assert not fetcher.audio_dirs[0].exists()


def test_fetch_error_propagates(tmp_path):
    fetcher = FakeFetcher(error=ExtractionError("This post needs a login"))
    with pytest.raises(ExtractionError, match="login"):
        make(tmp_path, FakeExtractor(), fetcher).run("https://www.instagram.com/reel/x/")


def test_missing_thumbnail_is_fine(tmp_path):
    fetcher = FakeFetcher(thumbnail=None)
    draft = make(tmp_path, FakeExtractor(FOUND), fetcher).run(TIKTOK)
    assert draft.thumbnail_path is None and fetcher.thumbnail_requests == []


BLOG_HTML = (
    '<html><head><meta property="og:image" content="https://blog/og.jpg"></head>'
    "<body><h1>Soup</h1><p>2 cups stock</p></body></html>"
)


def blog_http(html=BLOG_HTML):
    return httpx2.Client(
        transport=httpx2.MockTransport(
            lambda r: httpx2.Response(200, text=html, headers={"content-type": "text/html"})
        )
    )


def test_blog_page(tmp_path):
    ex, fetcher = FakeExtractor(FOUND), FakeFetcher()
    stages = []
    draft = make(tmp_path, ex, fetcher, http=blog_http()).run(
        "https://blog.example/soup", stages.append
    )
    assert ex.inputs == ["Soup\n2 cups stock"]
    assert draft.platform == "web" and draft.thumbnail_path == "thumb.jpg"
    assert fetcher.thumbnail_requests == ["https://blog/og.jpg"]
    assert stages == ["Reading the page…", "Finding the recipe…"]


def test_blog_page_without_recipe(tmp_path):
    ex = FakeExtractor(RecipeDraft(found_recipe=False))
    with pytest.raises(ExtractionError, match="No recipe found on that page"):
        make(tmp_path, ex, http=blog_http()).run("https://blog.example/about")


def test_truncated_page_adds_warning(tmp_path, monkeypatch):
    from app.extraction import web

    monkeypatch.setattr(web, "MAX_TEXT_CHARS", 5)
    draft = make(tmp_path, FakeExtractor(FOUND), http=blog_http()).run("https://blog.example/x")
    assert any("very long" in w for w in draft.warnings)


def test_build_pipeline_from_settings(tmp_path):
    from app.config import get_settings
    from app.extraction.pipeline import build_pipeline

    base = {"DATA_DIR": str(tmp_path), "ANTHROPIC_API_KEY": "sk-ant-test"}
    p = build_pipeline(get_settings(base))
    assert p.transcriber is None
    assert p.extractor.model == "claude-opus-5-5"
    assert p.thumbnails_dir == tmp_path / "thumbnails"
    p = build_pipeline(
        get_settings({**base, "TRANSCRIBE_API_KEY": "sk-x", "CLAUDE_MODEL": "claude-haiku-5-5"})
    )
    assert p.transcriber is not None
    assert p.extractor.model == "claude-haiku-5-5"
