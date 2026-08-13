"""Optional robots.txt check. Uses already-fetched text; never opens sockets."""

from __future__ import annotations

from urllib.robotparser import RobotFileParser

from studio_pipeline.errors import HTTP_NOT_FOUND, HTTP_TIMEOUT, PLATFORM_BLOCKED, PipelineError
from studio_pipeline.http.client import DEFAULT_USER_AGENT
from studio_pipeline.scrapers.http import HttpClient, fetch_public
from studio_pipeline.scrapers.urls import robots_url_for

# Same product token as HTTP User-Agent so robots.txt rules match the crawler.
ROBOTS_USER_AGENT = DEFAULT_USER_AGENT


def allowed_by_robots(
    http: HttpClient,
    page_url: str,
    *,
    timeout: float,
    sleep,
) -> tuple[bool, str | None]:
    """Return (allowed, warning_message). Fail-open if robots.txt is missing or unreadable."""

    robots_url = robots_url_for(page_url)
    try:
        response = fetch_public(http, robots_url, timeout=timeout, sleep=sleep, max_attempts=1)
    except PipelineError as exc:
        # Optional check: missing or blocked robots.txt must not fail the scrape.
        if exc.code in {HTTP_NOT_FOUND, HTTP_TIMEOUT, PLATFORM_BLOCKED}:
            return True, None
        return True, f"robots.txt could not be read ({exc.code}); continuing"
    if response.status >= 400:
        return True, None
    parser = RobotFileParser()
    parser.parse(response.text.splitlines())
    try:
        allowed = parser.can_fetch(ROBOTS_USER_AGENT, page_url)
    except Exception:
        return True, "robots.txt could not be parsed; continuing"
    if allowed:
        return True, None
    return False, f"robots.txt disallows fetching {page_url}"
