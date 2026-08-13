"""Google/Places lookup. Never scrapes maps HTML. Tests inject FakePlacesProvider."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, Protocol, TypedDict


class PlacesMap(TypedDict, total=False):
    latitude: float
    longitude: float
    address: str
    placeId: str


class PlacesResult(TypedDict, total=False):
    rating: float
    count: int
    excerpts: list[str]
    map: PlacesMap
    url: str


class PlacesProvider(Protocol):
    """Licensed Places lookup. Implementations must not fetch google.com/maps HTML."""

    def lookup(self, name: str, city: str, address: str) -> PlacesResult | None: ...


def _norm(value: object) -> str:
    return " ".join(str(value or "").lower().split())


def _as_float(value: object) -> float | None:
    if value is None or value == "" or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number


def _as_count(value: object) -> int | None:
    number = _as_float(value)
    if number is None or number < 0 or number != int(number):
        return None
    return int(number)


def _as_map(raw: object) -> PlacesMap | None:
    if not isinstance(raw, dict):
        return None
    payload: PlacesMap = {}
    lat = _as_float(raw.get("latitude"))
    lng = _as_float(raw.get("longitude"))
    if lat is not None and -90 <= lat <= 90:
        payload["latitude"] = lat
    if lng is not None and -180 <= lng <= 180:
        payload["longitude"] = lng
    address = str(raw.get("address") or "").strip()
    if address:
        payload["address"] = address
    place_id = str(raw.get("placeId") or raw.get("place_id") or "").strip()
    if place_id:
        payload["placeId"] = place_id
    return payload or None


def _as_result(raw: object) -> PlacesResult | None:
    if not isinstance(raw, dict):
        return None
    payload: PlacesResult = {}
    rating = _as_float(raw.get("rating"))
    if rating is not None and 0 <= rating <= 5:
        payload["rating"] = rating
    count = _as_count(raw.get("count") if "count" in raw else raw.get("ratingCount"))
    if count is not None:
        payload["count"] = count
    excerpts_raw = raw.get("excerpts")
    if isinstance(excerpts_raw, list):
        excerpts = [str(item).strip() for item in excerpts_raw if str(item).strip()]
        if excerpts:
            payload["excerpts"] = excerpts
    mapped = _as_map(raw.get("map"))
    if mapped:
        payload["map"] = mapped
    url = str(raw.get("url") or raw.get("sourceUrl") or "").strip()
    if url:
        payload["url"] = url
    if not payload:
        return None
    return payload


class NullPlacesProvider:
    """Used when no Places API key is configured. lookup is never called by enrich_facts."""

    available = False

    def lookup(self, name: str, city: str, address: str) -> PlacesResult | None:
        _ = (name, city, address)
        return None


class FakePlacesProvider:
    """Fixture-backed Places lookup. Never opens a network connection."""

    available = True

    def __init__(
        self,
        entries: Sequence[Mapping[str, Any]] | None = None,
        *,
        default: Mapping[str, Any] | None = None,
    ) -> None:
        self._entries = [dict(row) for row in (entries or [])]
        self._default = dict(default) if default else None
        self.lookups: list[tuple[str, str, str]] = []

    @classmethod
    def from_fixture(cls, path: Path) -> FakePlacesProvider:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
        if isinstance(payload, list):
            return cls(entries=payload)
        if not isinstance(payload, dict):
            return cls()
        entries = payload.get("entries") or payload.get("lookups") or payload.get("places") or []
        default = payload.get("default")
        if not isinstance(entries, list):
            entries = []
        if default is not None and not isinstance(default, dict):
            default = None
        return cls(entries=entries, default=default)

    def lookup(self, name: str, city: str, address: str) -> PlacesResult | None:
        self.lookups.append((name, city, address))
        want_name = _norm(name)
        want_city = _norm(city)
        want_address = _norm(address)
        for row in self._entries:
            entry_name = _norm(row.get("name") or row.get("title"))
            entry_city = _norm(row.get("city") or row.get("cidade"))
            if want_name and entry_name and entry_name not in want_name and want_name not in entry_name:
                continue
            if want_city and entry_city and entry_city not in want_city and want_city not in entry_city:
                continue
            if want_name or want_city or want_address:
                return _as_result(row)
        if self._default is not None:
            return _as_result(self._default)
        return None


def create_places_provider(config: Any | None = None) -> PlacesProvider:
    """Return a Places adapter. Missing API key → NullPlacesProvider.

    Licensed HTTP APIs are not wired. Search provider/API key is not a Places
    adapter — a fake web-search config must not silently become FakePlaces.
    Unknown provider names also yield NullPlacesProvider. Never scrapes
    Google Maps HTML.
    """
    name = ""
    if config is not None:
        name = str(getattr(config, "places_provider", None) or "").strip().lower()
    if name in {"fake", "fixture"}:
        return FakePlacesProvider()
    return NullPlacesProvider()
