"""Collect public commercial facts (plan §8 etapa D / §17 M3).

Every published fact is Evidence with sourceUrl, sourceType, collectedAt,
and confidence. Missing data is omitted. Conflicts are kept with a warning.
Does not save files. Tests must inject HttpClient / PlacesProvider.
"""

from __future__ import annotations

import copy
import json
from collections.abc import Callable, Mapping
from typing import Any
from urllib.parse import quote

from studio_pipeline.clock import utc_now_iso
from studio_pipeline.discovery.classify import (
    classify_url,
    hostname_of,
    is_google_host,
    looks_like_login_url,
)
from studio_pipeline.enrichment.html import (
    MAX_PAGES,
    PageFacts,
    excerpt_of,
    follow_candidates,
    is_google_maps_url,
    parse_official_html,
    same_host,
)
from studio_pipeline.enrichment.places import (
    FakePlacesProvider,
    NullPlacesProvider,
    PlacesProvider,
    PlacesResult,
    create_places_provider,
)
from studio_pipeline.errors import HTTP_NOT_FOUND, HTTP_TIMEOUT, PLATFORM_BLOCKED
from studio_pipeline.http.client import is_public_http_url

STAGE = "enriching"
FACT_KEYS = (
    "description",
    "equipment",
    "prices",
    "openingHours",
    "googleReviews",
    "map",
)
SOURCE_TYPES = frozenset(
    {"official_site", "instagram", "facebook", "google", "directory", "source_json"}
)

# Official site and Google outrank imported JSON (plan §3).
CONFIDENCE = {
    "official_site": {
        "description": 0.95,
        "equipment": 0.93,
        "prices": 0.91,
        "openingHours": 0.88,
        "map": 0.85,
    },
    "google": {
        "googleReviews": 0.84,
        "map": 0.86,
    },
    "source_json": {
        "googleReviews": 0.55,
        "map": 0.50,
    },
    "directory": {
        "prices": 0.35,
        "googleReviews": 0.40,
        "map": 0.40,
    },
}

CAPTCHA_MARKERS = (
    "solve this captcha",
    "confirm you are human",
    "confirm you're human",
    "unusual traffic",
    "security check required",
)


def empty_facts() -> dict[str, list[Any]]:
    return {key: [] for key in FACT_KEYS}


def enrich_facts(
    studio: dict,
    dossier: dict,
    *,
    http_client=None,
    places_provider=None,
    config=None,
    now: Callable[[], str] | None = None,
) -> dict[str, Any]:
    """Return updated dossier['facts'] plus extra warnings to merge. Do not save files.

    Return shape::

        {"facts": {description, equipment, prices, openingHours, googleReviews, map},
         "warnings": [PipelineWarning, ...]}
    """
    _ = config
    clock = now or utc_now_iso
    collected_at = clock()
    facts = _copy_facts(dossier.get("facts") if isinstance(dossier, dict) else None)
    warnings: list[dict[str, Any]] = []

    _add_source_json_facts(studio, facts, collected_at)
    _add_official_site_facts(
        studio,
        facts,
        warnings,
        http_client=http_client,
        collected_at=collected_at,
        clock=clock,
    )
    _add_places_facts(
        studio,
        facts,
        warnings,
        places_provider=places_provider,
        collected_at=collected_at,
        clock=clock,
    )
    warnings.extend(_conflict_warnings(facts, collected_at))
    return {"facts": facts, "warnings": warnings}


def make_evidence(
    value: Any,
    *,
    source_url: str,
    source_type: str,
    collected_at: str,
    confidence: float,
    excerpt: str | None = None,
) -> dict[str, Any] | None:
    if value is None or value == [] or value == {}:
        return None
    if source_type not in SOURCE_TYPES:
        return None
    url = str(source_url or "").strip()
    if not url:
        return None
    payload: dict[str, Any] = {
        "value": value,
        "sourceUrl": url,
        "sourceType": source_type,
        "collectedAt": collected_at,
        "confidence": _clamp_confidence(confidence),
    }
    if excerpt:
        payload["excerpt"] = excerpt
    return payload


