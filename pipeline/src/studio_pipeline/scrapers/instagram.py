"""Public Instagram profile scrape (no login, no Graph API, no stealth)."""

from __future__ import annotations

from collections.abc import Callable

from studio_pipeline.scrapers.http import DEFAULT_TIMEOUT_SECONDS, HttpClient
from studio_pipeline.scrapers.models import SocialScrape
from studio_pipeline.scrapers.public import DEFAULT_MAX_POSTS, scrape_public_profile


def scrape_instagram(
    profile_url: str,
    http: HttpClient,
    *,
    max_posts: int = DEFAULT_MAX_POSTS,
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
    sleep: Callable[[float], None] | None = None,
    respect_robots: bool = True,
    now: Callable[[], str] | None = None,
) -> SocialScrape:
    """Collect bio, public highlights, profile image URL, and up to ``max_posts`` posts.

    Live Instagram frequently returns 401/403 or a login wall. That is
    ``PLATFORM_BLOCKED`` — do not retry with a different User-Agent.
    """

    return scrape_public_profile(
        "instagram",
        profile_url,
        http,
        max_posts=max_posts,
        timeout=timeout,
        sleep=sleep,
        respect_robots=respect_robots,
        now=now,
    )
