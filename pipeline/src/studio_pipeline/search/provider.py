"""Web search adapter. No unofficial scrapers. Tests never hit the network."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Protocol, TypedDict

from studio_pipeline.config import Config, load_config


class SearchHit(TypedDict):
    url: str
    title: str
    snippet: str


class SearchProvider(Protocol):
    def search(self, query: str) -> list[SearchHit]: ...


def _norm_query(query: str) -> str:
    return " ".join(query.lower().split())


def _as_hit(item: object) -> SearchHit | None:
    if not isinstance(item, dict):
        return None
    url = str(item.get("url") or "").strip()
    if not url:
        return None
    return {
        "url": url,
        "title": str(item.get("title") or ""),
        "snippet": str(item.get("snippet") or ""),
    }


class NullSearchProvider:
    """Used when SEARCH_API_KEY is empty. Always returns no hits."""

    def search(self, query: str) -> list[SearchHit]:
        _ = query
        return []


class FakeSearchProvider:
    """Fixture-backed search. Never opens a network connection."""

    def __init__(
        self,
        hits_by_query: Mapping[str, Sequence[Mapping[str, str]]] | None = None,
        *,
        default_hits: Sequence[Mapping[str, str]] | None = None,
    ) -> None:
        self._hits_by_query: dict[str, list[SearchHit]] = {}
        for key, rows in (hits_by_query or {}).items():
            parsed = [hit for hit in (_as_hit(row) for row in rows) if hit is not None]
            self._hits_by_query[_norm_query(key)] = parsed
        self._default = [
            hit for hit in (_as_hit(row) for row in (default_hits or [])) if hit is not None
        ]
        self.queries: list[str] = []

    @classmethod
    def from_fixture(cls, path: Path) -> FakeSearchProvider:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
        if isinstance(payload, list):
            return cls(default_hits=payload)
        if not isinstance(payload, dict):
            return cls()
        default_hits = payload.get("default") or payload.get("hits") or []
        queries = payload.get("queries") or {}
        if not isinstance(queries, dict):
            queries = {}
        if not isinstance(default_hits, list):
            default_hits = []
        return cls(hits_by_query=queries, default_hits=default_hits)

    def search(self, query: str) -> list[SearchHit]:
        self.queries.append(query)
        key = _norm_query(query)
        if key in self._hits_by_query:
            return list(self._hits_by_query[key])
        matched: list[SearchHit] = []
        seen: set[str] = set()
        for stored, hits in self._hits_by_query.items():
            if stored and stored in key:
                for hit in hits:
                    url = hit["url"]
                    if url not in seen:
                        seen.add(url)
                        matched.append(hit)
        if matched:
            return matched
        return list(self._default)


def create_search_provider(config: Config | None = None) -> SearchProvider:
    """Return a search adapter. Empty SEARCH_API_KEY → NullSearchProvider.

    Licensed HTTP APIs are not wired in M2. Unknown provider names also
    yield NullSearchProvider. Never scrapes Google.
    """
    settings = config if config is not None else load_config()
    if not (settings.search_api_key or "").strip():
        return NullSearchProvider()
    name = (settings.search_provider or "").strip().lower()
    if name in {"fake", "fixture"}:
        return FakeSearchProvider()
    return NullSearchProvider()
