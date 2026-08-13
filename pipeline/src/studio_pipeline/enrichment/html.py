"""Parse public official-site HTML for commercial facts. No login, no stealth UA."""

from __future__ import annotations

import json
import re
from html.parser import HTMLParser
from typing import Any
from urllib.parse import urljoin, urlparse

from studio_pipeline.discovery.classify import (
    classify_url,
    hostname_of,
    is_google_host,
    looks_like_login_url,
)
from studio_pipeline.http.client import is_public_http_url

MAX_PAGES = 6
FOLLOW_HINTS = (
    "horario",
    "horário",
    "horarios",
    "horários",
    "hours",
    "preco",
    "preço",
    "precos",
    "preços",
    "price",
    "pricing",
    "valores",
    "contato",
    "contact",
    "sobre",
    "about",
    "equipamento",
    "equipment",
    "ensaio",
    "ensaios",
)
_SKIP_SUFFIXES = (
    ".css",
    ".js",
    ".mjs",
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".webp",
    ".svg",
    ".ico",
    ".pdf",
    ".zip",
    ".mp3",
    ".mp4",
    ".woff",
    ".woff2",
)
_SKIP_TAGS = frozenset({"script", "style", "noscript", "svg"})
_HEADINGS = frozenset({"h1", "h2", "h3", "h4", "h5", "h6"})
_DAY_INTERVAL_RE = re.compile(
    r"(.+?)\s*[:\-–—]\s*(\d{1,2}[:h]\d{2})\s*[-–—atéto]+\s*(\d{1,2}[:h]\d{2})",
    re.IGNORECASE,
)
_CURRENCY_RE = re.compile(
    r"(R\$\s*[\d.]{1,12}(?:,\d{2})?|\$\s*[\d,]{1,12}(?:\.\d{2})?|"
    r"[\d.]{1,12}(?:,\d{2})?\s*(?:BRL|USD|EUR|reais))",
    re.IGNORECASE,
)


def collapse(value: object) -> str:
    return " ".join(str(value or "").split())


def excerpt_of(text: str, limit: int = 180) -> str:
    collapsed = collapse(text)
    if len(collapsed) <= limit:
        return collapsed
    return collapsed[: limit - 3] + "..."


def is_google_maps_url(url: str) -> bool:
    host = hostname_of(url)
    path = (urlparse(url).path or "").lower()
    if host in {"maps.google.com", "maps.app.goo.gl", "goo.gl"}:
        return True
    if is_google_host(host):
        return host.startswith("maps.") or "/maps" in path
    return False


def same_host(left: str, right: str) -> bool:
    return hostname_of(left) == hostname_of(right) and bool(hostname_of(left))


def _abs_http(href: str, base_url: str) -> str | None:
    text = (href or "").strip()
    if not text or text.startswith(("#", "mailto:", "tel:", "javascript:")):
        return None
    joined = urljoin(base_url, text)
    parsed = urlparse(joined)
    if parsed.scheme not in {"http", "https"}:
        return None
    path = (parsed.path or "").lower()
    if any(path.endswith(suffix) for suffix in _SKIP_SUFFIXES):
        return None
    return joined.split("#", 1)[0]


def _context_from_heading(text: str) -> str | None:
    blob = collapse(text).lower()
    if any(token in blob for token in ("equipamento", "equipment", "gear", "setup")):
        return "equipment"
    if any(token in blob for token in ("preço", "preco", "price", "pricing", "valores", "tabela")):
        return "prices"
    if any(token in blob for token in ("horário", "horario", "hours", "funcionamento")):
        return "hours"
    if any(token in blob for token in ("sobre", "about", "o estúdio", "o estudio")):
        return "about"
    if any(token in blob for token in ("endereço", "endereco", "address", "localização", "localizacao")):
        return "address"
    return None


