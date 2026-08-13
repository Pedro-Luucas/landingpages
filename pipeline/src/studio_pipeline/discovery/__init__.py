"""Social/web discovery (plan §8 etapa B / §17 M2)."""

from studio_pipeline.discovery.classify import UrlClassification, classify_url
from studio_pipeline.discovery.normalize import normalize_social_url, strip_tracking_params
from studio_pipeline.discovery.social import (
    DiscoveryOutcome,
    build_search_queries,
    discover_profiles,
    select_profiles,
)

__all__ = [
    "DiscoveryOutcome",
    "UrlClassification",
    "build_search_queries",
    "classify_url",
    "discover_profiles",
    "normalize_social_url",
    "select_profiles",
    "strip_tracking_params",
]
