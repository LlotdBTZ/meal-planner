import httpx2
import pytest

from app.extraction import transcribe
from app.extraction.schema import ExtractionError
from app.extraction.transcribe import OpenAITranscriber


def make(handler, **kw):
    return OpenAITranscriber(
        "sk-test", http=httpx2.Client(transport=httpx2.MockTransport(handler)), **kw
    )


@pytest.fixture
def audio(tmp_path):
    p = tmp_path / "audio.m4a"
    p.write_bytes(b"fake audio")
    return p


def test_sends_file_and_returns_text(audio):
    seen = {}

    def handler(request):
        seen["auth"] = request.headers["authorization"]
        seen["body"] = request.read()
        return httpx2.Response(200, text="  two cups of rice \n")

    assert make(handler).transcribe(audio) == "two cups of rice"
    assert seen["auth"] == "Bearer sk-test"
    assert b"fake audio" in seen["body"]
    assert b"whisper-1" in seen["body"]


def test_custom_model(audio):
    seen = {}

    def handler(request):
        seen["body"] = request.read()
        return httpx2.Response(200, text="x")

    make(handler, model="other-model").transcribe(audio)
    assert b"other-model" in seen["body"]


@pytest.mark.parametrize("status, message", [(401, "API key"), (500, "failed \\(500\\)")])
def test_http_errors(audio, status, message):
    with pytest.raises(ExtractionError, match=message):
        make(lambda r: httpx2.Response(status)).transcribe(audio)


def test_network_error(audio):
    def handler(request):
        raise httpx2.ConnectError("down")

    with pytest.raises(ExtractionError, match="Couldn't reach"):
        make(handler).transcribe(audio)


def test_too_large_is_rejected_without_upload(audio, monkeypatch):
    monkeypatch.setattr(transcribe, "MAX_AUDIO_BYTES", 5)
    with pytest.raises(ExtractionError, match="too long"):
        make(lambda r: pytest.fail("should not upload")).transcribe(audio)
