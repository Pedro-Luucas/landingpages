"""M2 public scrapers: fixtures only, never the network."""

from __future__ import annotations

import json
from pathlib import Path
from urllib.parse import urlparse

import pytest

from studio_pipeline.config import schemas_dir
from studio_pipeline.errors import (
    HTTP_TIMEOUT,
    PLATFORM_BLOCKED,
    RATE_LIMITED,
    PipelineError,
)
from studio_pipeline.scrapers import (
    HttpResponse,
    merge_social,
    scrape_facebook,
    scrape_instagram,
)
from studio_pipeline.validation.schemas import load_json, make_validator

FIXTURES = Path(__file__).parent / "fixtures" / "scrapers"
IG_URL = "https://www.instagram.com/aurorasoundlab.cwb/"
FB_URL = "https://www.facebook.com/aurorasoundlab.cwb/"
NOW = "2026-08-12T12:30:00Z"
BLOCK_TOKEN = "UNIQUE_BLOCK_HTML_DUMP_TOKEN"


def _read(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def _social_validator():
    schema = load_json(schemas_dir() / "dossier.schema.json")
    fragment = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$defs": schema["$defs"],
        **schema["$defs"]["Social"],
    }
    return make_validator(fragment)


class FixtureHttp:
    """Serves canned HTML/JSON. Raises if a CDN/image URL is requested."""

    def __init__(self, routes: dict[str, HttpResponse]) -> None:
        self.routes = {_key(url): response for url, response in routes.items()}
        self.calls: list[str] = []

    def get(self, url: str, timeout: float | None = None) -> HttpResponse:
        self.calls.append(url)
        key = _key(url)
        if key in self.routes:
            return self.routes[key]
        path = urlparse(url).path
        if path.rstrip("/").endswith("robots.txt"):
            return HttpResponse(404, {}, "Not Found", url)
        raise AssertionError(f"unexpected URL (no network): {url}")


def _key(url: str) -> str:
    parsed = urlparse(url)
    path = parsed.path.rstrip("/") or "/"
    return f"{parsed.scheme}://{parsed.netloc.lower()}{path}"


def _html(url: str, body: str, status: int = 200) -> HttpResponse:
    return HttpResponse(status, {"Content-Type": "text/html; charset=utf-8"}, body, url)


def _json(url: str, payload: dict, status: int = 200) -> HttpResponse:
    return HttpResponse(
        status,
        {"Content-Type": "application/json"},
        json.dumps(payload),
        url,
    )


def _ig_http(html_name: str = "instagram_public.html") -> FixtureHttp:
    return FixtureHttp({IG_URL: _html(IG_URL, _read(html_name))})


def _fb_http() -> FixtureHttp:
    return FixtureHttp({FB_URL: _html(FB_URL, _read("facebook_public.html"))})


def test_instagram_happy_path_bio_and_captions() -> None:
    http = _ig_http()
    result = scrape_instagram(IG_URL, http, max_posts=30, now=lambda: NOW, sleep=lambda _: None)

    assert result.bio is not None
    assert "Cabine isolada" in result.bio.value
    assert result.bio.source_type == "instagram"
    assert result.profile_image is not None
    assert result.profile_image.value == "https://cdn.aurorasoundlab.example/profile.jpg"
    assert result.highlights
    assert result.highlights[0].value["title"] == "A sala"
    assert 1 <= len(result.posts) <= 30
    captions = [post.caption for post in result.posts if post.caption]
    assert any("TLM 103" in (caption or "") for caption in captions)
    assert all(post.caption for post in result.posts)
    assert not any("cdn.aurorasoundlab.example" in url for url in http.calls)


def test_instagram_caps_at_max_posts() -> None:
    posts = []
    for index in range(31):
        posts.append(
            {
                "id": f"p{index:02d}",
                "url": f"https://www.instagram.com/p/post{index:02d}/",
                "publishedAt": f"2026-07-{(index % 28) + 1:02d}T12:00:00Z",
                "caption": f"Caption {index}",
                "media": [
                    {
                        "url": f"https://cdn.aurorasoundlab.example/posts/{index}.jpg",
                        "type": "image",
                    }
                ],
            }
        )
    http = FixtureHttp({IG_URL: _json(IG_URL, {"bio": "Bio from JSON.", "posts": posts})})
    result = scrape_instagram(IG_URL, http, max_posts=30, now=lambda: NOW, sleep=lambda _: None)
    assert result.bio is not None
    assert result.bio.value == "Bio from JSON."
    assert len(result.posts) == 30


