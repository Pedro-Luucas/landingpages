"""M2 discovery: classify, aggregators, search, scoring. No network."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from studio_pipeline.config import (
    DEFAULT_DISCOVERY_CONFIDENCE_THRESHOLD,
    load_config,
    schemas_dir,
)
from studio_pipeline.discovery.classify import classify_url
from studio_pipeline.discovery.normalize import normalize_social_url, strip_tracking_params
from studio_pipeline.discovery.social import discover_profiles
from studio_pipeline.errors import PLATFORM_BLOCKED, SOCIAL_NOT_FOUND
from studio_pipeline.http.client import DEFAULT_USER_AGENT, FakeHttpClient, HttpResponse
from studio_pipeline.search.provider import (
    FakeSearchProvider,
    NullSearchProvider,
    create_search_provider,
)
from studio_pipeline.validation.schemas import load_json, make_validator

FIXTURES = Path(__file__).parent / "fixtures" / "discovery"
NOW = "2026-08-12T12:00:00Z"


def _now() -> str:
    return NOW


def _studio(**overrides: Any) -> dict[str, Any]:
    studio: dict[str, Any] = {
        "schemaVersion": 1,
        "studioId": "aurora-sound-lab-cwb",
        "name": "Aurora Sound Lab",
        "slug": "aurora-sound-lab",
        "location": {
            "city": "Curitiba",
            "state": "Paraná",
            "address": "Rua Fictícia do Ensaio, 240, Curitiba - PR",
        },
        "contacts": {
            "phone": "+55 41 90000-1111",
            "website": "https://www.aurorasoundlab.example/",
        },
        "source": {
            "importedAt": NOW,
            "sourceFile": "fixture.json",
            "sourceHash": "0" * 64,
            "originalRecord": {
                "title": "Aurora Sound Lab",
                "cidade": "Curitiba",
                "website": "https://www.aurorasoundlab.example/",
            },
        },
        "pipelineStatus": "discovering",
        "updatedAt": NOW,
    }
    for key, value in overrides.items():
        if key in {"contacts", "location", "source"} and isinstance(value, dict):
            merged = dict(studio.get(key) or {})
            if key == "source" and "originalRecord" in value:
                original = dict(merged.get("originalRecord") or {})
                original.update(value["originalRecord"])
                merged.update(value)
                merged["originalRecord"] = original
            else:
                merged.update(value)
            studio[key] = merged
        else:
            studio[key] = value
    return studio


def _assert_valid_discovery(discovery: dict[str, Any]) -> None:
    schema = load_json(schemas_dir() / "dossier.schema.json")
    validator = make_validator(
        {
            "$schema": schema.get("$schema"),
            "$defs": schema["$defs"],
            "$ref": "#/$defs/Discovery",
        }
    )
    validator.validate(discovery)


def _html_response(name: str, url: str, status: int = 200) -> HttpResponse:
    text = (FIXTURES / name).read_text(encoding="utf-8")
    return HttpResponse(
        status=status,
        headers={"content-type": "text/html; charset=utf-8"},
        text=text,
        final_url=url,
    )


def test_classify_and_normalize_social_urls() -> None:
    ig = classify_url(
        "https://www.instagram.com/risetogetherstudio?igsh=MWh3YzNidG9qYnEwYQ=="
    )
    assert ig.kind == "instagram"
    assert ig.handle == "risetogetherstudio"
    assert ig.canonical == "https://www.instagram.com/risetogetherstudio/"

    fb = classify_url("https://pt-br.facebook.com/MisterRecStudio")
    assert fb.kind == "facebook"
    assert fb.handle == "misterrecstudio"
    assert fb.canonical == "https://www.facebook.com/misterrecstudio/"

    mid = classify_url("https://beacons.ai/grstudio")
    assert mid.kind == "intermediate"

    site = classify_url("https://www.aurorasoundlab.example/")
    assert site.kind == "official_site"

    assert classify_url("https://www.google.com/search?q=MS+Propagandas").kind == "other"
    assert classify_url("https://www.google.com/url?q=https://example.com").kind == "other"
    assert classify_url("https://www.google.com.br/maps/place/foo").kind == "other"

    assert classify_url("https://www.instagram.com/p/shortcode/").kind == "other"
    stripped = strip_tracking_params(
        "https://www.instagram.com/foo/?utm_source=ig&igsh=abc&keep=1"
    )
    assert "utm_source" not in stripped
    assert "igsh" not in stripped
    assert "keep=1" in stripped
    assert normalize_social_url("http://instagram.com/FooBar") == (
        "https://www.instagram.com/foobar/"
    )


def test_direct_instagram_url_selects_without_search() -> None:
    search = FakeSearchProvider(
        default_hits=[
            {
                "url": "https://www.instagram.com/unrelated/",
                "title": "nope",
                "snippet": "nope",
            }
        ]
    )
    studio = _studio(
        contacts={
            "phone": "+55 41 90000-1111",
            "website": "https://www.instagram.com/aurorasoundlab.cwb/",
        }
    )
    outcome = discover_profiles(
        studio,
        http_client=FakeHttpClient(),
        search_provider=search,
        now=_now,
    )
    _assert_valid_discovery(outcome.discovery)
    assert search.queries == []
    assert outcome.discovery["requiresHumanReview"] is False
    selected = outcome.discovery["selectedProfiles"]
    assert "instagram" in selected
    assert selected["instagram"]["value"] == "https://www.instagram.com/aurorasoundlab.cwb/"
    assert selected["instagram"]["confidence"] >= DEFAULT_DISCOVERY_CONFIDENCE_THRESHOLD
    assert any(item["result"] == "skipped_already_matched" for item in outcome.discovery["attempts"])


def test_intermediate_linktree_and_beacons_extract_instagram() -> None:
    linktree = "https://linktr.ee/aurorasoundlab"
    beacons = "https://beacons.ai/aurorasoundlab"
    http = FakeHttpClient(
        {
            linktree: _html_response("linktree_aurora.html", linktree),
            beacons: _html_response("beacons_aurora.html", beacons),
        }
    )
    search = FakeSearchProvider()
    studio = _studio(contacts={"website": linktree})
    outcome = discover_profiles(
        studio, http_client=http, search_provider=search, now=_now
    )
    _assert_valid_discovery(outcome.discovery)
    assert search.queries == []
    assert outcome.discovery["requiresHumanReview"] is False
    assert (
        outcome.discovery["selectedProfiles"]["instagram"]["value"]
        == "https://www.instagram.com/aurorasoundlab.cwb/"
    )
    assert any(item["method"] == "intermediate" for item in outcome.discovery["attempts"])

    studio_b = _studio(contacts={"website": beacons})
    outcome_b = discover_profiles(
        studio_b, http_client=http, search_provider=search, now=_now
    )
    _assert_valid_discovery(outcome_b.discovery)
    assert "instagram" in outcome_b.discovery["selectedProfiles"]


def test_search_finds_profile_when_no_direct_social() -> None:
    search = FakeSearchProvider.from_fixture(FIXTURES / "search_aurora.json")
    studio = _studio()
    outcome = discover_profiles(
        studio,
        http_client=FakeHttpClient(),
        search_provider=search,
        now=_now,
    )
    _assert_valid_discovery(outcome.discovery)
    assert search.queries
    assert any("Instagram" in query for query in search.queries)
    assert outcome.discovery["requiresHumanReview"] is False
    assert (
        outcome.discovery["selectedProfiles"]["instagram"]["value"]
        == "https://www.instagram.com/aurorasoundlab.cwb/"
    )


def test_ambiguous_instagram_profiles_require_human_review() -> None:
    url = "https://linktr.ee/aurora-ambiguous"
    http = FakeHttpClient({url: _html_response("linktree_ambiguous.html", url)})
    search = FakeSearchProvider()
    studio = _studio(contacts={"website": url})
    outcome = discover_profiles(
        studio, http_client=http, search_provider=search, now=_now
    )
    _assert_valid_discovery(outcome.discovery)
    assert search.queries == []
    assert outcome.discovery["requiresHumanReview"] is True
    assert outcome.discovery["selectedProfiles"] == {}
    handles = {item["handle"] for item in outcome.candidates if item["platform"] == "instagram"}
    assert handles == {"aurora.sound.lab", "aurorasoundlab.cwb"}
    assert all(item["score"] >= DEFAULT_DISCOVERY_CONFIDENCE_THRESHOLD for item in outcome.candidates)
    assert any(item["result"] == "ambiguous_instagram" for item in outcome.discovery["attempts"])


def test_none_found_requires_review() -> None:
    studio = _studio()
    outcome = discover_profiles(
        studio,
        http_client=FakeHttpClient(),
        search_provider=NullSearchProvider(),
        now=_now,
    )
    _assert_valid_discovery(outcome.discovery)
    assert outcome.discovery["requiresHumanReview"] is True
    assert outcome.discovery["selectedProfiles"] == {}
    assert outcome.candidates == []
    assert any(warning["code"] == SOCIAL_NOT_FOUND for warning in outcome.warnings)


def test_blocked_intermediate_records_warning_without_evasion() -> None:
    url = "https://linktr.ee/blocked-studio"
    http = FakeHttpClient(
        {
            url: HttpResponse(
                status=403,
                headers={"content-type": "text/html"},
                text="<html>Forbidden</html>",
                final_url=url,
            )
        }
    )
    studio = _studio(contacts={"website": url})
    outcome = discover_profiles(
        studio,
        http_client=http,
        search_provider=NullSearchProvider(),
        now=_now,
    )
    _assert_valid_discovery(outcome.discovery)
    assert http.requested == [url]
    assert any(warning["code"] == PLATFORM_BLOCKED for warning in outcome.warnings)
    assert any(item["result"] == PLATFORM_BLOCKED for item in outcome.discovery["attempts"])
    assert outcome.discovery["requiresHumanReview"] is True
    assert outcome.discovery["selectedProfiles"] == {}
    assert DEFAULT_USER_AGENT.startswith("studio-pipeline/")


def test_instagram_preferred_over_facebook_when_both_valid() -> None:
    studio = _studio(
        contacts={
            "phone": "+55 41 90000-1111",
            "website": "https://www.aurorasoundlab.example/",
            "instagram": "https://www.instagram.com/aurorasoundlab.cwb/",
            "facebook": "https://www.facebook.com/aurorasoundlab.cwb/",
        }
    )
    search = FakeSearchProvider()
    outcome = discover_profiles(
        studio,
        http_client=FakeHttpClient(),
        search_provider=search,
        now=_now,
    )
    _assert_valid_discovery(outcome.discovery)
    assert search.queries == []
    selected = outcome.discovery["selectedProfiles"]
    assert "instagram" in selected
    assert selected["instagram"]["value"] == "https://www.instagram.com/aurorasoundlab.cwb/"
    assert "facebook" in selected
    assert selected["facebook"]["value"] == "https://www.facebook.com/aurorasoundlab.cwb/"
    assert outcome.discovery["requiresHumanReview"] is False
    ig = next(item for item in outcome.candidates if item["platform"] == "instagram")
    fb = next(item for item in outcome.candidates if item["platform"] == "facebook")
    assert ig["score"] >= DEFAULT_DISCOVERY_CONFIDENCE_THRESHOLD
    assert fb["score"] >= DEFAULT_DISCOVERY_CONFIDENCE_THRESHOLD


def test_search_runs_when_source_profile_is_below_threshold() -> None:
    search = FakeSearchProvider.from_fixture(FIXTURES / "search_aurora.json")
    studio = _studio(
        contacts={
            "phone": "+55 41 90000-1111",
            "website": "https://www.aurorasoundlab.example/",
            "instagram": "https://www.instagram.com/unrelatedxyz/",
        }
    )
    outcome = discover_profiles(
        studio,
        http_client=FakeHttpClient(),
        search_provider=search,
        now=_now,
    )
    _assert_valid_discovery(outcome.discovery)
    assert search.queries
    assert outcome.discovery["requiresHumanReview"] is False
    assert (
        outcome.discovery["selectedProfiles"]["instagram"]["value"]
        == "https://www.instagram.com/aurorasoundlab.cwb/"
    )
    assert not any(
        item["result"] == "skipped_already_matched" for item in outcome.discovery["attempts"]
    )


def test_null_search_provider_when_api_key_empty(tmp_path: Path) -> None:
    config = load_config(
        environ={
            "SEARCH_API_KEY": "",
            "SEARCH_PROVIDER": "google",
            "LOG_LEVEL": "info",
        },
        dotenv_path=tmp_path / "missing.env",
    )
    provider = create_search_provider(config)
    assert isinstance(provider, NullSearchProvider)
    assert provider.search("Aurora Sound Lab Instagram") == []
    assert config.discovery_confidence_threshold == DEFAULT_DISCOVERY_CONFIDENCE_THRESHOLD
    text = repr(config)
    assert "SEARCH_API_KEY" not in text
    assert "ai_api_key='***'" in text or "ai_api_key=''" in text