def append_evidence(bucket: list[dict[str, Any]], evidence: dict[str, Any] | None) -> None:
    if not evidence:
        return
    for existing in bucket:
        if (
            existing.get("sourceUrl") == evidence.get("sourceUrl")
            and existing.get("sourceType") == evidence.get("sourceType")
            and existing.get("value") == evidence.get("value")
        ):
            return
    bucket.append(evidence)


def _copy_facts(raw: object) -> dict[str, list[Any]]:
    facts = empty_facts()
    if not isinstance(raw, dict):
        return facts
    for key in FACT_KEYS:
        items = raw.get(key)
        if isinstance(items, list):
            facts[key] = [copy.deepcopy(item) for item in items if isinstance(item, dict)]
    return facts


def _clamp_confidence(value: float) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return 0.0
    return max(0.0, min(1.0, number))


def _warning(
    code: str,
    message: str,
    at: str,
    *,
    retryable: bool = False,
) -> dict[str, Any]:
    return {
        "code": code,
        "message": message,
        "stage": STAGE,
        "at": at,
        "retryable": retryable,
    }


def _source_json_url(studio: dict[str, Any]) -> str:
    studio_id = str(studio.get("studioId") or "studio").strip() or "studio"
    return f"urn:studio-pipeline:source-json:{studio_id}"


def _original_record(studio: dict[str, Any]) -> dict[str, Any]:
    source = studio.get("source")
    if not isinstance(source, dict):
        return {}
    original = source.get("originalRecord")
    return original if isinstance(original, dict) else {}


def _as_float(value: object) -> float | None:
    if value is None or value == "" or isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _as_count(value: object) -> int | None:
    number = _as_float(value)
    if number is None or number < 0 or number != int(number):
        return None
    return int(number)


def _add_source_json_facts(
    studio: dict[str, Any],
    facts: dict[str, list[Any]],
    collected_at: str,
) -> None:
    original = _original_record(studio)
    if not original:
        return
    source_url = _source_json_url(studio)
    reviews = _reviews_from_original(original)
    if reviews:
        original_bits = []
        if "rating" in original:
            original_bits.append(f"rating={original.get('rating')}")
        if "ratingCount" in original:
            original_bits.append(f"ratingCount={original.get('ratingCount')}")
        append_evidence(
            facts["googleReviews"],
            make_evidence(
                reviews,
                source_url=source_url,
                source_type="source_json",
                collected_at=collected_at,
                confidence=CONFIDENCE["source_json"]["googleReviews"],
                excerpt=excerpt_of(" ".join(original_bits) or json.dumps(reviews)),
            ),
        )
    mapped = _map_from_original(original)
    if mapped:
        original_address = str(original.get("address") or "").strip()
        append_evidence(
            facts["map"],
            make_evidence(
                mapped,
                source_url=source_url,
                source_type="source_json",
                collected_at=collected_at,
                confidence=CONFIDENCE["source_json"]["map"],
                excerpt=excerpt_of(original_address or json.dumps(mapped, ensure_ascii=False)),
            ),
        )


def _reviews_from_original(original: Mapping[str, Any]) -> dict[str, Any] | None:
    payload: dict[str, Any] = {}
    rating = _as_float(original.get("rating"))
    if rating is not None and 0 <= rating <= 5:
        payload["rating"] = int(rating) if rating == int(rating) else rating
    count = _as_count(original.get("ratingCount"))
    if count is not None:
        payload["count"] = count
    return payload or None


def _map_from_original(original: Mapping[str, Any]) -> dict[str, Any] | None:
    payload: dict[str, Any] = {}
    lat = _as_float(original.get("latitude"))
    lng = _as_float(original.get("longitude"))
    if lat is not None and -90 <= lat <= 90:
        payload["latitude"] = lat
    if lng is not None and -180 <= lng <= 180:
        payload["longitude"] = lng
    address = str(original.get("address") or "").strip()
    if address:
        payload["address"] = address
    return payload or None


