"""Injected HTTP client for public-page scrapers.

Live Instagram/Facebook responses are often 401/403, a login wall, or a
challenge. Callers must treat that as ``PLATFORM_BLOCKED`` and must not retry
with a browser-like User-Agent or cookie jar to bypass the block.

The client is responsible for TLS, redirects, and timeouts. This module only
interprets the result of ``get(url)``.
"""

from __future__ import annotations

import inspect
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Protocol
from urllib.parse import urlparse

from studio_pipeline.errors import (
    HTTP_NOT_FOUND,
    HTTP_TIMEOUT,
    PLATFORM_BLOCKED,
    RATE_LIMITED,
    PipelineError,
)

DEFAULT_TIMEOUT_SECONDS = 15.0
MAX_TRANSIENT_ATTEMPTS = 3
MAX_BACKOFF_SECONDS = 30.0

_LOGIN_PATH_MARKERS = (
    "/accounts/login",
    "/login.php",
    "/checkpoint",
    "/challenge",
)


@dataclass(frozen=True)
class HttpResponse:
    """Result of a single GET. ``text`` is decoded body; never log it in errors."""

    status: int
    headers: Mapping[str, str]
    text: str
    final_url: str


class HttpClient(Protocol):
    """Minimal GET client. Implementations must not log in or solve challenges.

    ``get(url)`` returns ``(status, headers, text, final_url)`` or :class:`HttpResponse`.
    Extra keyword ``timeout`` is passed when the implementation accepts it.
    """

    def get(self, url: str) -> HttpResponse | tuple[int, Mapping[str, str], str, str]: ...


def header_value(headers: Mapping[str, str] | Sequence[tuple[str, str]] | None, name: str) -> str:
    if headers is None:
        return ""
    target = name.lower()
    if isinstance(headers, Mapping):
        items = headers.items()
    else:
        items = headers
    for key, value in items:
        if str(key).lower() == target:
            return str(value)
    return ""


def host_of(url: str) -> str:
    return (urlparse(url).netloc or "unknown-host").lower()


def as_response(result: object) -> HttpResponse:
    """Accept scrapers HttpResponse, discovery HttpResponse, or a 4-tuple."""
    if isinstance(result, HttpResponse):
        return result
    if isinstance(result, tuple) and len(result) == 4:
        status, headers, text, final_url = result
        header_map = _mapping(headers)
        return HttpResponse(int(status), header_map, str(text or ""), str(final_url or ""))
    status = getattr(result, "status", None)
    if status is None:
        raise TypeError(
            "HttpClient.get must return HttpResponse or (status, headers, text, final_url)"
        )
    headers = getattr(result, "headers", None)
    text = getattr(result, "text", None)
    final_url = getattr(result, "final_url", None)
    return HttpResponse(
        int(status),
        _mapping(headers),
        str(text or ""),
        str(final_url or ""),
    )


def invoke_get(http: HttpClient, url: str, timeout: float) -> object:
    func = http.get
    try:
        signature = inspect.signature(func)
    except (TypeError, ValueError):
        return func(url)
    if "timeout" in signature.parameters:
        return func(url, timeout=timeout)  # type: ignore[call-arg]
    return func(url)


def fetch_public(
    http: HttpClient,
    url: str,
    *,
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
    sleep: Callable[[float], None] | None = None,
    max_attempts: int = MAX_TRANSIENT_ATTEMPTS,
) -> HttpResponse:
    """GET a public URL. Backs off on HTTP 429 only. Never rotates User-Agent."""

    sleeper = sleep or time.sleep
    last_status: int | None = None
    for attempt in range(max(1, max_attempts)):
        try:
            raw = invoke_get(http, url, timeout)
        except PipelineError:
            raise
        except TimeoutError as exc:
            raise PipelineError(HTTP_TIMEOUT, f"timeout fetching {host_of(url)}") from exc
        except Exception as exc:
            if _looks_like_timeout(exc):
                raise PipelineError(HTTP_TIMEOUT, f"timeout fetching {host_of(url)}") from exc
            raise
        response = as_response(raw)
        last_status = response.status
        if response.status == 429:
            if attempt + 1 < max_attempts:
                sleeper(_retry_delay(response.headers, attempt))
                continue
            raise PipelineError(RATE_LIMITED, f"rate limited at {host_of(url)}")
        return _reject_blocked(response)
    raise PipelineError(RATE_LIMITED, f"rate limited at {host_of(url)} (HTTP {last_status})")


def _mapping(headers: object) -> dict[str, str]:
    if headers is None:
        return {}
    if isinstance(headers, Mapping):
        return {str(k): str(v) for k, v in headers.items()}
    if isinstance(headers, Sequence) and not isinstance(headers, (str, bytes)):
        return {str(k): str(v) for k, v in headers}
    return {}


def _looks_like_timeout(exc: BaseException) -> bool:
    if isinstance(exc, TimeoutError):
        return True
    name = type(exc).__name__.lower()
    if "timeout" in name:
        return True
    return "timed out" in str(exc).lower()


def _retry_delay(headers: Mapping[str, str], attempt: int) -> float:
    raw = header_value(headers, "Retry-After").strip()
    if raw:
        try:
            return min(max(float(raw), 0.0), MAX_BACKOFF_SECONDS)
        except ValueError:
            pass
    return min(0.5 * (2**attempt), MAX_BACKOFF_SECONDS)


def _reject_blocked(response: HttpResponse) -> HttpResponse:
    status = response.status
    host = host_of(response.final_url or "")
    # Discovery StdlibHttpClient uses status 0 for timeout/transport failure.
    if status == 0:
        raise PipelineError(HTTP_TIMEOUT, f"timeout fetching {host}")
    if status in {401, 403, 451}:
        raise PipelineError(PLATFORM_BLOCKED, f"public page blocked (HTTP {status}) at {host}")
    if status in {404, 410}:
        raise PipelineError(HTTP_NOT_FOUND, f"public page not found (HTTP {status}) at {host}")
    if _is_login_destination(response.final_url):
        raise PipelineError(PLATFORM_BLOCKED, f"public page redirected to a login wall at {host}")
    if status >= 400:
        raise PipelineError(PLATFORM_BLOCKED, f"public page blocked (HTTP {status}) at {host}")
    return response


def _is_login_destination(url: str) -> bool:
    path = urlparse(url).path.lower()
    if any(marker in path for marker in _LOGIN_PATH_MARKERS):
        return True
    stripped = path.rstrip("/")
    return stripped.endswith("/login")
