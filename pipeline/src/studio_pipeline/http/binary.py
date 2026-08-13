"""Binary HTTP GET for media downloads. No cookies, no stealth, no login.

``StdlibHttpClient.get`` caps bodies at 1MB, which is too small for photos.
This adapter returns raw bytes with an 8 MiB cap. Tests inject ``FakeBinaryHttp``.
"""

from __future__ import annotations

import socket
from collections.abc import Mapping
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, Request, build_opener

from studio_pipeline.config import (
    DEFAULT_DISCOVERY_HTTP_TIMEOUT_SECONDS,
    DEFAULT_DISCOVERY_MAX_REDIRECTS,
)
from studio_pipeline.http.client import DEFAULT_USER_AGENT, is_public_http_url

MAX_BINARY_BODY_BYTES = 8 * 1024 * 1024

BinaryResult = tuple[int, Mapping[str, str], bytes, str]


def _headers_map(headers: Mapping[str, str] | None) -> dict[str, str]:
    if headers is None:
        return {}
    return {str(key).lower(): str(value) for key, value in headers.items()}


def _guess_content_type(body: bytes) -> str:
    if body.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if body.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if body.startswith(b"GIF87a") or body.startswith(b"GIF89a"):
        return "image/gif"
    if len(body) >= 12 and body[:4] == b"RIFF" and body[8:12] == b"WEBP":
        return "image/webp"
    head = body.lstrip()[:64].lower()
    if head.startswith(b"<svg") or (head.startswith(b"<?xml") and b"<svg" in body[:512].lower()):
        return "image/svg+xml"
    if head.startswith(b"<!doctype html") or head.startswith(b"<html"):
        return "text/html"
    return "application/octet-stream"


def _read_limited(stream: Any, max_bytes: int) -> bytes:
    """Read at most ``max_bytes + 1`` so callers can detect overflow."""
    try:
        return stream.read(max_bytes + 1)
    except Exception:
        return b""


class _LimitedRedirectHandler(HTTPRedirectHandler):
    def __init__(self, max_redirects: int) -> None:
        super().__init__()
        self.max_redirections = max_redirects

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if not is_public_http_url(str(newurl or "")):
            raise URLError("redirect to non-public URL")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


class StdlibBinaryHttp:
    """urllib GET of raw bytes. Honest User-Agent, timeout, 8 MiB cap.

    Tests must inject ``FakeBinaryHttp``; this adapter is for production callers.
    """

    def __init__(
        self,
        *,
        timeout: float = DEFAULT_DISCOVERY_HTTP_TIMEOUT_SECONDS,
        max_redirects: int = DEFAULT_DISCOVERY_MAX_REDIRECTS,
        user_agent: str = DEFAULT_USER_AGENT,
        max_body_bytes: int = MAX_BINARY_BODY_BYTES,
    ) -> None:
        self.timeout = timeout
        self.max_redirects = max_redirects
        self.user_agent = user_agent
        self.max_body_bytes = max_body_bytes

    def get_bytes(self, url: str) -> BinaryResult:
        if not is_public_http_url(url):
            return 0, {}, b"", url
        request = Request(
            url,
            headers={
                "User-Agent": self.user_agent,
                "Accept": "image/*,*/*;q=0.8",
            },
            method="GET",
        )
        opener = build_opener(_LimitedRedirectHandler(self.max_redirects))
        try:
            with opener.open(request, timeout=self.timeout) as response:
                raw = _read_limited(response, self.max_body_bytes)
                headers = _headers_map(response.headers)
                status = int(getattr(response, "status", 200) or 200)
                final_url = response.geturl() or url
                return status, headers, raw, final_url
        except HTTPError as exc:
            raw = b""
            try:
                raw = _read_limited(exc, self.max_body_bytes)
            except Exception:
                raw = b""
            headers = _headers_map(getattr(exc, "headers", None) or {})
            final_url = getattr(exc, "url", None) or url
            return int(exc.code or 0), headers, raw, str(final_url)
        except (TimeoutError, socket.timeout, URLError, OSError):
            return 0, {}, b"", url


class FakeBinaryHttp:
    """In-memory binary client. Tests inject this; it never opens a socket."""

    def __init__(
        self,
        routes: Mapping[str, bytes | BinaryResult] | None = None,
        *,
        default_body: bytes | None = None,
    ) -> None:
        self._routes = {self._key(url): item for url, item in (routes or {}).items()}
        self.default_body = default_body
        self.calls: list[str] = []

    @staticmethod
    def _key(url: str) -> str:
        return url.strip().rstrip("/")

    def add(self, url: str, body: bytes | BinaryResult) -> None:
        self._routes[self._key(url)] = body

    def get_bytes(self, url: str) -> BinaryResult:
        self.calls.append(url)
        item = self._routes.get(self._key(url))
        if item is None:
            item = self._routes.get(url)
        if item is None:
            if self.default_body is not None:
                body = self.default_body
                return 200, {"content-type": _guess_content_type(body)}, body, url
            raise AssertionError(f"unexpected URL (no network): {url}")
        if isinstance(item, tuple):
            status, headers, body, final_url = item
            return int(status), dict(headers), body, str(final_url or url)
        return 200, {"content-type": _guess_content_type(item)}, item, url