def _official_website(studio: dict[str, Any]) -> str | None:
    contacts = studio.get("contacts")
    if not isinstance(contacts, dict):
        return None
    website = str(contacts.get("website") or "").strip()
    if not website:
        return None
    if not is_public_http_url(website):
        return None
    if is_google_maps_url(website) or is_google_host(hostname_of(website)):
        return None
    if looks_like_login_url(website):
        return None
    if classify_url(website).kind != "official_site":
        return None
    return website


def _add_official_site_facts(
    studio: dict[str, Any],
    facts: dict[str, list[Any]],
    warnings: list[dict[str, Any]],
    *,
    http_client: Any,
    collected_at: str,
    clock: Callable[[], str],
) -> None:
    website = _official_website(studio)
    if website is None:
        return
    if http_client is None or not hasattr(http_client, "get"):
        warnings.append(
            _warning(
                "OFFICIAL_SITE_SKIPPED",
                "Official site was not fetched: no HTTP client was injected",
                clock(),
            )
        )
        return
    seed = website
    queue = [seed]
    seen: set[str] = set()
    fetched = 0
    while queue and fetched < MAX_PAGES:
        url = queue.pop(0)
        key = url.strip().rstrip("/")
        if key in seen:
            continue
        seen.add(key)
        if not is_public_http_url(url) or looks_like_login_url(url):
            continue
        if is_google_maps_url(url) or is_google_host(hostname_of(url)):
            continue
        if classify_url(url).kind != "official_site":
            continue
        status, text, final_url = _http_get(http_client, url)
        fetched += 1
        at = clock()
        if status == 0:
            warnings.append(
                _warning(HTTP_TIMEOUT, f"timeout fetching official site page {url}", at, retryable=True)
            )
            continue
        if status in {401, 403, 451}:
            warnings.append(
                _warning(PLATFORM_BLOCKED, f"official site blocked (HTTP {status})", at)
            )
            continue
        if status in {404, 410}:
            warnings.append(
                _warning(HTTP_NOT_FOUND, f"official site page not found (HTTP {status})", at)
            )
            continue
        if status >= 400:
            warnings.append(
                _warning(PLATFORM_BLOCKED, f"official site blocked (HTTP {status})", at)
            )
            continue
        if looks_like_login_url(final_url) or not same_host(final_url, seed):
            warnings.append(
                _warning(PLATFORM_BLOCKED, "official site redirected away from the public host", at)
            )
            continue
        if _looks_like_captcha(text):
            warnings.append(
                _warning(PLATFORM_BLOCKED, "official site presented a CAPTCHA or challenge", at)
            )
            continue
        page = parse_official_html(text, base_url=final_url or url)
        _merge_page_facts(facts, page, source_url=final_url or url, collected_at=collected_at)
        if fetched == 1:
            for candidate in follow_candidates(page, seed_url=seed):
                cand_key = candidate.strip().rstrip("/")
                if cand_key not in seen:
                    queue.append(candidate)


def _looks_like_captcha(text: str) -> bool:
    blob = (text or "").lower()
    return any(marker in blob for marker in CAPTCHA_MARKERS)


def _http_get(http_client: Any, url: str) -> tuple[int, str, str]:
    try:
        raw = http_client.get(url)
    except TimeoutError:
        return 0, "", url
    except Exception as exc:
        if "time" in type(exc).__name__.lower() or "timed out" in str(exc).lower():
            return 0, "", url
        return 0, "", url
    if isinstance(raw, tuple) and len(raw) == 4:
        status, _headers, text, final_url = raw
        return int(status or 0), str(text or ""), str(final_url or url)
    status = getattr(raw, "status", None)
    if status is None:
        return 0, "", url
    text = str(getattr(raw, "text", "") or "")
    final_url = str(getattr(raw, "final_url", "") or url)
    return int(status or 0), text, final_url


