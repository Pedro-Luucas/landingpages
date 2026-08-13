"""Canonical public URLs. Tracking params are dropped; no login cookies."""

from __future__ import annotations

from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from studio_pipeline.errors import INPUT_INVALID, PipelineError

TRACKING_PARAMS = frozenset(
    {
        "utm_source",
        "utm_medium",
        "utm_campaign",
        "utm_content",
        "utm_term",
        "fbclid",
        "igshid",
        "igsh",
        "mibextid",
        "ref",
        "ref_src",
        "refid",
    }
)


def require_http_url(url: str, *, what: str = "profile URL") -> str:
    text = (url or "").strip()
    if not text:
        raise PipelineError(INPUT_INVALID, f"{what} is required")
    parsed = urlparse(text)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise PipelineError(INPUT_INVALID, f"{what} must be an http(s) URL")
    return canonicalize_url(text)


def canonicalize_url(url: str) -> str:
    parsed = urlparse(url.strip())
    query = [
        (key, value)
        for key, value in parse_qsl(parsed.query, keep_blank_values=True)
        if key.lower() not in TRACKING_PARAMS
    ]
    path = parsed.path or "/"
    if path != "/" and path.endswith("/"):
        path = path.rstrip("/")
    return urlunparse(
        (
            parsed.scheme.lower(),
            parsed.netloc.lower(),
            path,
            "",
            urlencode(query),
            "",
        )
    )


def origin_of(url: str) -> str:
    parsed = urlparse(url)
    return f"{parsed.scheme}://{parsed.netloc}"


def robots_url_for(page_url: str) -> str:
    return f"{origin_of(page_url)}/robots.txt"


def is_reel_url(url: str) -> bool:
    path = urlparse(url).path.lower()
    return "/reel/" in path or "/reels/" in path
