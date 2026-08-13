"""Normalize social URLs/handles and strip tracking parameters."""

from __future__ import annotations

import re
import unicodedata
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

TRACKING_PARAM_EXACT = frozenset(
    {
        "fbclid",
        "gclid",
        "gbraid",
        "wbraid",
        "mc_cid",
        "mc_eid",
        "igsh",
        "igshid",
        "ig_rid",
        "ig_mid",
        "mibextid",
        "feature",
        "ref",
        "ref_src",
        "refsrc",
        "refid",
        "paipv",
        "eav",
        "_r",
        "_t",
        "rdid",
        "share_id",
        "si",
    }
)

_IG_RESERVED = frozenset(
    {
        "p",
        "reel",
        "reels",
        "stories",
        "tv",
        "explore",
        "accounts",
        "about",
        "legal",
        "developer",
        "developers",
        "emails",
        "fusion",
        "idsync",
        "lite",
        "api",
        "graphql",
        "direct",
        "privacy",
        "safety",
        "session",
        "share",
        "nametag",
        "static",
        "directory",
        "web",
        "challenge",
        "popular",
        "support",
        "help",
        "terms",
        "blog",
        "press",
        "locations",
        "location",
        "guide",
        "about-us",
        "emailsignup",
    }
)

_FB_RESERVED = frozenset(
    {
        "login",
        "login.php",
        "recover",
        "share",
        "sharer",
        "sharer.php",
        "dialog",
        "groups",
        "events",
        "watch",
        "marketplace",
        "gaming",
        "reels",
        "stories",
        "photo",
        "photo.php",
        "permalink.php",
        "ads",
        "business",
        "policies",
        "privacy",
        "help",
        "settings",
        "checkpoint",
        "confirmemail",
        "pages",
        "people",
        "pg",
        "l.php",
        "l",
        "hashtag",
        "public",
        "tr",
        "r.php",
        "home.php",
        "index.php",
        "cookie",
        "policies.php",
        "share.php",
    }
)

_HANDLE_RE = re.compile(r"^[A-Za-z0-9._]{1,64}$")
_FB_ID_RE = re.compile(r"^\d{5,}$")


def slugify(value: str) -> str:
    text = unicodedata.normalize("NFKD", value.strip().lower())
    ascii_text = "".join(ch for ch in text if not unicodedata.combining(ch))
    ascii_text = ascii_text.encode("ascii", "ignore").decode("ascii")
    ascii_text = re.sub(r"[^a-z0-9]+", "-", ascii_text)
    return ascii_text.strip("-")


def strip_tracking_params(url: str) -> str:
    parsed = urlparse(url.strip())
    if parsed.scheme not in {"http", "https"}:
        return url.strip()
    kept: list[tuple[str, str]] = []
    for key, value in parse_qsl(parsed.query, keep_blank_values=True):
        lowered = key.lower()
        if lowered.startswith("utm_"):
            continue
        if lowered in TRACKING_PARAM_EXACT:
            continue
        kept.append((key, value))
    query = urlencode(kept, doseq=True)
    return urlunparse(
        (parsed.scheme, parsed.netloc, parsed.path, parsed.params, query, "")
    )


def _path_segments(url: str) -> list[str]:
    parsed = urlparse(url)
    return [part for part in parsed.path.split("/") if part]


def instagram_handle(url: str) -> str | None:
    parsed = urlparse(url.strip())
    host = (parsed.hostname or "").lower()
    if "instagram.com" not in host:
        return None
    segments = _path_segments(url)
    if not segments:
        return None
    first = segments[0]
    if first.lower() in _IG_RESERVED:
        return None
    if first.startswith("@"):
        first = first[1:]
    if not _HANDLE_RE.fullmatch(first):
        return None
    if first.lower() in _IG_RESERVED:
        return None
    return first.lower()


def facebook_handle(url: str) -> str | None:
    parsed = urlparse(url.strip())
    host = (parsed.hostname or "").lower()
    if not any(token in host for token in ("facebook.com", "fb.com", "fb.me")):
        return None
    query = dict(parse_qsl(parsed.query, keep_blank_values=True))
    profile_id = query.get("id") or query.get("sk")
    if parsed.path.rstrip("/").lower().endswith("profile.php") and profile_id:
        if _FB_ID_RE.fullmatch(profile_id):
            return f"id:{profile_id}"
        return None
    segments = _path_segments(url)
    if not segments:
        return None
    first = segments[0]
    lowered = first.lower()
    if lowered in _FB_RESERVED:
        if lowered in {"pages", "people", "pg"} and len(segments) >= 2:
            candidate = segments[-1]
            if _FB_ID_RE.fullmatch(candidate):
                return f"id:{candidate}"
            if _HANDLE_RE.fullmatch(candidate) and candidate.lower() not in _FB_RESERVED:
                return candidate.lower()
        return None
    if first.startswith("@"):
        first = first[1:]
    if _FB_ID_RE.fullmatch(first):
        return f"id:{first}"
    if not _HANDLE_RE.fullmatch(first):
        return None
    return first.lower()


def canonical_instagram_url(url: str) -> str | None:
    handle = instagram_handle(url)
    if not handle:
        return None
    return f"https://www.instagram.com/{handle}/"


def canonical_facebook_url(url: str) -> str | None:
    handle = facebook_handle(url)
    if not handle:
        return None
    if handle.startswith("id:"):
        return f"https://www.facebook.com/profile.php?id={handle[3:]}"
    return f"https://www.facebook.com/{handle}/"


def normalize_social_url(url: str) -> str | None:
    """Canonical Instagram/Facebook profile URL, or None if not a profile."""
    return canonical_instagram_url(url) or canonical_facebook_url(url)


def digits_only(value: str) -> str:
    return re.sub(r"\D", "", value)
