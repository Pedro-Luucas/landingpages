"""OpenAI-compatible adapter: urllib mocked, no live API."""

from __future__ import annotations

import io
import json
from email.message import Message
from typing import Any
from urllib.error import HTTPError
from urllib.request import Request

import pytest

from studio_pipeline.ai.factory import create_provider
from studio_pipeline.ai.providers.fake import FakeProvider
from studio_pipeline.ai.providers.openai_compatible import (
    PROMPT_VERSION,
    OpenAICompatibleProvider,
)
from studio_pipeline.config import load_config
from studio_pipeline.errors import (
    AI_OUTPUT_INVALID,
    AI_PROVIDER_ERROR,
    AI_RATE_LIMITED,
    PipelineError,
)

API_KEY = "sk-test-secret-key-do-not-log"
IMAGE_URL = "https://cdn.aurorasoundlab.example/posts/hero.jpg"


class FakeHTTPResponse:
    def __init__(self, body: bytes, status: int = 200) -> None:
        self._body = body
        self.status = status

    def read(self, n: int = -1) -> bytes:
        if n is None or n < 0:
            return self._body
        return self._body[:n]

    def geturl(self) -> str:
        return "https://api.openai.com/v1/chat/completions"

    def __enter__(self) -> FakeHTTPResponse:
        return self

    def __exit__(self, *_args: object) -> None:
        return None


class CapturingUrlopen:
    def __init__(self, handler: Any) -> None:
        self.handler = handler
        self.requests: list[Request] = []
        self.timeouts: list[float | None] = []

    def __call__(self, request: Request, timeout: float | None = None) -> Any:
        self.requests.append(request)
        self.timeouts.append(timeout)
        return self.handler(request, timeout)