def _merge_page_facts(
    facts: dict[str, list[Any]],
    page: PageFacts,
    *,
    source_url: str,
    collected_at: str,
) -> None:
    scores = CONFIDENCE["official_site"]
    if page.description:
        append_evidence(
            facts["description"],
            make_evidence(
                page.description,
                source_url=source_url,
                source_type="official_site",
                collected_at=collected_at,
                confidence=scores["description"],
                excerpt=page.description_excerpt or excerpt_of(page.description),
            ),
        )
    if page.equipment:
        append_evidence(
            facts["equipment"],
            make_evidence(
                list(page.equipment),
                source_url=source_url,
                source_type="official_site",
                collected_at=collected_at,
                confidence=scores["equipment"],
                excerpt=page.equipment_excerpt or excerpt_of("; ".join(page.equipment)),
            ),
        )
    if page.prices:
        append_evidence(
            facts["prices"],
            make_evidence(
                list(page.prices),
                source_url=source_url,
                source_type="official_site",
                collected_at=collected_at,
                confidence=scores["prices"],
                excerpt=page.prices_excerpt,
            ),
        )
    if page.hours:
        append_evidence(
            facts["openingHours"],
            make_evidence(
                list(page.hours),
                source_url=source_url,
                source_type="official_site",
                collected_at=collected_at,
                confidence=scores["openingHours"],
                excerpt=page.hours_excerpt,
            ),
        )
    if page.map:
        append_evidence(
            facts["map"],
            make_evidence(
                dict(page.map),
                source_url=source_url,
                source_type="official_site",
                collected_at=collected_at,
                confidence=scores["map"],
                excerpt=page.map_excerpt,
            ),
        )


def _places_available(provider: Any) -> bool:
    if provider is None:
        return False
    if isinstance(provider, NullPlacesProvider):
        return False
    return bool(getattr(provider, "available", True))


def _add_places_facts(
    studio: dict[str, Any],
    facts: dict[str, list[Any]],
    warnings: list[dict[str, Any]],
    *,
    places_provider: PlacesProvider | None,
    collected_at: str,
    clock: Callable[[], str],
) -> None:
    if not _places_available(places_provider):
        warnings.append(
            _warning(
                "PLACES_UNAVAILABLE",
                "Google/Places skipped: no API key or provider (maps HTML is never scraped)",
                clock(),
            )
        )
        return
    assert places_provider is not None
    location = studio.get("location") if isinstance(studio.get("location"), dict) else {}
    name = str(studio.get("name") or "").strip()
    city = str(location.get("city") or "").strip()
    address = str(location.get("address") or "").strip()
    try:
        result = places_provider.lookup(name, city, address)
    except Exception as exc:
        warnings.append(
            _warning(
                "PLACES_UNAVAILABLE",
                f"Google/Places lookup failed: {type(exc).__name__}",
                clock(),
                retryable=True,
            )
        )
        return
    if not result:
        return
    source_url = _places_source_url(result, name=name, city=city, address=address)
    reviews = _reviews_from_places(result)
    if reviews:
        excerpts = reviews.get("excerpts") or []
        original = excerpts[0] if excerpts else json.dumps(reviews, ensure_ascii=False)
        append_evidence(
            facts["googleReviews"],
            make_evidence(
                reviews,
                source_url=source_url,
                source_type="google",
                collected_at=collected_at,
                confidence=CONFIDENCE["google"]["googleReviews"],
                excerpt=excerpt_of(str(original)),
            ),
        )
    mapped = result.get("map") if isinstance(result.get("map"), dict) else None
    if mapped:
        original_address = str(mapped.get("address") or address or "")
        append_evidence(
            facts["map"],
            make_evidence(
                dict(mapped),
                source_url=source_url,
                source_type="google",
                collected_at=collected_at,
                confidence=CONFIDENCE["google"]["map"],
                excerpt=excerpt_of(original_address or json.dumps(mapped, ensure_ascii=False)),
            ),
        )


def _reviews_from_places(result: PlacesResult) -> dict[str, Any] | None:
    payload: dict[str, Any] = {}
    rating = result.get("rating")
    if isinstance(rating, (int, float)) and 0 <= float(rating) <= 5:
        payload["rating"] = rating
    count = result.get("count")
    if isinstance(count, int) and count >= 0:
        payload["count"] = count
    excerpts = result.get("excerpts")
    if isinstance(excerpts, list):
        cleaned = [str(item).strip() for item in excerpts if str(item).strip()]
        if cleaned:
            payload["excerpts"] = cleaned
    return payload or None


