import json
from types import SimpleNamespace

import anthropic
import httpx2
import pytest

from app.extraction.llm import FALLBACK_BETA, ClaudeExtractor, build_user_message
from app.extraction.schema import EXTRACTION_SCHEMA, ExtractionError

RECORDED = {
    "found_recipe": True,
    "name": "Garlic Butter Shrimp",
    "servings": 2,
    "ingredients": [
        {
            "quantity": 1,
            "unit": "lb",
            "item": "shrimp",
            "note": "peeled",
            "section": "Meat & Seafood",
            "raw_text": "1 lb shrimp, peeled",
        }
    ],
    "steps": [],
    "warnings": [],
}


class FakeMessages:
    def __init__(self, response=None, error=None):
        self.response, self.error, self.calls = response, error, []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        if self.error:
            raise self.error
        return self.response


def fake_client(text=None, stop_reason="end_turn", error=None):
    blocks = [SimpleNamespace(type="thinking", thinking="")]
    if text is not None:
        blocks.append(SimpleNamespace(type="text", text=text))
    messages = FakeMessages(SimpleNamespace(stop_reason=stop_reason, content=blocks), error)
    return SimpleNamespace(beta=SimpleNamespace(messages=messages)), messages


def test_extract_parses_recorded_response_and_sends_expected_request():
    client, messages = fake_client(json.dumps(RECORDED))
    draft = ClaudeExtractor("key", model="claude-opus-5-5", client=client).extract("caption")
    assert draft.found_recipe and draft.name == "Garlic Butter Shrimp"
    assert draft.ingredients[0].note == "peeled"

    [call] = messages.calls
    assert call["model"] == "claude-opus-5-5"
    assert call["betas"] == [FALLBACK_BETA]
    assert call["fallbacks"] == "default"
    assert call["output_config"]["format"] == {"type": "json_schema", "schema": EXTRACTION_SCHEMA}
    assert call["messages"] == [{"role": "user", "content": "<source>\ncaption\n</source>"}]
    assert "thinking" not in call  # Opus 5.5 rejects disabling it; leave the default


def test_empty_text_skips_the_api():
    client, messages = fake_client(json.dumps(RECORDED))
    assert ClaudeExtractor("k", client=client).extract("   ").found_recipe is False
    assert messages.calls == []


@pytest.mark.parametrize(
    "text, stop_reason, message",
    [
        ("{}", "refusal", "declined"),
        ("{}", "max_tokens", "too long"),
        (None, "end_turn", "returned nothing"),
        ("not json", "end_turn", "unexpected"),
    ],
)
def test_bad_responses_become_friendly_errors(text, stop_reason, message):
    client, _ = fake_client(text, stop_reason)
    with pytest.raises(ExtractionError, match=message):
        ClaudeExtractor("k", client=client).extract("caption")


def _status_error(cls, status):
    req = httpx2.Request("POST", "https://api.anthropic.com/v1/messages")
    return cls("err", response=httpx2.Response(status, request=req), body=None)


@pytest.mark.parametrize(
    "error, message",
    [
        (_status_error(anthropic.AuthenticationError, 401), "API key"),
        (_status_error(anthropic.RateLimitError, 429), "busy"),
        (_status_error(anthropic.InternalServerError, 500), "error \\(500\\)"),
        (
            anthropic.APIConnectionError(
                request=httpx2.Request("POST", "https://api.anthropic.com")
            ),
            "Couldn't reach",
        ),
    ],
)
def test_api_errors_become_friendly_errors(error, message):
    client, _ = fake_client(error=error)
    with pytest.raises(ExtractionError, match=message):
        ClaudeExtractor("k", client=client).extract("caption")


def test_source_is_wrapped_and_trimmed():
    assert build_user_message("  hi \n") == "<source>\nhi\n</source>"


def test_missing_credentials_become_friendly_error():
    client, _ = fake_client(
        error=TypeError('"Could not resolve authentication method. Expected one of api_key"')
    )
    with pytest.raises(ExtractionError, match="ANTHROPIC_API_KEY"):
        ClaudeExtractor("", client=client).extract("caption")


def test_other_type_errors_are_not_hidden():
    client, _ = fake_client(error=TypeError("unexpected keyword"))
    with pytest.raises(TypeError):
        ClaudeExtractor("k", client=client).extract("caption")
