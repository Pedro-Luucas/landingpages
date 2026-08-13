"""Tiny public HTTP client used by discovery for intermediate pages."""

from studio_pipeline.http.adapter import ScraperHttpAdapter
from studio_pipeline.http.binary import (
    MAX_BINARY_BODY_BYTES,
    FakeBinaryHttp,
    StdlibBinaryHttp,
)
from studio_pipeline.http.client import (
    DEFAULT_USER_AGENT,
    FakeHttpClient,
    HttpClient,
    HttpResponse,
    StdlibHttpClient,
    is_public_http_url,
)

__all__ = [
    "DEFAULT_USER_AGENT",
    "FakeBinaryHttp",
    "FakeHttpClient",
    "HttpClient",
    "HttpResponse",
    "MAX_BINARY_BODY_BYTES",
    "ScraperHttpAdapter",
    "StdlibBinaryHttp",
    "StdlibHttpClient",
    "is_public_http_url",
]
