"""Search adapter Protocol and offline fakes (plan §8 etapa B)."""

from studio_pipeline.search.provider import (
    FakeSearchProvider,
    NullSearchProvider,
    SearchHit,
    SearchProvider,
    create_search_provider,
)

__all__ = [
    "FakeSearchProvider",
    "NullSearchProvider",
    "SearchHit",
    "SearchProvider",
    "create_search_provider",
]