@pytest.fixture(autouse=True)
def no_network(monkeypatch: pytest.MonkeyPatch) -> None:
    def blocked(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("network access is forbidden in openai_compatible tests")

    monkeypatch.setattr("urllib.request.urlopen", blocked)
    monkeypatch.setattr("socket.create_connection", blocked)


@pytest.fixture
def config(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("AI_PROVIDER", "openai")
    monkeypatch.setenv("AI_MODEL", "gpt-4o-mini")
    monkeypatch.setenv("AI_API_KEY", API_KEY)
    return load_config()


def _site() -> dict[str, Any]:
    return {
        "schemaVersion": 1,
        "studioId": "aurora-sound-lab-cwb",
        "generationId": "gen-test",
        "inputHash": "a" * 64,
        "provider": "openai",
        "model": "gpt-4o-mini",
        "promptVersion": PROMPT_VERSION,
        "templateId": "minimal",
        "branding": {
            "colors": {
                "background": "#111",
                "surface": "#222",
                "primary": "#f90",
                "secondary": "#09f",
                "text": "#fff",
                "mutedText": "#aaa",
            },
            "fontHeading": "Inter",
            "fontBody": "Inter",
            "radius": "small",
            "mood": ["focused"],
        },
        "copy": {
            "hero": {"title": "Aurora Sound Lab"},
            "contact": {"title": "Contato", "cta": "Falar"},
        },
        "sections": [{"id": "hero", "enabled": True, "order": 0}],
        "assetPaths": [],
        "factualClaims": [],
        "warnings": [],
        "createdAt": "2026-08-12T12:00:00Z",
    }


def _envelope(content: Any) -> bytes:
    if not isinstance(content, str):
        content = json.dumps(content, ensure_ascii=False)
    return json.dumps(
        {"choices": [{"message": {"role": "assistant", "content": content}}]}
    ).encode("utf-8")


def _http_error(status: int, body: bytes = b'{"error":{"message":"nope"}}') -> HTTPError:
    headers = Message()
    headers["Content-Type"] = "application/json"
    return HTTPError(
        "https://api.openai.com/v1/chat/completions",
        status,
        "error",
        headers,
        io.BytesIO(body),
    )


def _dossier(*, captions: int = 2) -> dict[str, Any]:
    posts = []
    for index in range(captions):
        posts.append(
            {
                "externalId": f"p{index}",
                "url": f"https://www.instagram.com/p/{index}/",
                "caption": f"caption-{index} sala tratada",
                "media": [{"url": IMAGE_URL, "type": "image"}],
                "collectedAt": "2026-08-12T12:00:00Z",
            }
        )
    return {
        "schemaVersion": 1,
        "studioId": "aurora-sound-lab-cwb",
        "social": {
            "bio": {
                "value": "Estúdio em Curitiba",
                "sourceUrl": "https://www.instagram.com/aurorasoundlab.cwb/",
                "sourceType": "instagram",
                "collectedAt": "2026-08-12T12:00:00Z",
                "confidence": 0.9,
            },
            "highlights": [
                {
                    "value": {"title": "Cabine", "text": "Isolada"},
                    "sourceUrl": "https://www.instagram.com/stories/highlights/1/",
                    "sourceType": "instagram",
                    "collectedAt": "2026-08-12T12:00:00Z",
                    "confidence": 0.8,
                }
            ],
            "posts": posts,
        },
        "facts": {
            "description": [
                {
                    "value": "Sala tratada no Água Verde",
                    "sourceUrl": "https://www.aurorasoundlab.example/sobre",
                    "sourceType": "official_site",
                    "collectedAt": "2026-08-12T12:00:00Z",
                    "confidence": 0.95,
                }
            ],
            "equipment": [],
            "prices": [],
            "openingHours": [],
            "googleReviews": [],
            "map": [],
        },
    }


def _user_payload(request: Request) -> dict[str, Any]:
    body = json.loads(request.data.decode("utf-8"))
    content = body["messages"][1]["content"]
    return json.loads(content)


def test_valid_json_returns_generated_site(config) -> None:
    site = _site()
    capture = CapturingUrlopen(lambda *_a, **_k: FakeHTTPResponse(_envelope(site)))
    provider = OpenAICompatibleProvider(config, urlopen=capture, sleep=lambda _s: None)
    result = provider.generate_site(_dossier(), {}, {"selected": []})
    assert result["templateId"] == "minimal"
    assert result["copy"]["hero"]["title"] == "Aurora Sound Lab"
    assert result["promptVersion"] == PROMPT_VERSION
    assert result["model"] == "gpt-4o-mini"
    assert capture.requests
    posted = json.loads(capture.requests[0].data.decode("utf-8"))
    assert posted["response_format"] == {"type": "json_object"}
    assert posted["model"] == "gpt-4o-mini"
    user = _user_payload(capture.requests[0])
    keys = [key for key in user if key in {"bio", "highlights", "captions", "facts"}]
    assert keys == ["bio", "highlights", "captions", "facts"]
    assert user["bio"] == "Estúdio em Curitiba"
    assert IMAGE_URL not in json.dumps(posted)
    assert "image_url" not in json.dumps(posted)
    assert API_KEY not in json.dumps(user)
    assert capture.timeouts[0] == 60.0


def test_401_maps_to_ai_provider_error(config) -> None:
    def raise_401(*_a, **_k):
        raise _http_error(401)

    provider = OpenAICompatibleProvider(config, urlopen=raise_401, sleep=lambda _s: None)
    with pytest.raises(PipelineError) as excinfo:
        provider.generate_site(_dossier(), {}, {"selected": []})
    assert excinfo.value.code == AI_PROVIDER_ERROR
    assert API_KEY not in str(excinfo.value)
    assert API_KEY not in excinfo.value.message


def test_malformed_json_maps_to_ai_output_invalid(config) -> None:
    capture = CapturingUrlopen(
        lambda *_a, **_k: FakeHTTPResponse(_envelope("this is not json {"))
    )
    provider = OpenAICompatibleProvider(config, urlopen=capture, sleep=lambda _s: None)
    with pytest.raises(PipelineError) as excinfo:
        provider.generate_site(_dossier(), {}, {"selected": []})
    assert excinfo.value.code == AI_OUTPUT_INVALID


def test_malformed_http_body_maps_to_ai_output_invalid(config) -> None:
    capture = CapturingUrlopen(lambda *_a, **_k: FakeHTTPResponse(b"not-json"))
    provider = OpenAICompatibleProvider(config, urlopen=capture, sleep=lambda _s: None)
    with pytest.raises(PipelineError) as excinfo:
        provider.generate_site(_dossier(), {}, {"selected": []})
    assert excinfo.value.code == AI_OUTPUT_INVALID


def test_missing_api_key_is_provider_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AI_PROVIDER", "openai")
    monkeypatch.setenv("AI_MODEL", "gpt-4o-mini")
    monkeypatch.setenv("AI_API_KEY", "")
    settings = load_config()
    provider = OpenAICompatibleProvider(settings, urlopen=lambda *_a, **_k: None)
    with pytest.raises(PipelineError) as excinfo:
        provider.generate_site(_dossier(), {}, {"selected": []})
    assert excinfo.value.code == AI_PROVIDER_ERROR
    assert "AI_API_KEY" in excinfo.value.message


def test_factory_registers_openai(config) -> None:
    provider = create_provider(config)
    assert isinstance(provider, OpenAICompatibleProvider)


def test_factory_still_returns_fake(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AI_PROVIDER", "fake")
    monkeypatch.setenv("AI_API_KEY", "")
    provider = create_provider(load_config())
    assert isinstance(provider, FakeProvider)


def test_captions_capped_at_30(config) -> None:
    site = _site()
    capture = CapturingUrlopen(lambda *_a, **_k: FakeHTTPResponse(_envelope(site)))
    provider = OpenAICompatibleProvider(config, urlopen=capture, sleep=lambda _s: None)
    provider.generate_site(_dossier(captions=35), {}, {"selected": []})
    user = _user_payload(capture.requests[0])
    assert len(user["captions"]) == 30
    assert user["captions"][0] == "caption-0 sala tratada"
    assert user["captions"][-1] == "caption-29 sala tratada"


def test_429_retries_then_succeeds(config) -> None:
    sleeps: list[float] = []
    hits = {"n": 0}

    def flaky(_request: Request, timeout: float | None = None) -> FakeHTTPResponse:
        hits["n"] += 1
        if hits["n"] == 1:
            raise _http_error(429, b'{"error":{"message":"slow down"}}')
        return FakeHTTPResponse(_envelope(_site()))

    provider = OpenAICompatibleProvider(
        config, urlopen=flaky, sleep=lambda seconds: sleeps.append(seconds)
    )
    result = provider.generate_site(_dossier(), {}, {"selected": []})
    assert result["templateId"] == "minimal"
    assert hits["n"] == 2
    assert sleeps == [0.5]


def test_429_exhausted_maps_to_rate_limited(config) -> None:
    def always_429(*_a, **_k):
        raise _http_error(429)

    provider = OpenAICompatibleProvider(config, urlopen=always_429, sleep=lambda _s: None)
    with pytest.raises(PipelineError) as excinfo:
        provider.generate_site(_dossier(), {}, {"selected": []})
    assert excinfo.value.code == AI_RATE_LIMITED


def test_openai_base_url_from_environ(config, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_BASE_URL", "https://llm.example.test/v1")
    capture = CapturingUrlopen(lambda *_a, **_k: FakeHTTPResponse(_envelope(_site())))
    provider = OpenAICompatibleProvider(config, urlopen=capture, sleep=lambda _s: None)
    provider.generate_site(_dossier(), {}, {"selected": []})
    assert capture.requests[0].full_url == "https://llm.example.test/v1/chat/completions"
    auth = capture.requests[0].get_header("Authorization")
    assert auth == f"Bearer {API_KEY}"