def _day_label(value: object) -> str:
    if isinstance(value, list):
        parts = [_day_label(item) for item in value if _day_label(item)]
        return ", ".join(parts)
    text = collapse(value)
    if "schema.org/" in text.lower():
        text = text.rstrip("/").split("/")[-1]
    return text


def _interval_pair(opens: object, closes: object) -> str | None:
    start = collapse(opens)
    end = collapse(closes)
    if not start or not end:
        return None
    return f"{start}-{end}"


def _split_intervals(raw: object) -> list[str]:
    text = collapse(raw)
    if not text:
        return []
    parts = [collapse(part) for part in re.split(r"[,;/]| e ", text)]
    return [part for part in parts if part]


class PageFacts:
    __slots__ = (
        "description",
        "description_excerpt",
        "equipment",
        "equipment_excerpt",
        "prices",
        "prices_excerpt",
        "hours",
        "hours_excerpt",
        "map",
        "map_excerpt",
        "links",
    )

    def __init__(self) -> None:
        self.description: str | None = None
        self.description_excerpt: str | None = None
        self.equipment: list[str] = []
        self.equipment_excerpt: str | None = None
        self.prices: list[dict[str, str]] = []
        self.prices_excerpt: str | None = None
        self.hours: list[dict[str, Any]] = []
        self.hours_excerpt: str | None = None
        self.map: dict[str, Any] | None = None
        self.map_excerpt: str | None = None
        self.links: list[tuple[str, str]] = []