def test_blocked_403_is_platform_blocked_without_html_dump() -> None:
    body = _read("instagram_blocked.html")
    assert BLOCK_TOKEN in body
    http = FixtureHttp({IG_URL: _html(IG_URL, body, status=403)})
    with pytest.raises(PipelineError) as excinfo:
        scrape_instagram(IG_URL, http, sleep=lambda _: None)
    assert excinfo.value.code == PLATFORM_BLOCKED
    dumped = f"{excinfo.value} {excinfo.value.message}"
    assert BLOCK_TOKEN not in dumped
    assert "<html" not in dumped.lower()
    assert "<form" not in dumped.lower()


def test_login_wall_is_platform_blocked() -> None:
    http = FixtureHttp({IG_URL: _html(IG_URL, _read("instagram_login_wall.html"))})
    with pytest.raises(PipelineError) as excinfo:
        scrape_instagram(IG_URL, http, sleep=lambda _: None)
    assert excinfo.value.code == PLATFORM_BLOCKED
    assert "log in to continue" not in excinfo.value.message.lower()


def test_facebook_complements_missing_bio() -> None:
    ig = scrape_instagram(
        IG_URL,
        _ig_http("instagram_no_bio.html"),
        now=lambda: NOW,
        sleep=lambda _: None,
    )
    fb = scrape_facebook(FB_URL, _fb_http(), now=lambda: NOW, sleep=lambda _: None)
    assert ig.bio is None
    assert fb.bio is not None
    social = merge_social(ig, fb)
    assert social["bio"]["value"].startswith("Estúdio em Curitiba no Facebook")
    assert social["bio"]["sourceType"] == "facebook"
    assert any(item["value"]["title"] == "Cabine" for item in social["highlights"])
    _social_validator().validate(social)


def test_merge_dedupes_overlapping_posts() -> None:
    ig = scrape_instagram(IG_URL, _ig_http(), now=lambda: NOW, sleep=lambda _: None)
    fb = scrape_facebook(FB_URL, _fb_http(), now=lambda: NOW, sleep=lambda _: None)
    social = merge_social(ig, fb)
    urls = [post["url"] for post in social["posts"]]
    media_urls = [item["url"] for post in social["posts"] for item in post["media"]]
    assert len(urls) == len(set(urls))
    assert media_urls.count("https://cdn.aurorasoundlab.example/posts/1001.jpg") == 1
    assert any("fb-about.jpg" in item for item in media_urls)
    assert any("facebook.com" in url for url in urls)
    assert social["bio"]["sourceType"] == "instagram"
    _social_validator().validate(social)


def test_reel_without_still_is_not_selectable_photo() -> None:
    result = scrape_instagram(IG_URL, _ig_http(), now=lambda: NOW, sleep=lambda _: None)
    reel = next(post for post in result.posts if "reelNoStill" in post.url)
    assert reel.media
    assert all(not item.selectable_photo for item in reel.media)
    assert any("reel_without_still" in item.flags for item in reel.media)
    assert not any(item.selectable_photo and item.type == "video" for item in reel.media)

    with_thumb = next(post for post in result.posts if "reelWithThumb" in post.url)
    assert any(item.type == "image" and item.selectable_photo for item in with_thumb.media)
    assert any(item.type == "video" and not item.selectable_photo for item in with_thumb.media)


