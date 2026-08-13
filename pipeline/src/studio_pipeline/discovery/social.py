"""Social/web discovery (plan §8 etapa B). No login, cookies, or evasion."""

from __future__ import annotations

from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlparse

from studio_pipeline.clock import utc_now_iso
from studio_pipeline.config import (
    DEFAULT_DISCOVERY_AMBIGUITY_MARGIN,
    DEFAULT_DISCOVERY_CONFIDENCE_THRESHOLD,
    Config,
)
from studio_pipeline.discovery.classify import (
    UrlClassification,
    classify_url,
    looks_like_login_url,
)
from studio_pipeline.discovery.extract import extract_urls_from_html
from studio_pipeline.discovery.score import ScoreContext, ScoredCandidate, score_candidate
from studio_pipeline.errors import (
    HTTP_TIMEOUT,
    PLATFORM_BLOCKED,
    RATE_LIMITED,
    SOCIAL_AMBIGUOUS,
    SOCIAL_NOT_FOUND,
)
from studio_pipeline.http.client import HttpClient, HttpResponse, is_public_http_url
from studio_pipeline.search.provider import NullSearchProvider, SearchHit, SearchProvider

STAGE = "discovering"
MAX_INTERMEDIATE_FETCHES = 8
MAX_SEARCH_QUERIES = 8
METHOD_RANK = {"direct_url": 3, "source_field": 3, "intermediate": 2, "web_search": 1}
_SKIP_SEARCH_REASONS = frozenset(
    {
        "selected",
        "selected_facebook_fallback",
        "ambiguous_instagram",
        "ambiguous_facebook",
    }
)

_URL_KEYS = frozenset(
    {
        "website",
        "instagram",
        "facebook",
        "url",
        "instagramurl",
        "facebookurl",
        "valor",
    }
)


@dataclass
class DiscoveryOutcome:
    """Return value for the orchestrator. `discovery` matches dossier.discovery."""

    discovery: dict[str, Any]
    candidates: list[dict[str, Any]] = field(default_factory=list)
    warnings: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class _Seed:
    url: str
    origin: str
    first_party: bool


@dataclass
class _RawCandidate:
    platform: str
    url: str
    handle: str
    method: str
    source_url: str
    title: str = ""
    snippet: str = ""
    first_party: bool = False


def _warning(code: str, message: str, now: str, *, retryable: bool = False) -> dict[str, Any]:
    return {
        "code": code,
        "message": message,
        "stage": STAGE,
        "at": now,
        "retryable": retryable,
    }


def _attempt(
    *,
    now: str,
    method: str,
    result: str,
    url: str | None = None,
    query: str | None = None,
    evidence: dict[str, Any] | None = None,
) -> dict[str, Any]:
    item: dict[str, Any] = {"at": now, "method": method, "result": result}
    if url and urlparse(url).scheme in {"http", "https"}:
        item["url"] = url
    if query:
        item["query"] = query
    if evidence:
        item["evidence"] = evidence
    return item


def _iter_url_strings(value: Any, *, depth: int = 0) -> Iterator[str]:
    if depth > 5 or value is None:
        return
    if isinstance(value, str):
        text = value.strip()
        if text.lower().startswith(("http://", "https://")):
            yield text.split()[0].rstrip(".,);")
        return
    if isinstance(value, dict):
        for key, child in value.items():
            key_l = str(key).lower()
            if key_l in _URL_KEYS or depth <= 2:
                yield from _iter_url_strings(child, depth=depth + 1)
        return
    if isinstance(value, list):
        for child in value:
            yield from _iter_url_strings(child, depth=depth + 1)


def collect_seed_urls(studio: dict[str, Any]) -> list[_Seed]:
    seeds: list[_Seed] = []
    seen: set[str] = set()

    def add(url: str, origin: str, first_party: bool) -> None:
        text = (url or "").strip()
        if not text or text in seen:
            return
        if not text.lower().startswith(("http://", "https://")):
            return
        seen.add(text)
        seeds.append(_Seed(url=text, origin=origin, first_party=first_party))

    contacts = studio.get("contacts") if isinstance(studio.get("contacts"), dict) else {}
    for key in ("website", "instagram", "facebook"):
        value = contacts.get(key)
        if isinstance(value, str):
            add(value, f"contacts.{key}", True)

    source = studio.get("source") if isinstance(studio.get("source"), dict) else {}
    original = source.get("originalRecord")
    if isinstance(original, dict):
        for key in ("website", "instagram", "facebook"):
            value = original.get(key)
            if isinstance(value, str):
                add(value, f"originalRecord.{key}", True)
        for found in _iter_url_strings(original):
            add(found, "originalRecord", True)
    return seeds