class _FactHTMLParser(HTMLParser):
    def __init__(self, *, base_url: str) -> None:
        super().__init__(convert_charrefs=True)
        self.base_url = base_url
        self.meta: dict[str, str] = {}
        self.json_ld: list[str] = []
        self.links: list[tuple[str, str]] = []
        self.equipment: list[str] = []
        self.prices: list[dict[str, str]] = []
        self.hours: list[dict[str, Any]] = []
        self.descriptions: list[str] = []
        self.addresses: list[str] = []
        self._skip_depth = 0
        self._in_ld = False
        self._ld_buf: list[str] = []
        self._ctx: str | None = None
        self._ctx_depth = 0
        self._capture: list[str] | None = None
        self._capture_kind: str | None = None
        self._link_href: str | None = None
        self._link_buf: list[str] | None = None
        self._price: dict[str, str] | None = None
        self._price_tag: str | None = None
        self._hour: dict[str, Any] | None = None
        self._hour_tag: str | None = None
        self._li_kind: str | None = None
        self._heading = False
        self._address = False

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.handle_starttag(tag, attrs)

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        data = {key.lower(): (value or "") for key, value in attrs}
        if self._skip_depth:
            if tag in _SKIP_TAGS:
                self._skip_depth += 1
            return
        if tag in _SKIP_TAGS:
            if tag == "script" and "application/ld+json" in data.get("type", "").lower():
                self._in_ld = True
                self._ld_buf = []
                return
            self._skip_depth = 1
            return
        if tag == "meta":
            prop = (data.get("property") or data.get("name") or "").lower()
            if prop and data.get("content"):
                self.meta[prop] = data["content"]
            return
        if tag == "a" and data.get("href"):
            abs_url = _abs_http(data["href"], self.base_url)
            if abs_url:
                self._link_href = abs_url
                self._link_buf = []
        ctx = self._section_from_attrs(data)
        if ctx:
            self._ctx = ctx
            self._ctx_depth = 1
        elif self._ctx and tag in {"section", "article", "div", "ul", "ol", "table"}:
            self._ctx_depth += 1
        if "data-description" in data:
            self._capture = []
            self._capture_kind = "description"
        if tag == "address" or "data-address" in data:
            self._address = True
            self._capture = []
            self._capture_kind = "address"
        if tag in _HEADINGS:
            self._heading = True
            self._capture = []
            self._capture_kind = "heading"
        if self._is_price_node(tag, data):
            self._price = self._price_from_attrs(data)
            self._price_tag = tag
            self._capture = []
            self._capture_kind = "price"
        if self._is_hour_node(tag, data):
            self._hour = self._hour_from_attrs(data)
            self._hour_tag = tag
            self._capture = []
            self._capture_kind = "hour"
        if tag == "li":
            kind = self._ctx if self._ctx in {"equipment", "prices", "hours"} else None
            if "data-equipment-item" in data:
                kind = "equipment"
            if kind:
                self._li_kind = kind
                self._capture = []
                self._capture_kind = f"li:{kind}"
                if kind == "prices" and self._price is None:
                    self._price = self._price_from_attrs(data)
                if kind == "hours" and self._hour is None:
                    self._hour = self._hour_from_attrs(data)

    def handle_endtag(self, tag: str) -> None:
        if self._in_ld and tag == "script":
            blob = "".join(self._ld_buf).strip()
            if blob:
                self.json_ld.append(blob)
            self._in_ld = False
            self._ld_buf = []
            return
        if self._skip_depth:
            if tag in _SKIP_TAGS:
                self._skip_depth = max(0, self._skip_depth - 1)
            return
        text = collapse("".join(self._capture)) if self._capture is not None else ""
        if tag == "a" and self._link_href:
            self.links.append((self._link_href, collapse("".join(self._link_buf or []))))
            self._link_href = None
            self._link_buf = None
        if self._heading and tag in _HEADINGS:
            heading_ctx = _context_from_heading(text)
            if heading_ctx:
                self._ctx = heading_ctx
                self._ctx_depth = max(self._ctx_depth, 1)
            self._heading = False
            if self._capture_kind == "heading":
                self._capture = None
                self._capture_kind = None
        if self._capture_kind == "description" and tag in {"p", "div", "span", "section"}:
            if text:
                self.descriptions.append(text)
            self._capture = None
            self._capture_kind = None
        if self._address and tag in {"address", "p", "div", "span"}:
            if text:
                self.addresses.append(text)
            self._address = False
            if self._capture_kind == "address":
                self._capture = None
                self._capture_kind = None
        if self._li_kind and tag == "li":
            self._finish_li(text)
            self._li_kind = None
            if self._capture_kind and self._capture_kind.startswith("li:"):
                self._capture = None
                self._capture_kind = None
        if self._price is not None and tag == self._price_tag:
            self._finish_price(text)
        if self._hour is not None and tag == self._hour_tag:
            self._finish_hour(text)
        if self._ctx and tag in {"section", "article", "div", "ul", "ol", "table"}:
            self._ctx_depth = max(0, self._ctx_depth - 1)
            if self._ctx_depth == 0:
                self._ctx = None

    def handle_data(self, data: str) -> None:
        if self._in_ld:
            self._ld_buf.append(data)
            return
        if self._skip_depth:
            return
        if self._link_buf is not None:
            self._link_buf.append(data)
        if self._capture is not None:
            self._capture.append(data)

    def _section_from_attrs(self, data: dict[str, str]) -> str | None:
        if "data-equipment" in data:
            return "equipment"
        if "data-prices" in data or "data-price-list" in data:
            return "prices"
        if "data-hours" in data or "data-opening-hours" in data:
            return "hours"
        if "data-about" in data:
            return "about"
        ident = f"{data.get('id', '')} {data.get('class', '')} {data.get('aria-label', '')}".lower()
        return _context_from_heading(ident) if ident.strip() else None

    def _is_price_node(self, tag: str, data: dict[str, str]) -> bool:
        _ = tag
        return "data-price" in data or "data-amount" in data and self._ctx == "prices"

    def _is_hour_node(self, tag: str, data: dict[str, str]) -> bool:
        _ = tag
        return "data-day" in data or "data-hours-row" in data

    def _price_from_attrs(self, data: dict[str, str]) -> dict[str, str]:
        payload: dict[str, str] = {}
        label = collapse(data.get("data-label") or data.get("data-name"))
        amount = collapse(data.get("data-amount") or data.get("data-price"))
        conditions = collapse(data.get("data-conditions") or data.get("data-note"))
        if label:
            payload["label"] = label
        if amount and amount.lower() != "true":
            payload["amountText"] = amount
        if conditions:
            payload["conditions"] = conditions
        return payload

    def _hour_from_attrs(self, data: dict[str, str]) -> dict[str, Any]:
        payload: dict[str, Any] = {}
        day = collapse(data.get("data-day") or data.get("data-weekday"))
        if day:
            payload["day"] = day
        intervals = _split_intervals(data.get("data-intervals") or data.get("data-hours"))
        if intervals:
            payload["intervals"] = intervals
        return payload

    def _finish_li(self, text: str) -> None:
        kind = self._li_kind
        if kind == "equipment" and text:
            self.equipment.append(text)
        elif kind == "prices":
            self._finish_price(text)
        elif kind == "hours":
            self._finish_hour(text)

    def _finish_price(self, text: str) -> None:
        payload = dict(self._price or {})
        self._price = None
        self._price_tag = None
        if self._capture_kind == "price":
            self._capture = None
            self._capture_kind = None
        if not payload.get("label") or not payload.get("amountText"):
            parsed = _price_from_text(text)
            if parsed:
                if not payload.get("label"):
                    payload["label"] = parsed["label"]
                if not payload.get("amountText"):
                    payload["amountText"] = parsed["amountText"]
                if parsed.get("conditions") and not payload.get("conditions"):
                    payload["conditions"] = parsed["conditions"]
        if payload.get("label") and payload.get("amountText"):
            self.prices.append(payload)

    def _finish_hour(self, text: str) -> None:
        payload = dict(self._hour or {})
        self._hour = None
        self._hour_tag = None
        if self._capture_kind == "hour":
            self._capture = None
            self._capture_kind = None
        if not payload.get("day"):
            parsed = _hour_from_text(text)
            if parsed:
                payload = parsed
        elif "intervals" not in payload:
            parsed = _hour_from_text(text)
            if parsed and parsed.get("intervals"):
                payload["intervals"] = parsed["intervals"]
        day = collapse(payload.get("day"))
        if not day:
            return
        intervals = payload.get("intervals")
        if not isinstance(intervals, list):
            intervals = []
        self.hours.append({"day": day, "intervals": [str(item) for item in intervals if str(item).strip()]})


