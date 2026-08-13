"""In-memory scrape results. Merge emits dossier.social camelCase dicts."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

MediaType = Literal["image", "video", "carousel"]
Platform = Literal["instagram", "facebook"]


@dataclass
class Evidence:
    value: Any
    source_url: str
    source_type: str
    collected_at: str
    confidence: float
    excerpt: str | None = None

    def to_dossier(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "value": self.value,
            "sourceUrl": self.source_url,
            "sourceType": self.source_type,
            "collectedAt": self.collected_at,
            "confidence": self.confidence,
        }
        if self.excerpt:
            payload["excerpt"] = self.excerpt
        return payload


@dataclass
class PostMedia:
    url: str
    type: MediaType
    selectable_photo: bool = True
    flags: tuple[str, ...] = ()

    def to_dossier(self) -> dict[str, Any]:
        return {"url": self.url, "type": self.type}


@dataclass
class SocialPost:
    external_id: str
    url: str
    media: list[PostMedia]
    collected_at: str
    published_at: str | None = None
    caption: str | None = None

    def to_dossier(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "externalId": self.external_id,
            "url": self.url,
            "media": [item.to_dossier() for item in self.media],
            "collectedAt": self.collected_at,
        }
        if self.published_at:
            payload["publishedAt"] = self.published_at
        if self.caption:
            payload["caption"] = self.caption
        return payload


@dataclass
class ScrapeWarning:
    code: str
    message: str
    stage: str = "scraping"
    at: str | None = None
    retryable: bool = False

    def to_dossier(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "code": self.code,
            "message": self.message,
            "stage": self.stage,
            "retryable": self.retryable,
        }
        if self.at:
            payload["at"] = self.at
        return payload


@dataclass
class SocialScrape:
    """Public-profile scrape for one platform. Extra media flags stay here, not in dossier.social."""

    platform: Platform
    profile_url: str
    bio: Evidence | None = None
    profile_image: Evidence | None = None
    highlights: list[Evidence] = field(default_factory=list)
    posts: list[SocialPost] = field(default_factory=list)
    warnings: list[ScrapeWarning] = field(default_factory=list)

    def to_social_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "highlights": [item.to_dossier() for item in self.highlights],
            "posts": [item.to_dossier() for item in self.posts],
        }
        if self.bio is not None:
            payload["bio"] = self.bio.to_dossier()
        if self.profile_image is not None:
            payload["profileImage"] = self.profile_image.to_dossier()
        return payload