def build_search_queries(studio: dict[str, Any]) -> list[str]:
    name = str(studio.get("name") or "").strip()
    location = studio.get("location") if isinstance(studio.get("location"), dict) else {}
    city = str(location.get("city") or "").strip()
    state = str(location.get("state") or "").strip()
    address = str(location.get("address") or "").strip()
    queries: list[str] = []
    seen: set[str] = set()

    def add(parts: list[str]) -> None:
        text = " ".join(part for part in parts if part).strip()
        key = " ".join(text.lower().split())
        if not text or key in seen:
            return
        seen.add(key)
        queries.append(text)

    if not name:
        return []
    for network in ("Instagram", "Facebook"):
        add([name, network])
        add([name, city, network])
        add([name, city, state, network])
        add([name, address, network])
    return queries[:MAX_SEARCH_QUERIES]


def _is_blocked(response: HttpResponse) -> bool:
    if response.status in {401, 403}:
        return True
    if looks_like_login_url(response.final_url or ""):
        return True
    return False


def _merge_raw(existing: _RawCandidate, incoming: _RawCandidate) -> _RawCandidate:
    keep = existing
    if METHOD_RANK.get(incoming.method, 0) > METHOD_RANK.get(existing.method, 0):
        keep = incoming
        keep.title = keep.title or existing.title
        keep.snippet = keep.snippet or existing.snippet
        keep.first_party = keep.first_party or existing.first_party
        return keep
    existing.first_party = existing.first_party or incoming.first_party
    if incoming.title and not existing.title:
        existing.title = incoming.title
    if incoming.snippet and not existing.snippet:
        existing.snippet = incoming.snippet
    return existing


def _add_raw(
    bucket: dict[tuple[str, str], _RawCandidate],
    classified: UrlClassification,
    *,
    method: str,
    source_url: str,
    first_party: bool,
    title: str = "",
    snippet: str = "",
) -> _RawCandidate | None:
    if classified.kind not in {"instagram", "facebook"}:
        return None
    if not classified.canonical or not classified.handle or not classified.platform:
        return None
    key = (classified.platform, classified.handle)
    incoming = _RawCandidate(
        platform=classified.platform,
        url=classified.canonical,
        handle=classified.handle,
        method=method,
        source_url=source_url,
        title=title,
        snippet=snippet,
        first_party=first_party,
    )
    if key in bucket:
        bucket[key] = _merge_raw(bucket[key], incoming)
    else:
        bucket[key] = incoming
    return bucket[key]


def _score_context(studio: dict[str, Any]) -> ScoreContext:
    location = studio.get("location") if isinstance(studio.get("location"), dict) else {}
    contacts = studio.get("contacts") if isinstance(studio.get("contacts"), dict) else {}
    website = str(contacts.get("website") or "")
    host = (urlparse(website).hostname or "").lower()
    return ScoreContext(
        name=str(studio.get("name") or ""),
        city=str(location.get("city") or ""),
        state=str(location.get("state") or ""),
        address=str(location.get("address") or ""),
        phone=str(contacts.get("phone") or ""),
        website_host=host,
    )


def _score_raw_candidates(
    bucket: dict[tuple[str, str], _RawCandidate],
    context: ScoreContext,
) -> list[ScoredCandidate]:
    scored = [
        score_candidate(
            platform=raw.platform,
            url=raw.url,
            handle=raw.handle,
            method=raw.method,
            source_url=raw.source_url,
            title=raw.title,
            snippet=raw.snippet,
            first_party=raw.first_party,
            context=context,
        )
        for raw in bucket.values()
    ]
    scored.sort(
        key=lambda item: (-item.score, 0 if item.platform == "instagram" else 1, item.handle)
    )
    return scored


def _candidate_dict(item: ScoredCandidate) -> dict[str, Any]:
    return {
        "platform": item.platform,
        "url": item.url,
        "handle": item.handle,
        "score": item.score,
        "rationale": list(item.rationale),
        "method": item.method,
        "sourceUrl": item.source_url,
        "title": item.title,
        "snippet": item.snippet,
        "firstParty": item.first_party,
    }