def _price_from_text(text: str) -> dict[str, str] | None:
    collapsed = collapse(text)
    if not collapsed:
        return None
    match = _CURRENCY_RE.search(collapsed)
    if not match:
        return None
    amount = collapse(match.group(0))
    label = collapse(collapsed[: match.start()].strip(" -:–—|"))
    rest = collapse(collapsed[match.end() :].strip(" -:–—|()"))
    if not label:
        return None
    payload = {"label": label, "amountText": amount}
    if rest:
        payload["conditions"] = rest
    return payload


def _hour_from_text(text: str) -> dict[str, Any] | None:
    collapsed = collapse(text)
    if not collapsed:
        return None
    match = _DAY_INTERVAL_RE.search(collapsed)
    if match:
        day = collapse(match.group(1))
        start = match.group(2).replace("h", ":")
        end = match.group(3).replace("h", ":")
        if day:
            return {"day": day, "intervals": [f"{start}-{end}"]}
    lower = collapsed.lower()
    if "fechado" in lower or "closed" in lower:
        day = collapse(re.split(r"[:\-–—]", collapsed, maxsplit=1)[0])
        if day and day.lower() not in {"fechado", "closed"}:
            return {"day": day, "intervals": []}
    return None


def _walk_json(value: object) -> list[object]:
    found: list[object] = []
    stack: list[object] = [value]
    while stack:
        current = stack.pop()
        found.append(current)
        if isinstance(current, dict):
            stack.extend(current.values())
        elif isinstance(current, list):
            stack.extend(current)
    return found


