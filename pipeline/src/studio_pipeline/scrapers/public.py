"""Shared public-profile scrape. Live IG/FB often block; tests cover that path."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from studio_pipeline.clock import utc_now_iso
from studio_pipeline.errors import PLATFORM_BLOCKED, PipelineError
from studio_pipeline.scrapers.http import (
    DEFAULT_TIMEOUT_SECONDS,
    HttpClient,
    fetch_public,
    header_value,
)
from studio_pipeline.scrapers.models import (
    Evidence,
    Platform,
    ScrapeWarning,
    SocialPost,
    SocialScrape,
)
from studio_pipeline.scrapers.parse import annotate_selectable_media, parse_public_document
from studio_pipeline.scrapers.robots import allowed_by_robots
from studio_pipeline.scrapers.urls import canonicalize_url, require_http_url

DEFAULT_MAX_POSTS = 30
CONFIDENCE = {
    "instagram": {"bio": 0.9, "profile_image": 0.9, "highlight": 0.8},
    "facebook": {"bio": 0.75, "profile_image": 0.75, "highlight": 0.7},
}


def scrape_public_profile(
    platform: Platform,
    profile_url: str,
    http: HttpClient,
    *,
    max_posts: int = DEFAULT_MAX_POSTS,
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
    sleep: Callable[[float], None] | None = None,
    respect_robots: bool = True,
    now: Callable[[], str] | None = None,
) -> SocialScrape:
    """Fetch and parse one public social profile.

    Does not download binary images. Profile photo is recorded as a URL only.
    ``PLATFORM_BLOCKED`` is raised on 401/403/login walls; the error message
    never includes response HTML. Live Instagram/Facebook commonly take that path.
    """

    collected_at = (now or utc_now_iso)()
    canonical = require_http_url(profile_url)
    warnings: list[ScrapeWarning] = []
    limit = max(0, max_posts)

    if respect_robots:
        allowed, robots_message = allowed_by_robots(
            http, canonical, timeout=timeout, sleep=sleep
        )
        if not allowed:
            warnings.append(
                ScrapeWarning(
                    code="ROBOTS_DISALLOWED",
                    message=robots_message or "robots.txt disallows this URL",
                    at=collected_at,
                    retryable=False,
                )
            )
            return SocialScrape(
                platform=platform,
                profile_url=canonical,
                warnings=warnings,
            )
        if robots_message:
            warnings.append(
                ScrapeWarning(
                    code="ROBOTS_UNREADABLE",
                    message=robots_message,
                    at=collected_at,
                    retryable=True,
                )
            )

    response = fetch_public(http, canonical, timeout=timeout, sleep=sleep)
    content_type = header_value(response.headers, "Content-Type")
    parsed = parse_public_document(
        response.text,
        content_type=content_type,
        base_url=response.final_url or canonical,
    )
    if parsed.login_wall:
        raise PipelineError(
            PLATFORM_BLOCKED,
            f"public page is a login wall or challenge at {platform}",
        )

    scores = CONFIDENCE[platform]
    source_url = canonicalize_url(response.final_url or canonical)
    bio = _evidence(parsed.bio, source_url, platform, collected_at, scores["bio"])
    profile_image = _evidence(
        parsed.profile_image_url,
        source_url,
        platform,
        collected_at,
        scores["profile_image"],
    )
    highlights = [
        Evidence(
            value=_highlight_value(title, text),
            source_url=source_url,
            source_type=platform,
            collected_at=collected_at,
            confidence=scores["highlight"],
        )
        for title, text in parsed.highlights
        if title
    ]
    annotate_selectable_media(parsed.posts)
    posts = _to_social_posts(parsed.posts, collected_at, limit)
    return SocialScrape(
        platform=platform,
        profile_url=source_url,
        bio=bio,
        profile_image=profile_image,
        highlights=highlights,
        posts=posts,
        warnings=warnings,
    )


def _evidence(
    value: str | None,
    source_url: str,
    platform: Platform,
    collected_at: str,
    confidence: float,
) -> Evidence | None:
    if not value:
        return None
    excerpt = value if len(value) <= 180 else value[:177] + "..."
    return Evidence(
        value=value,
        source_url=source_url,
        source_type=platform,
        collected_at=collected_at,
        confidence=confidence,
        excerpt=excerpt,
    )


def _highlight_value(title: str, text: str | None) -> dict[str, Any]:
    payload: dict[str, Any] = {"title": title}
    if text:
        payload["text"] = text
    return payload


def _to_social_posts(parsed_posts: list, collected_at: str, limit: int) -> list[SocialPost]:
    unique: list[SocialPost] = []
    seen: set[str] = set()
    ordered = _sort_posts(parsed_posts)
    for raw in ordered:
        url = canonicalize_url(raw.url) if raw.url else ""
        key = url or raw.external_id
        if not key or key in seen:
            continue
        seen.add(key)
        unique.append(
            SocialPost(
                external_id=str(raw.external_id or key),
                url=url or key,
                media=list(raw.media),
                collected_at=collected_at,
                published_at=raw.published_at,
                caption=raw.caption,
            )
        )
        if len(unique) >= limit:
            break
    return unique


def _sort_posts(posts: list) -> list:
    dated = [post for post in posts if post.published_at]
    if dated and len(dated) == len(posts):
        return sorted(posts, key=lambda post: post.published_at or "", reverse=True)
    return list(posts)