def _evidence(item: ScoredCandidate, collected_at: str) -> dict[str, Any]:
    source_type = {
        "direct_url": "source_json" if item.first_party else item.platform,
        "source_field": "source_json",
        "intermediate": "directory",
        "web_search": "google",
    }.get(item.method, item.platform)
    if item.method == "direct_url" and item.platform in {"instagram", "facebook"}:
        source_type = item.platform
    excerpt = "; ".join(item.rationale)
    payload: dict[str, Any] = {
        "value": item.url,
        "sourceUrl": item.source_url or item.url,
        "sourceType": source_type,
        "collectedAt": collected_at,
        "confidence": min(1.0, max(0.0, item.score)),
    }
    if excerpt:
        payload["excerpt"] = excerpt
    return payload


def _pick_platform(
    scored: list[ScoredCandidate],
    platform: str,
    *,
    threshold: float,
    margin: float,
) -> tuple[ScoredCandidate | None, bool]:
    """Return (winner or None, ambiguous)."""
    group = [item for item in scored if item.platform == platform]
    group.sort(key=lambda item: (-item.score, item.handle))
    if not group:
        return None, False
    best = group[0]
    if best.score < threshold:
        return None, False
    if len(group) >= 2:
        second = group[1]
        if (best.score - second.score) < margin and second.score >= (threshold - margin):
            return None, True
    return best, False


def select_profiles(
    scored: list[ScoredCandidate],
    *,
    threshold: float,
    margin: float,
) -> tuple[ScoredCandidate | None, ScoredCandidate | None, bool, str]:
    """Instagram wins when both are valid. Close IG pair → no silent pick."""
    ig, ig_ambiguous = _pick_platform(scored, "instagram", threshold=threshold, margin=margin)
    fb, fb_ambiguous = _pick_platform(scored, "facebook", threshold=threshold, margin=margin)

    if ig_ambiguous:
        return None, None, True, "ambiguous_instagram"
    if ig is not None:
        facebook = None if fb_ambiguous else fb
        return ig, facebook, False, "selected"
    if fb_ambiguous:
        return None, None, True, "ambiguous_facebook"
    if fb is not None:
        return None, fb, False, "selected_facebook_fallback"
    if scored:
        return None, None, True, "below_threshold"
    return None, None, True, "none_found"


