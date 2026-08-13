"""Classify URLs as Instagram, Facebook, intermediate aggregator, or site."""

from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import parse_qs, urlparse, urlunparse

from studio_pipeline.discovery.normalize import (
    canonical_facebook_url,
    canonical_instagram_url,
    facebook_handle,
    instagram_handle,
    strip_tracking_params,
)

INTERMEDIATE_HOSTS = frozenset(
    {
        "linktr.ee",
        "linktree.com",
        "beacons.ai",
        "bio.site",
        "lnk.bio",
        "carrd.co",
        "hoo.be",
        "tap.bio",
        "solo.to",
        "campsite.bio",
        "allmylinks.com",
        "direct.me",
        "hypel.ink",
        "snipfeed.co",
        "msha.ke",
        "stan.store",
        "withkoji.com",
        "bento.me",
        "biolinky.co",
        "issuu.com",
    }
)

INTERMEDIATE_HOST_SUFFIXES = (
    ".carrd.co",
    ".bio.site",
    ".linktr.ee",
    ".beacons.ai",
    ".lnk.bio",
    ".hoo.be",
)


@dataclass(frozen=True)
class UrlClassification:
    kind: str
    url: str
    canonical: str | None = None
    handle: str | None = None
    host: str = ""
    platform: str | None = None


def hostname_of(url: str) -> str:
    parsed = urlparse(url.strip())
    host = (parsed.hostname or "").lower().rstrip(".")
    if host.startswith("www."):
        host = host[4:]
    return host


def is_instagram_host(host: str) -> bool:
    return host == "instagram.com" or host.endswith(".instagram.com")


def is_facebook_host(host: str) -> bool:
    return host in {"facebook.com", "fb.com", "fb.me"} or host.endswith(
        ".facebook.com"
    ) or host.endswith(".fb.com")


def is_intermediate_host(host: str) -> bool:
    if host in INTERMEDIATE_HOSTS:
        return True
    return any(host.endswith(suffix) for suffix in INTERMEDIATE_HOST_SUFFIXES)


def is_google_host(host: str) -> bool:
    """True for Google properties (search, maps, goo.gl), including ccTLDs.

    These must not be treated as a studio's official site or fetched as HTML.
    """
    if not host:
        return False
    if host in {"goo.gl", "g.co"} or host.endswith(".goo.gl"):
        return True
    labels = host.split(".")
    return "google" in labels


def classify_url(url: str) -> UrlClassification:
    """Classify a URL for the discovery chain. Does not fetch."""
    raw = (url or "").strip()
    if not raw:
        return UrlClassification(kind="other", url=raw)
    cleaned = strip_tracking_params(raw) or raw
    parsed = urlparse(cleaned)
    if parsed.scheme not in {"http", "https"}:
        return UrlClassification(kind="other", url=raw, host=hostname_of(raw))
    host = hostname_of(cleaned)
    if is_instagram_host(host):
        handle = instagram_handle(cleaned)
        canonical = canonical_instagram_url(cleaned) if handle else None
        if handle and canonical:
            return UrlClassification(
                kind="instagram",
                url=raw,
                canonical=canonical,
                handle=handle,
                host=host,
                platform="instagram",
            )
        return UrlClassification(kind="other", url=raw, host=host, platform="instagram")
    if is_facebook_host(host):
        handle = facebook_handle(cleaned)
        canonical = canonical_facebook_url(cleaned) if handle else None
        if handle and canonical:
            return UrlClassification(
                kind="facebook",
                url=raw,
                canonical=canonical,
                handle=handle,
                host=host,
                platform="facebook",
            )
        return UrlClassification(kind="other", url=raw, host=host, platform="facebook")
    if is_intermediate_host(host):
        canonical = urlunparse(
            (
                "https",
                parsed.netloc.lower(),
                parsed.path or "/",
                "",
                parsed.query,
                "",
            )
        )
        return UrlClassification(
            kind="intermediate",
            url=raw,
            canonical=canonical,
            host=host,
        )
    if is_google_host(host):
        return UrlClassification(kind="other", url=raw, host=host)
    return UrlClassification(
        kind="official_site",
        url=raw,
        canonical=cleaned.split("#", 1)[0],
        host=host,
    )


def looks_like_login_url(url: str) -> bool:
    parsed = urlparse(url)
    path = (parsed.path or "").lower()
    markers = (
        "/login",
        "/log-in",
        "/signin",
        "/sign-in",
        "/accounts/login",
        "/checkpoint",
        "/cookie/consent",
    )
    if any(marker in path for marker in markers):
        return True
    params = {key.lower() for key in parse_qs(parsed.query)}
    return "next" in params and "login" in path