def _ld_types(node: dict[str, Any]) -> set[str]:
    raw = node.get("@type") or node.get("type") or ""
    if isinstance(raw, list):
        return {str(item).lower() for item in raw}
    return {str(raw).lower()} if raw else set()


def _apply_json_ld(page: PageFacts, blobs: list[str]) -> None:
    for blob in blobs:
        try:
            payload = json.loads(blob)
        except json.JSONDecodeError:
            continue
        for node in _walk_json(payload):
            if not isinstance(node, dict):
                continue
            types = _ld_types(node)
            if types & {
                "localbusiness",
                "organization",
                "place",
                "store",
                "professionalservice",
                "musicgroup",
            }:
                description = collapse(node.get("description"))
                if description and not page.description:
                    page.description = description
                    page.description_excerpt = excerpt_of(description)
                _apply_ld_address(page, node)
                _apply_ld_hours(page, node)
            if types & {"offer", "aggregateoffer"}:
                price = _offer_to_price(node)
                if price:
                    page.prices.append(price)
                    if not page.prices_excerpt:
                        page.prices_excerpt = excerpt_of(
                            f"{price['label']} {price['amountText']}"
                        )
            equipment = node.get("equipment")
            if isinstance(equipment, list):
                for item in equipment:
                    text = collapse(item if not isinstance(item, dict) else item.get("name"))
                    if text:
                        page.equipment.append(text)


def _apply_ld_address(page: PageFacts, node: dict[str, Any]) -> None:
    mapped: dict[str, Any] = dict(page.map or {})
    geo = node.get("geo") if isinstance(node.get("geo"), dict) else {}
    lat = geo.get("latitude") if geo else node.get("latitude")
    lng = geo.get("longitude") if geo else node.get("longitude")
    try:
        if lat is not None and lng is not None:
            lat_f = float(lat)
            lng_f = float(lng)
            if -90 <= lat_f <= 90 and -180 <= lng_f <= 180:
                mapped["latitude"] = lat_f
                mapped["longitude"] = lng_f
    except (TypeError, ValueError):
        pass
    address = node.get("address")
    original = ""
    if isinstance(address, str):
        original = collapse(address)
    elif isinstance(address, dict):
        original = collapse(address.get("streetAddress") or "")
        parts = [
            collapse(address.get("streetAddress")),
            collapse(address.get("addressLocality")),
            collapse(address.get("addressRegion")),
            collapse(address.get("postalCode")),
        ]
        joined = ", ".join(part for part in parts if part)
        if joined:
            mapped["address"] = joined
            original = original or joined
    if original and "address" not in mapped:
        mapped["address"] = original
    if mapped:
        page.map = mapped
        page.map_excerpt = excerpt_of(original or json.dumps(mapped, ensure_ascii=False))


def _apply_ld_hours(page: PageFacts, node: dict[str, Any]) -> None:
    spec = node.get("openingHoursSpecification")
    rows: list[dict[str, Any]] = []
    if isinstance(spec, dict):
        spec = [spec]
    if isinstance(spec, list):
        for item in spec:
            if not isinstance(item, dict):
                continue
            day = _day_label(item.get("dayOfWeek"))
            interval = _interval_pair(item.get("opens"), item.get("closes"))
            if not day:
                continue
            intervals = [interval] if interval else []
            rows.append({"day": day, "intervals": intervals})
            original = collapse(
                f"{day} {item.get('opens') or ''}-{item.get('closes') or ''}".strip("- ")
            )
            if original and not page.hours_excerpt:
                page.hours_excerpt = excerpt_of(original)
    hours = node.get("openingHours")
    if not rows and hours:
        values = hours if isinstance(hours, list) else [hours]
        for raw in values:
            text = collapse(raw)
            parsed = _hour_from_text(text.replace(" ", " ", 1)) if text else None
            if parsed:
                rows.append(parsed)
                if not page.hours_excerpt:
                    page.hours_excerpt = excerpt_of(text)
            elif text:
                parts = text.split()
                day = parts[0] if parts else text
                rest = " ".join(parts[1:]) if len(parts) > 1 else ""
                intervals = _split_intervals(rest.replace("–", "-"))
                rows.append({"day": day, "intervals": intervals})
                if not page.hours_excerpt:
                    page.hours_excerpt = excerpt_of(text)
    if rows and not page.hours:
        page.hours = rows