def _fetch_intermediates(
    *,
    queue: list[_Seed],
    http_client: HttpClient | None,
    bucket: dict[tuple[str, str], _RawCandidate],
    attempts: list[dict[str, Any]],
    warnings: list[dict[str, Any]],
    now: Callable[[], str],
    max_fetches: int,
) -> None:
    seen: set[str] = set()
    fetches = 0
    while queue and fetches < max_fetches:
        seed = queue.pop(0)
        key = seed.url.strip().rstrip("/")
        if key in seen:
            continue
        seen.add(key)
        classified = classify_url(seed.url)
        if classified.kind != "intermediate":
            continue
        if http_client is None:
            attempts.append(
                _attempt(
                    now=now(),
                    method="intermediate",
                    result="skipped_no_http_client",
                    url=seed.url,
                    evidence={"origin": seed.origin},
                )
            )
            continue
        if not is_public_http_url(seed.url):
            attempts.append(
                _attempt(
                    now=now(),
                    method="intermediate",
                    result="skipped_non_public_url",
                    url=seed.url,
                )
            )
            continue
        fetches += 1
        try:
            response = http_client.get(seed.url)
        except Exception as exc:
            warnings.append(
                _warning(
                    HTTP_TIMEOUT if "time" in str(exc).lower() else PLATFORM_BLOCKED,
                    f"Intermediate fetch failed for {seed.url}",
                    now(),
                    retryable=True,
                )
            )
            attempts.append(
                _attempt(
                    now=now(),
                    method="intermediate",
                    result="error",
                    url=seed.url,
                    evidence={"error": type(exc).__name__},
                )
            )
            continue
        if response.status == 0:
            warnings.append(
                _warning(
                    HTTP_TIMEOUT,
                    f"Intermediate fetch timed out or failed for {seed.url}",
                    now(),
                    retryable=True,
                )
            )
            attempts.append(
                _attempt(
                    now=now(),
                    method="intermediate",
                    result="timeout",
                    url=seed.url,
                )
            )
            continue
        if _is_blocked(response):
            warnings.append(
                _warning(
                    PLATFORM_BLOCKED,
                    f"Intermediate page blocked ({response.status}) at {seed.url}",
                    now(),
                    retryable=False,
                )
            )
            attempts.append(
                _attempt(
                    now=now(),
                    method="intermediate",
                    result=PLATFORM_BLOCKED,
                    url=seed.url,
                    evidence={
                        "status": response.status,
                        "finalUrl": response.final_url,
                    },
                )
            )
            continue
        if response.status == 429:
            warnings.append(
                _warning(
                    RATE_LIMITED,
                    f"Intermediate page rate-limited at {seed.url}",
                    now(),
                    retryable=True,
                )
            )
            attempts.append(
                _attempt(
                    now=now(),
                    method="intermediate",
                    result=RATE_LIMITED,
                    url=seed.url,
                    evidence={"status": 429},
                )
            )
            continue
        if response.status >= 400:
            attempts.append(
                _attempt(
                    now=now(),
                    method="intermediate",
                    result=f"http_{response.status}",
                    url=seed.url,
                    evidence={"status": response.status},
                )
            )
            continue

        found_social: list[str] = []
        landing = classify_url(response.final_url or seed.url)
        if landing.kind in {"instagram", "facebook"}:
            _add_raw(
                bucket,
                landing,
                method="intermediate",
                source_url=seed.url,
                first_party=seed.first_party,
            )
            if landing.canonical:
                found_social.append(landing.canonical)
        for extracted in extract_urls_from_html(
            response.text, base_url=response.final_url or seed.url
        ):
            item = classify_url(extracted)
            if item.kind in {"instagram", "facebook"}:
                added = _add_raw(
                    bucket,
                    item,
                    method="intermediate",
                    source_url=seed.url,
                    first_party=seed.first_party,
                )
                if added:
                    found_social.append(added.url)
            elif item.kind == "intermediate" and item.canonical:
                queue.append(
                    _Seed(
                        url=item.canonical,
                        origin=seed.url,
                        first_party=seed.first_party,
                    )
                )
        attempts.append(
            _attempt(
                now=now(),
                method="intermediate",
                result="extracted" if found_social else "no_social_links",
                url=seed.url,
                evidence={
                    "status": response.status,
                    "finalUrl": response.final_url,
                    "social": found_social,
                    "origin": seed.origin,
                },
            )
        )


