"""Public HTTP GET for discovery. No cookies, no stealth, no login."""

from __future__ import annotations

import ipaddress
import socket
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Protocol
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import HTTPRedirectHandler, Request, build_opener

from studio_pipeline.config import (
    DEFAULT_DISCOVERY_HTTP_TIMEOUT_SECONDS,
    DEFAULT_DISCOVERY_MAX_REDIRECTS,
)

DEFAULT_USER_AGENT = "studio-pipeline/0.1 (+public-discovery)"
MAX_BODY_BYTES = 1_000_000

_BLOCKED_HOSTS = frozenset({"localhost", "127.0.0.1", "0.0.0.0", "::1", "[::1]"})


class HttpClient(Protocol):
    def get(self, url: str) -> HttpResponse: ...


@dataclass(frozen=True)
class HttpResponse:
    """`get(url)` result. Unpackable as status, headers, text, final_url."""

    status: int
    headers: Mapping[str, str]
    text: str
    final_url: str

    def __iter__(self):
        yield self.status
        yield self.headers
        yield self.text
        yield self.final_url


def is_public_http_url(url: str) -> bool:
    """True for http(s) URLs that are not loopback/private IP literals."""
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        return False
    host = (parsed.hostname or "").strip().lower()
    if not host or host in _BLOCKED_HOSTS:
        return False
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return True
    return not (ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved)


def _decode_body(raw: bytes, content_type: str | None) -> str:
    charset = "utf-8"
    if content_type:
        for part in content_type.split(";"):
            part = part.strip()
            if part.lower().startswith("charset="):
                charset = part.split("=", 1)[1].strip().strip('"') or charset
                break
    try:
        return raw.decode(charset, errors="replace")
    except LookupError:
        return raw.decode("utf-8", errors="replace")


def _headers_map(headers: Mapping[str, str] | None) -> dict[str, str]:
    if headers is None:
        return {}
    return {str(key).lower(): str(value) for key, value in headers.items()}


class _LimitedRedirectHandler(HTTPRedirectHandler):
    def __init__(self, max_redirects: int) -> None:
        super().__init__()
        self.max_redirections = max_redirects


class StdlibHttpClient:
    """urllib GET with timeout, redirect cap, and an honest User-Agent.

    Tests must inject a fake; this adapter is for production callers only.
    """

    def __init__(
        self,
        *,
        timeout: float = DEFAULT_DISCOVERY_HTTP_TIMEOUT_SECONDS,
        max_redirects: int = DEFAULT_DISCOVERY_MAX_REDIRECTS,
        user_agent: str = DEFAULT_USER_AGENT,
    ) -> None:
        self.timeout = timeout
        self.max_redirects = max_redirects
        self.user_agent = user_agent

    def get(self, url: str) -> HttpResponse:
        if not is_public_http_url(url):
            return HttpResponse(status=0, headers={}, text="", final_url=url)
        request = Request(
            url,
            headers={
                "User-Agent": self.user_agent,
                "Accept": "text/html,application/xhtml+xml;q=0.9,*/*;q=0.8",
            },
            method="GET",
        )
        opener = build_opener(_LimitedRedirectHandler(self.max_redirects))
        try:
            with opener.open(request, timeout=self.timeout) as response:
                raw = response.read(MAX_BODY_BYTES)
                headers = _headers_map(response.headers)
                text = _decode_body(raw, headers.get("content-type"))
                status = int(getattr(response, "status", 200) or 200)
                final_url = response.geturl() or url
                return HttpResponse(
                    status=status,
                    headers=headers,
                    text=text,
                    final_url=final_url,
                )
        except HTTPError as exc:
            raw = b""
            try:
                raw = exc.read(MAX_BODY_BYTES)
            except Exception:
                raw = b""
            headers = _headers_map(getattr(exc, "headers", None) or {})
            text = _decode_body(raw, headers.get("content-type"))
            final_url = getattr(exc, "url", None) or url
            return HttpResponse(
                status=int(exc.code or 0),
                headers=headers,
                text=text,
                final_url=str(final_url),
            )
        except (TimeoutError, socket.timeout, URLError, OSError):
            return HttpResponse(status=0, headers={}, text="", final_url=url)


class FakeHttpClient:
    """In-memory HTTP client. Tests inject this; it never opens a socket."""

    def __init__(
        self,
        responses: Mapping[str, HttpResponse] | None = None,
        *,
        default: HttpResponse | None = None,
    ) -> None:
        self._responses = {self._key(url): resp for url, resp in (responses or {}).items()}
        self.default = default or HttpResponse(status=404, headers={}, text="", final_url="")
        self.requested: list[str] = []

    @staticmethod
    def _key(url: str) -> str:
        return url.strip().rstrip("/")

    def add(self, url: str, response: HttpResponse) -> None:
        self._responses[self._key(url)] = response

    def get(self, url: str) -> HttpResponse:
        self.requested.append(url)
        key = self._key(url)
        response = self._responses.get(key)
        if response is None:
            response = self._responses.get(url)
        if response is None:
            return HttpResponse(
                status=self.default.status,
                headers=dict(self.default.headers),
                text=self.default.text,
                final_url=self.default.final_url or url,
            )
        final_url = response.final_url or url
        return HttpResponse(
            status=response.status,
            headers=dict(response.headers),
            text=response.text,
            final_url=final_url,
        )
