"""Merge Instagram (primary) with Facebook gap-fill. Dedupe cross-posted content."""

from __future__ import annotations

from typing import Any

from studio_pipeline.scrapers.models import SocialPost, SocialScrape
from studio_pipeline.scrapers.public import DEFAULT_MAX_POSTS
from studio_pipeline.scrapers.urls import canonicalize_url


def merge_social(
    primary: SocialScrape | None,
    facebook: SocialScrape | None,
    *,
    max_posts: int = DEFAULT_MAX_POSTS,
) -> dict[str, Any]:
    """Return a dossier.social-shaped dict.

    Instagram (``primary``) wins when both sides have a field. Facebook fills
    missing bio, profile image, highlights, and posts. Posts are deduped by
    canonical URL or media URL.
    """

    highlights = list(primary.highlights if primary else [])
    seen_titles = {_title_key(item.value) for item in highlights}
    if facebook:
        for item in facebook.highlights:
            key = _title_key(item.value)
            if key and key not in seen_titles:
                seen_titles.add(key)
                highlights.append(item)

    posts = list(primary.posts if primary else [])
    seen = _post_keys(posts)
    if facebook:
        for post in facebook.posts:
            keys = _keys_for_post(post)
            if keys & seen:
                continue
            seen.update(keys)
            posts.append(post)

    payload: dict[str, Any] = {
        "highlights": [item.to_dossier() for item in highlights],
        "posts": [post.to_dossier() for post in posts[: max(0, max_posts)]],
    }
    bio = _first_evidence(primary, facebook, "bio")
    if bio is not None:
        payload["bio"] = bio.to_dossier()
    image = _first_evidence(primary, facebook, "profile_image")
    if image is not None:
        payload["profileImage"] = image.to_dossier()
    return payload


def _first_evidence(
    primary: SocialScrape | None,
    facebook: SocialScrape | None,
    field: str,
):
    for scrape in (primary, facebook):
        if scrape is None:
            continue
        value = getattr(scrape, field)
        if value is not None and value.value:
            return value
    return None


def _title_key(value: object) -> str:
    if isinstance(value, dict):
        return str(value.get("title") or "").casefold().strip()
    return str(value or "").casefold().strip()


def _post_keys(posts: list[SocialPost]) -> set[str]:
    keys: set[str] = set()
    for post in posts:
        keys.update(_keys_for_post(post))
    return keys


def _keys_for_post(post: SocialPost) -> set[str]:
    keys: set[str] = set()
    if post.url:
        keys.add("url:" + canonicalize_url(post.url))
    for item in post.media:
        if item.url:
            keys.add("media:" + canonicalize_url(item.url))
    return keys