def test_no_network_sockets_or_urlopen(monkeypatch: pytest.MonkeyPatch) -> None:
    def blocked(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("network access is forbidden in scraper tests")

    monkeypatch.setattr("socket.create_connection", blocked)
    monkeypatch.setattr("urllib.request.urlopen", blocked)
    result = scrape_instagram(IG_URL, _ig_http(), now=lambda: NOW, sleep=lambda _: None)
    assert result.bio is not None
    social = merge_social(result, None)
    assert social["posts"]


def test_429_retries_then_succeeds() -> None:
    html = _read("instagram_public.html")
    sleeps: list[float] = []

    class OnceLimited:
        def __init__(self) -> None:
            self.profile_hits = 0

        def get(self, url: str, timeout: float | None = None) -> HttpResponse:
            if urlparse(url).path.endswith("robots.txt"):
                return HttpResponse(404, {}, "", url)
            self.profile_hits += 1
            if self.profile_hits == 1:
                return HttpResponse(429, {"Retry-After": "0.01"}, "slow down", url)
            return _html(url, html)

    result = scrape_instagram(
        IG_URL,
        OnceLimited(),
        now=lambda: NOW,
        sleep=sleeps.append,
    )
    assert result.bio is not None
    assert sleeps


def test_429_exhausted_is_rate_limited() -> None:
    class AlwaysLimited:
        def get(self, url: str, timeout: float | None = None) -> HttpResponse:
            if urlparse(url).path.endswith("robots.txt"):
                return HttpResponse(404, {}, "", url)
            return HttpResponse(429, {}, "slow down", url)

    with pytest.raises(PipelineError) as excinfo:
        scrape_instagram(IG_URL, AlwaysLimited(), sleep=lambda _: None)
    assert excinfo.value.code == RATE_LIMITED


def test_timeout_maps_to_http_timeout() -> None:
    class Boom:
        def get(self, url: str, timeout: float | None = None) -> HttpResponse:
            if urlparse(url).path.endswith("robots.txt"):
                return HttpResponse(404, {}, "", url)
            raise TimeoutError("timed out")

    with pytest.raises(PipelineError) as excinfo:
        scrape_instagram(IG_URL, Boom(), sleep=lambda _: None)
    assert excinfo.value.code == HTTP_TIMEOUT


def test_robots_disallow_skips_with_warning() -> None:
    robots = "https://www.instagram.com/robots.txt"
    http = FixtureHttp(
        {
            robots: HttpResponse(200, {"Content-Type": "text/plain"}, _read("robots_disallow.txt"), robots),
            IG_URL: _html(IG_URL, _read("instagram_public.html")),
        }
    )
    result = scrape_instagram(IG_URL, http, now=lambda: NOW, sleep=lambda _: None)
    assert result.posts == []
    assert result.bio is None
    assert any(warning.code == "ROBOTS_DISALLOWED" for warning in result.warnings)
    assert not any("aurorasoundlab" in urlparse(url).path for url in http.calls)


def test_discovery_http_response_is_accepted() -> None:
    from studio_pipeline.http.adapter import ScraperHttpAdapter
    from studio_pipeline.http.client import FakeHttpClient
    from studio_pipeline.http.client import HttpResponse as DiscoveryHttpResponse

    html = _read("instagram_public.html")
    inner = FakeHttpClient(
        {
            IG_URL: DiscoveryHttpResponse(
                status=200,
                headers={"content-type": "text/html"},
                text=html,
                final_url=IG_URL,
            )
        }
    )
    result = scrape_instagram(
        IG_URL,
        ScraperHttpAdapter(inner),
        now=lambda: NOW,
        sleep=lambda _: None,
    )
    assert result.bio is not None

    direct = FakeHttpClient(
        {
            IG_URL: DiscoveryHttpResponse(
                status=200,
                headers={"content-type": "text/html"},
                text=html,
                final_url=IG_URL,
            )
        }
    )
    again = scrape_instagram(IG_URL, direct, now=lambda: NOW, sleep=lambda _: None)
    assert again.bio is not None


def test_status_zero_is_http_timeout() -> None:
    class Zero:
        def get(self, url: str, timeout: float | None = None) -> HttpResponse:
            if urlparse(url).path.endswith("robots.txt"):
                return HttpResponse(404, {}, "", url)
            return HttpResponse(0, {}, "", url)

    with pytest.raises(PipelineError) as excinfo:
        scrape_instagram(IG_URL, Zero(), sleep=lambda _: None)
    assert excinfo.value.code == HTTP_TIMEOUT


def test_tuple_http_response_is_accepted() -> None:
    html = _read("instagram_public.html")

    class TupleClient:
        def get(self, url: str) -> tuple[int, dict[str, str], str, str]:
            if urlparse(url).path.endswith("robots.txt"):
                return (404, {}, "", url)
            return (200, {"Content-Type": "text/html"}, html, url)

    result = scrape_instagram(IG_URL, TupleClient(), now=lambda: NOW, sleep=lambda _: None)
    assert result.bio is not None


def test_merge_none_is_empty_social() -> None:
    social = merge_social(None, None)
    assert social == {"highlights": [], "posts": []}
    _social_validator().validate(social)
