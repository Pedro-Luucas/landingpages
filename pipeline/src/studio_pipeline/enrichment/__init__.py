"""Factual enrichment from public sources (plan §8 etapa D / §17 M3)."""

from studio_pipeline.enrichment.facts import (
    CONFIDENCE,
    FACT_KEYS,
    append_evidence,
    empty_facts,
    enrich_facts,
    make_evidence,
)
from studio_pipeline.enrichment.places import (
    FakePlacesProvider,
    NullPlacesProvider,
    PlacesProvider,
    create_places_provider,
)

__all__ = [
    "CONFIDENCE",
    "FACT_KEYS",
    "FakePlacesProvider",
    "NullPlacesProvider",
    "PlacesProvider",
    "append_evidence",
    "create_places_provider",
    "empty_facts",
    "enrich_facts",
    "make_evidence",
]