def discover_profiles(
    studio: dict[str, Any],
    *,
    http_client: HttpClient | None = None,
    search_provider: SearchProvider | None = None,
    config: Config | None = None,
    now: Callable[[], str] | None = None,
) -> DiscoveryOutcome:
    """Run the discovery chain. Does not persist or change pipeline state.

    Search runs only when no Instagram/Facebook candidate exists after
    classifying source URLs and fetching public aggregators. 401/403/login
    walls are recorded as PLATFORM_BLOCKED; they are never retried with evasion.
    """
    clock = now or utc_now_iso
    threshold = (
        config.discovery_confidence_threshold
        if config is not None
        else DEFAULT_DISCOVERY_CONFIDENCE_THRESHOLD
    )
    margin = (
        config.discovery_ambiguity_margin
        if config is not None
        else DEFAULT_DISCOVERY_AMBIGUITY_MARGIN
    )
    attempts: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    bucket: dict[tuple[str, str], _RawCandidate] = {}
    intermediate_queue: list[_Seed] = []

    for seed in collect_seed_urls(studio):
        classified = classify_url(seed.url)
        method = "source_field" if seed.origin.startswith("originalRecord") else "direct_url"
        if classified.kind in {"instagram", "facebook"}:
            _add_raw(
                bucket,
                classified,
                method="direct_url",
                source_url=seed.url,
                first_party=seed.first_party,
            )
            attempts.append(
                _attempt(
                    now=clock(),
                    method=method,
                    result="matched",
                    url=classified.canonical or seed.url,
                    evidence={
                        "kind": classified.kind,
                        "handle": classified.handle,
                        "origin": seed.origin,
                    },
                )
            )
        elif classified.kind == "intermediate":
            intermediate_queue.append(seed)
            attempts.append(
                _attempt(
                    now=clock(),
                    method=method,
                    result="intermediate",
                    url=seed.url,
                    evidence={"host": classified.host, "origin": seed.origin},
                )
            )
        elif classified.kind == "official_site":
            attempts.append(
                _attempt(
                    now=clock(),
                    method=method,
                    result="official_site",
                    url=seed.url,
                    evidence={"host": classified.host, "kind": "official_site"},
                )
            )
        else:
            attempts.append(
                _attempt(
                    now=clock(),
                    method=method,
                    result="ignored",
                    evidence={"origin": seed.origin, "url": seed.url},
                )
            )

    _fetch_intermediates(
        queue=intermediate_queue,
        http_client=http_client,
        bucket=bucket,
        attempts=attempts,
        warnings=warnings,
        now=clock,
        max_fetches=MAX_INTERMEDIATE_FETCHES,
    )

    context = _score_context(studio)
    pre_scored = _score_raw_candidates(bucket, context)
    _, _, _, pre_reason = select_profiles(
        pre_scored, threshold=threshold, margin=margin
    )
    # Plan §3/§8: search only when no valid profile exists yet. A below-threshold
    # candidate is not valid; an auto-selected or ambiguous high-confidence pair is.
    if pre_reason in _SKIP_SEARCH_REASONS:
        attempts.append(
            _attempt(
                now=clock(),
                method="web_search",
                result="skipped_already_matched",
            )
        )
    else:
        provider = search_provider if search_provider is not None else NullSearchProvider()
        search_intermediates: list[_Seed] = []
        for query in build_search_queries(studio):
            try:
                hits: list[SearchHit] = provider.search(query)
            except Exception as exc:
                attempts.append(
                    _attempt(
                        now=clock(),
                        method="web_search",
                        result="error",
                        query=query,
                        evidence={"error": type(exc).__name__},
                    )
                )
                continue
            found: list[str] = []
            for hit in hits:
                classified = classify_url(hit.get("url") or "")
                if classified.kind in {"instagram", "facebook"}:
                    added = _add_raw(
                        bucket,
                        classified,
                        method="web_search",
                        source_url=classified.canonical or hit["url"],
                        first_party=False,
                        title=hit.get("title") or "",
                        snippet=hit.get("snippet") or "",
                    )
                    if added:
                        found.append(added.url)
                elif classified.kind == "intermediate":
                    search_intermediates.append(
                        _Seed(
                            url=classified.canonical or hit["url"],
                            origin="web_search",
                            first_party=False,
                        )
                    )
            attempts.append(
                _attempt(
                    now=clock(),
                    method="web_search",
                    result="matched" if found else "no_profile",
                    query=query,
                    evidence={"urls": found, "hitCount": len(hits)},
                )
            )
        if search_intermediates:
            _fetch_intermediates(
                queue=search_intermediates,
                http_client=http_client,
                bucket=bucket,
                attempts=attempts,
                warnings=warnings,
                now=clock,
                max_fetches=MAX_INTERMEDIATE_FETCHES,
            )

    scored = _score_raw_candidates(bucket, context)

    instagram, facebook, requires_review, reason = select_profiles(
        scored, threshold=threshold, margin=margin
    )
    collected_at = clock()
    selected: dict[str, Any] = {}
    if instagram is not None:
        selected["instagram"] = _evidence(instagram, collected_at)
    if facebook is not None:
        selected["facebook"] = _evidence(facebook, collected_at)

    if reason == "none_found":
        warnings.append(
            _warning(SOCIAL_NOT_FOUND, "No Instagram or Facebook profile was found", collected_at)
        )
    elif reason in {"ambiguous_instagram", "ambiguous_facebook", "below_threshold"}:
        warnings.append(
            _warning(
                SOCIAL_AMBIGUOUS,
                "Social profile selection requires human review",
                collected_at,
            )
        )

    candidate_payloads = [_candidate_dict(item) for item in scored]
    attempts.append(
        _attempt(
            now=collected_at,
            method="score",
            result=reason,
            evidence={
                "threshold": threshold,
                "ambiguityMargin": margin,
                "requiresHumanReview": requires_review,
                "candidates": candidate_payloads,
            },
        )
    )

    discovery = {
        "attempts": attempts,
        "selectedProfiles": selected,
        "requiresHumanReview": requires_review,
    }
    return DiscoveryOutcome(
        discovery=discovery,
        candidates=candidate_payloads,
        warnings=warnings,
    )