def _places_source_url(
    result: Mapping[str, Any],
    *,
    name: str,
    city: str,
    address: str,
) -> str:
    url = str(result.get("url") or result.get("sourceUrl") or "").strip()
    if url:
        return url
    mapped = result.get("map") if isinstance(result.get("map"), dict) else {}
    place_id = str(mapped.get("placeId") or "").strip()
    if place_id:
        return f"https://www.google.com/maps/search/?api=1&query=place_id:{quote(place_id)}"
    query = " ".join(part for part in (name, city, address) if part)
    return f"https://www.google.com/maps/search/?api=1&query={quote(query or 'studio')}"


def _conflict_warnings(facts: dict[str, list[Any]], collected_at: str) -> list[dict[str, Any]]:
    warnings: list[dict[str, Any]] = []
    checkers = {
        "description": _description_signature,
        "prices": _prices_signature,
        "openingHours": _hours_signature,
        "googleReviews": _reviews_signature,
        "map": _map_signature,
        "equipment": _equipment_signature,
    }
    for key, signature in checkers.items():
        entries = [item for item in facts.get(key) or [] if isinstance(item, dict)]
        if len(entries) < 2:
            continue
        sigs = [signature(item.get("value")) for item in entries]
        unique = {item for item in sigs if item is not None}
        if len(unique) <= 1:
            continue
        sources = sorted(
            {
                str(item.get("sourceType") or "")
                for item in entries
                if item.get("sourceType")
            }
        )
        warnings.append(
            _warning(
                "FACT_CONFLICT",
                f"Conflicting {key} evidence kept from {', '.join(sources) or 'multiple sources'}; "
                "no value was chosen automatically",
                collected_at,
            )
        )
    return warnings


def _description_signature(value: object) -> tuple[Any, ...] | None:
    if not isinstance(value, str):
        return None
    collapsed = " ".join(value.lower().split())
    return (collapsed,) if collapsed else None


def _prices_signature(value: object) -> tuple[Any, ...] | None:
    if not isinstance(value, list) or not value:
        return None
    rows = []
    for item in value:
        if not isinstance(item, dict):
            continue
        rows.append(
            (
                " ".join(str(item.get("label") or "").lower().split()),
                " ".join(str(item.get("amountText") or "").lower().split()),
            )
        )
    return tuple(sorted(rows)) if rows else None


def _hours_signature(value: object) -> tuple[Any, ...] | None:
    if not isinstance(value, list) or not value:
        return None
    rows = []
    for item in value:
        if not isinstance(item, dict):
            continue
        intervals = item.get("intervals") if isinstance(item.get("intervals"), list) else []
        rows.append(
            (
                " ".join(str(item.get("day") or "").lower().split()),
                tuple(str(part) for part in intervals),
            )
        )
    return tuple(sorted(rows)) if rows else None


def _reviews_signature(value: object) -> tuple[Any, ...] | None:
    if not isinstance(value, dict):
        return None
    rating = value.get("rating")
    if not isinstance(rating, (int, float)):
        return None
    return (round(float(rating), 2),)


def _map_signature(value: object) -> tuple[Any, ...] | None:
    if not isinstance(value, dict):
        return None
    lat = value.get("latitude")
    lng = value.get("longitude")
    address = " ".join(str(value.get("address") or "").lower().split())
    lat_r = round(float(lat), 4) if isinstance(lat, (int, float)) else None
    lng_r = round(float(lng), 4) if isinstance(lng, (int, float)) else None
    if lat_r is None and lng_r is None and not address:
        return None
    return (lat_r, lng_r, address)


def _equipment_signature(value: object) -> tuple[Any, ...] | None:
    if not isinstance(value, list) or not value:
        return None
    items = tuple(sorted({" ".join(str(item).lower().split()) for item in value if str(item).strip()}))
    return items or None


__all__ = [
    "CONFIDENCE",
    "FACT_KEYS",
    "FakePlacesProvider",
    "NullPlacesProvider",
    "PlacesProvider",
    "STAGE",
    "append_evidence",
    "create_places_provider",
    "empty_facts",
    "enrich_facts",
    "make_evidence",
]
