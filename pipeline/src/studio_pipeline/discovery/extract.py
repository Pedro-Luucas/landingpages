"""Extract http(s) and social links from public aggregator HTML."""

from __future__ import annotations

import re
from html.parser import HTMLParser
from urllib.parse import urljoin

_HREF_ATTRS = frozenset({"href", "content", "data-url", "data-href", "src"})
_URL_RE = re.compile(r"https?://[^\s<>\"'`]+", re.IGNORECASE)
_TRAIL_PUNCT = ".,);]}>\"'"


class _AttrCollector(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.values: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        _ = tag
        for name, value in attrs:
            if name.lower() in _HREF_ATTRS and value:
                self.values.append(value.strip())


def _trim_url(raw: str) -> str:
    text = raw.strip()
    while text and text[-1] in _TRAIL_PUNCT:
        text = text[:-1]
    text = text.replace("&amp;", "&")
    return text


def extract_urls_from_html(html: str, *, base_url: str = "") -> list[str]:
    """Collect absolute http(s) URLs from hrefs, attributes, and raw text."""
    found: list[str] = []
    seen: set[str] = set()

    def add(candidate: str) -> None:
        text = _trim_url(candidate)
        if not text:
            return
        if text.startswith("//"):
            text = "https:" + text
        elif text.startswith("/") and base_url:
            text = urljoin(base_url, text)
        if not text.lower().startswith(("http://", "https://")):
            return
        if text not in seen:
            seen.add(text)
            found.append(text)

    parser = _AttrCollector()
    try:
        parser.feed(html)
        parser.close()
    except Exception:
        parser.values = []
    for value in parser.values:
        add(value)
    for match in _URL_RE.findall(html):
        add(match)
    return found
