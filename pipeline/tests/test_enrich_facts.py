"""M3 factual enrichment: fixtures only, never the network."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from studio_pipeline.config import schemas_dir
from studio_pipeline.enrichment import (
    CONFIDENCE,
    FakePlacesProvider,
    NullPlacesProvider,
    create_places_provider,
    enrich_facts,
)
from studio_pipeline.http.client import FakeHttpClient, HttpResponse
from studio_pipeline.validation.schemas import load_json, make_validator

FIXTURES = Path(__file__).parent / "fixtures" / "enrichment"
NOW = "2026-08-12T15:00:00Z"
SITE = "https://www.aurorasoundlab.example/"
HOURS_URL = "https://www.aurorasoundlab.example/horarios"
ABOUT_URL = "https://www.aurorasoundlab.example/sobre"
CONTACT_URL = "https://www.aurorasoundlab.example/contato"
PRICES_URL = "https://www.aurorasoundlab.example/precos"


def _now() -> str:
    return NOW


def _html_response(name: str, url: str, status: int = 200) -> HttpResponse:
    text = (FIXTURES / name).read_text(encoding="utf-8")
    return HttpResponse(
        status=status,
        headers={"content-type": "text/html; charset=utf-8"},
        text=text,
        final_url=url,
    )


def _official_http() -> FakeHttpClient:
    return FakeHttpClient(
        {
            SITE: _html_response("official_site.html", SITE),
            HOURS_URL: _html_response("hours.html", HOURS_URL),
            ABOUT_URL: _html_response("about.html", ABOUT_URL),
            CONTACT_URL: _html_response("contact.html", CONTACT_URL),
            PRICES_URL: _html_response("prices.html", PRICES_URL),
        }
    )


def _empty_dossier(studio_id: str = "aurora-sound-lab-cwb") -> dict[str, Any]:
    return {
        "schemaVersion": 1,
        "studioId": studio_id,
        "discovery": {
            "attempts": [],
            "selectedProfiles": {},
            "requiresHumanReview": False,
        },
        "social": {"highlights": [], "posts": []},
        "facts": {
            "description": [],
            "equipment": [],
            "prices": [],
            "openingHours": [],
            "googleReviews": [],
            "map": [],
        },
        "media": {"candidates": [], "selected": []},
        "warnings": [],
    }


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
            "website": SITE,
        },
        "source": {
            "importedAt": NOW,
            "sourceFile": "fixture.json",
            "sourceHash": "0" * 64,
            "originalRecord": {
                "title": "Aurora Sound Lab",
                "cidade": "Curitiba",
                "website": SITE,
            },
        },
        "pipelineStatus": "enriching",
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


def _assert_valid_facts(facts: dict[str, Any]) -> None:
    schema = load_json(schemas_dir() / "dossier.schema.json")
    validator = make_validator(
        {
            "$schema": schema.get("$schema"),
            "$defs": schema["$defs"],
            "$ref": "#/$defs/Facts",
        }
    )
    validator.validate(facts)


def _assert_valid_warnings(warnings: list[dict[str, Any]]) -> None:
    schema = load_json(schemas_dir() / "dossier.schema.json")
    validator = make_validator(
        {
            "$schema": schema.get("$schema"),
            "$defs": schema["$defs"],
            "$ref": "#/$defs/PipelineWarning",
        }
    )
    for warning in warnings:
        validator.validate(warning)


def _enrich(
    studio: dict[str, Any],
    dossier: dict[str, Any] | None = None,
    **kwargs: Any,
) -> dict[str, Any]:
    kwargs.setdefault("now", _now)
    kwargs.setdefault("places_provider", FakePlacesProvider())
    return enrich_facts(studio, dossier or _empty_dossier(), **kwargs)


def test_official_site_html_fills_equipment_and_hours_with_source_url() -> None:
    http = _official_http()
    result = _enrich(_studio(), http_client=http)
    facts = result["facts"]
    _assert_valid_facts(facts)
    _assert_valid_warnings(result["warnings"])

    assert facts["equipment"], "equipment should be parsed from the official site"
    equipment = facts["equipment"][0]
    assert equipment["sourceType"] == "official_site"
    assert equipment["sourceUrl"].startswith("https://www.aurorasoundlab.example")
    assert "Mesa analógica SSL" in equipment["value"]
    assert "Microfone Neumann TLM 103" in equipment["value"]
    assert 0 <= equipment["confidence"] <= 1
    assert equipment["collectedAt"] == NOW

    assert facts["openingHours"], "hours should be followed from the horarios link"
    hours = facts["openingHours"][0]
    assert hours["sourceType"] == "official_site"
    assert hours["sourceUrl"] == HOURS_URL
    days = {row["day"]: row["intervals"] for row in hours["value"]}
    assert days["Segunda a Sexta"] == ["10:00-22:00"]
    assert days["Sábado"] == ["11:00-20:00"]
    assert "Domingo" in days
    assert any("horarios" in url or url.rstrip("/") == SITE.rstrip("/") for url in http.requested)


def test_invalid_or_missing_website_leaves_facts_empty() -> None:
    dossier = _empty_dossier()
    missing = _enrich(_studio(contacts={"website": ""}), dossier, http_client=FakeHttpClient())
    assert missing["facts"]["description"] == []
    assert missing["facts"]["equipment"] == []
    assert missing["facts"]["prices"] == []
    assert missing["facts"]["openingHours"] == []
    assert missing["facts"]["googleReviews"] == []
    assert missing["facts"]["map"] == []
    _assert_valid_facts(missing["facts"])

    invalid = _enrich(
        _studio(contacts={"website": "not a uri"}),
        _empty_dossier(),
        http_client=FakeHttpClient(),
    )
    assert invalid["facts"] == missing["facts"]

    social_only = _enrich(
        _studio(contacts={"website": "https://www.instagram.com/aurorasoundlab.cwb/"}),
        _empty_dossier(),
        http_client=FakeHttpClient(),
    )
    assert social_only["facts"]["equipment"] == []
    assert social_only["facts"]["openingHours"] == []


def test_source_json_rating_becomes_google_reviews_evidence() -> None:
    studio = _studio(
        contacts={"website": ""},
        source={
            "originalRecord": {
                "rating": 4.8,
                "ratingCount": 42,
                "address": "Rua Fictícia do Ensaio, 240, Curitiba - PR",
                "latitude": -25.4298,
                "longitude": -49.2714,
            }
        },
    )
    result = _enrich(studio, http_client=FakeHttpClient())
    reviews = result["facts"]["googleReviews"]
    assert len(reviews) == 1
    evidence = reviews[0]
    assert evidence["sourceType"] == "source_json"
    assert evidence["value"]["rating"] == 4.8
    assert evidence["value"]["count"] == 42
    assert evidence["sourceUrl"].startswith("urn:studio-pipeline:source-json:")
    assert evidence["confidence"] == CONFIDENCE["source_json"]["googleReviews"]
    assert evidence["confidence"] < CONFIDENCE["google"]["googleReviews"]
    _assert_valid_facts(result["facts"])


def test_conflicting_descriptions_are_kept_with_warning() -> None:
    dossier = _empty_dossier()
    dossier["facts"]["description"] = [
        {
            "value": "A totally different blurb from a directory listing.",
            "sourceUrl": "https://directory.example/aurora-sound-lab",
            "sourceType": "directory",
            "collectedAt": NOW,
            "confidence": 0.3,
            "excerpt": "A totally different blurb from a directory listing.",
        }
    ]
    http = FakeHttpClient({SITE: _html_response("official_site.html", SITE)})
    result = _enrich(_studio(), dossier, http_client=http)
    descriptions = result["facts"]["description"]
    assert len(descriptions) >= 2
    values = {item["value"] for item in descriptions}
    assert "A totally different blurb from a directory listing." in values
    assert any("Curitiba" in str(item["value"]) for item in descriptions)
    assert all(item.get("sourceUrl") for item in descriptions)
    assert any(warning["code"] == "FACT_CONFLICT" for warning in result["warnings"])
    _assert_valid_facts(result["facts"])
    _assert_valid_warnings(result["warnings"])


def test_conflicting_prices_from_site_and_directory_are_kept_with_warning() -> None:
    directory = {
        "value": [
            {
                "label": "Ensaio 2 horas",
                "amountText": "R$ 90",
                "conditions": "Listagem de diretório.",
            }
        ],
        "sourceUrl": "https://directory.example/aurora-sound-lab",
        "sourceType": "directory",
        "collectedAt": NOW,
        "confidence": 0.35,
        "excerpt": "Ensaio 2 horas — R$ 90",
    }
    dossier = _empty_dossier()
    dossier["facts"]["prices"] = [directory]
    http = FakeHttpClient({PRICES_URL: _html_response("prices.html", PRICES_URL)})
    studio = _studio(contacts={"website": PRICES_URL})
    result = _enrich(studio, dossier, http_client=http)
    prices = result["facts"]["prices"]
    assert len(prices) == 2
    types = {item["sourceType"] for item in prices}
    assert types == {"official_site", "directory"}
    amounts = {
        item["sourceType"]: item["value"][0]["amountText"]
        for item in prices
        if item.get("value")
    }
    assert amounts["official_site"] == "R$ 120"
    assert amounts["directory"] == "R$ 90"
    assert any(warning["code"] == "FACT_CONFLICT" for warning in result["warnings"])
    _assert_valid_facts(result["facts"])
    _assert_valid_warnings(result["warnings"])


def test_fake_places_provider_outranks_source_json_confidence() -> None:
    studio = _studio(
        source={
            "originalRecord": {
                "rating": 4.8,
                "ratingCount": 42,
                "address": "Rua Fictícia do Ensaio, 240, Curitiba - PR",
                "latitude": -25.4298,
                "longitude": -49.2714,
            }
        },
    )
    places = FakePlacesProvider.from_fixture(FIXTURES / "places_aurora.json")
    result = _enrich(
        studio,
        http_client=FakeHttpClient(),
        places_provider=places,
    )
    reviews = result["facts"]["googleReviews"]
    by_type = {item["sourceType"]: item for item in reviews}
    assert "source_json" in by_type
    assert "google" in by_type
    assert by_type["google"]["value"]["rating"] == 4.9
    assert by_type["google"]["value"]["count"] == 128
    assert by_type["google"]["sourceUrl"] == "https://maps.example.com/place/aurora-sound-lab-cwb"
    assert by_type["google"]["confidence"] > by_type["source_json"]["confidence"]
    assert by_type["google"]["confidence"] == CONFIDENCE["google"]["googleReviews"]
    assert places.lookups
    _assert_valid_facts(result["facts"])


def test_html_without_prices_does_not_invent_prices() -> None:
    http = FakeHttpClient({SITE: _html_response("no_prices.html", SITE)})
    result = _enrich(_studio(), http_client=http)
    facts = result["facts"]
    assert facts["prices"] == []
    assert facts["equipment"], "equipment from the page must still be recorded"
    assert "R$" not in str(facts["equipment"])
    _assert_valid_facts(facts)


def test_null_places_provider_skips_without_scraping_maps() -> None:
    http = FakeHttpClient()
    result = _enrich(
        _studio(contacts={"website": ""}),
        http_client=http,
        places_provider=NullPlacesProvider(),
    )
    assert result["facts"]["googleReviews"] == []
    assert any(warning["code"] == "PLACES_UNAVAILABLE" for warning in result["warnings"])
    assert http.requested == []
    assert not any("google.com/maps" in url for url in http.requested)


def test_create_places_provider_ignores_search_config() -> None:
    class SearchCfg:
        search_api_key = "search-secret"
        search_provider = "fake"

    provider = create_places_provider(SearchCfg())
    assert isinstance(provider, NullPlacesProvider)
    assert provider.lookup("Aurora Sound Lab", "Curitiba", "") is None

    class FakePlacesCfg:
        places_provider = "fake"

    fake = create_places_provider(FakePlacesCfg())
    assert isinstance(fake, FakePlacesProvider)


def test_google_search_website_is_not_fetched_as_official_site() -> None:
    google = "https://www.google.com/search?q=MS+Propagandas"
    http = FakeHttpClient(
        {
            google: HttpResponse(
                status=200,
                headers={"content-type": "text/html; charset=utf-8"},
                text="<html><body>Knowledge panel hours 09:00</body></html>",
                final_url=google,
            )
        }
    )
    result = _enrich(
        _studio(contacts={"website": google}),
        http_client=http,
        places_provider=NullPlacesProvider(),
    )
    assert http.requested == []
    assert result["facts"]["openingHours"] == []
    assert result["facts"]["equipment"] == []
    _assert_valid_facts(result["facts"])
