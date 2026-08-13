"""Adapt discovery HTTP clients for public scrapers.

``studio_pipeline.http.HttpResponse`` is a different class from
``studio_pipeline.scrapers.http.HttpResponse``. This wrapper converts
discovery responses to a 4-tuple so scrapers can consume them. It never
rotates User-Agent and never adds cookies.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any


def _header_dict(headers: object) -> dict[str, str]:
    if headers is None:
        return {}
    if isinstance(headers, Mapping):
        return {str(key): str(value) for key, value in headers.items()}
    if isinstance(headers, (list, tuple)) and not isinstance(headers, (str, bytes)):
        return {str(key): str(value) for key, value in headers}
    return {}


def as_scraper_tuple(
    result: object,
    url: str,
) -> tuple[int, dict[str, str], str, str]:
    """Normalize ``get()`` output to ``(status, headers, text, final_url)``."""
    if isinstance(result, tuple) and len(result) == 4:
        status, headers, text, final_url = result
        return int(status), _header_dict(headers), str(text or ""), str(final_url or url)
    status = getattr(result, "status", None)
    if status is None:
        raise TypeError(
            "HttpClient.get must return HttpResponse or (status, headers, text, final_url)"
        )
    headers = getattr(result, "headers", None)
    text = getattr(result, "text", None)
    final_url = getattr(result, "final_url", None)
    return int(status), _header_dict(headers), str(text or ""), str(final_url or url)


class ScraperHttpAdapter:
    """Present a discovery ``HttpClient`` as a scrapers-compatible GET client."""

    def __init__(self, inner: Any) -> None:
        self._inner = inner

    def get(
        self,
        url: str,
        timeout: float | None = None,
    ) -> tuple[int, Mapping[str, str], str, str]:
        _ = timeout
        return as_scraper_tuple(self._inner.get(url), url)