def _offer_to_price(node: dict[str, Any]) -> dict[str, str] | None:
    offered = node.get("itemOffered")
    offered_name = ""
    if isinstance(offered, dict):
        offered_name = collapse(offered.get("name"))
    label = collapse(node.get("name") or offered_name)
    raw_price = node.get("price")
    if raw_price is None:
        raw_price = node.get("lowPrice")
    amount = collapse(raw_price)
    currency = collapse(node.get("priceCurrency"))
    if not label or not amount:
        return None
    if currency and currency.upper() not in amount.upper() and "R$" not in amount:
        amount_text = f"{currency} {amount}".strip()
    else:
        amount_text = amount
    payload = {"label": label, "amountText": amount_text}
    conditions = collapse(node.get("description"))
    if conditions:
        payload["conditions"] = conditions
    return payload


def parse_official_html(text: str, *, base_url: str) -> PageFacts:
    parser = _FactHTMLParser(base_url=base_url)
    parser.feed(text or "")
    parser.close()
    page = PageFacts()
    meta_desc = collapse(parser.meta.get("og:description") or parser.meta.get("description"))
    if meta_desc:
        page.description = meta_desc
        page.description_excerpt = excerpt_of(meta_desc)
    if parser.descriptions:
        page.description = parser.descriptions[0]
        page.description_excerpt = excerpt_of(parser.descriptions[0])
    page.equipment = _unique(parser.equipment)
    if page.equipment:
        page.equipment_excerpt = excerpt_of("; ".join(page.equipment))
    page.prices = list(parser.prices)
    if page.prices:
        page.prices_excerpt = excerpt_of(
            "; ".join(f"{row['label']} {row['amountText']}" for row in page.prices)
        )
    page.hours = list(parser.hours)
    if page.hours and not page.hours_excerpt:
        page.hours_excerpt = excerpt_of(
            "; ".join(
                f"{row['day']} {' '.join(row.get('intervals') or [])}".strip()
                for row in page.hours
            )
        )
    if parser.addresses:
        page.map = {"address": parser.addresses[0]}
        page.map_excerpt = excerpt_of(parser.addresses[0])
    page.links = list(parser.links)
    _apply_json_ld(page, parser.json_ld)
    if page.equipment:
        page.equipment = _unique(page.equipment)
        page.equipment_excerpt = page.equipment_excerpt or excerpt_of("; ".join(page.equipment))
    return page


def _unique(items: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        text = collapse(item)
        key = text.lower()
        if not text or key in seen:
            continue
        seen.add(key)
        out.append(text)
    return out


def follow_candidates(page: PageFacts, *, seed_url: str) -> list[str]:
    ranked: list[tuple[int, str]] = []
    seen: set[str] = set()
    for href, label in page.links:
        if not same_host(href, seed_url):
            continue
        if looks_like_login_url(href) or is_google_maps_url(href) or is_google_host(hostname_of(href)):
            continue
        if classify_url(href).kind != "official_site":
            continue
        if not is_public_http_url(href):
            continue
        blob = f"{urlparse(href).path} {label}".lower()
        if not any(hint in blob for hint in FOLLOW_HINTS):
            continue
        key = href.strip().rstrip("/")
        if key in seen:
            continue
        seen.add(key)
        priority = next(
            (index for index, hint in enumerate(FOLLOW_HINTS) if hint in blob),
            99,
        )
        ranked.append((priority, href))
    ranked.sort(key=lambda item: (item[0], item[1]))
    return [url for _, url in ranked]
