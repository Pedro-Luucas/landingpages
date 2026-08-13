"""Deterministic factuality checks for generated.json (plan §8 G / §17 M4)."""

from __future__ import annotations

import json
import re
from typing import Any

from studio_pipeline.errors import FACT_WITHOUT_EVIDENCE, PipelineError

_HOUR_SEP = r"(?:[–\-]|às|as|até|ate)"
PRICE_RE = re.compile(
    r"R\$\s*\d[\d.]{0,12}(?:,\d{2})?"
    r"|\b\d{1,6},\d{2}\s*(?:reais)?\b"
    r"|\b\d{1,6}\s*reais\b"
    r"|\b(?:USD|EUR|€)\s*\d[\d.,]*",
    re.IGNORECASE,
)
RATING_RE = re.compile(r"\b[0-5][.,]\d\b|\b[0-5]\s*/\s*5\b")
HOURS_RE = re.compile(
    rf"\b\d{{1,2}}:\d{{2}}\s*{_HOUR_SEP}\s*\d{{1,2}}:\d{{2}}\b"
    rf"|\b\d{{1,2}}\s*h\s*{_HOUR_SEP}\s*\d{{1,2}}\s*h\b",
    re.IGNORECASE,
)
ADDRESS_RE = re.compile(
    r"\b(?:Rua|Avenida|Av\.|Alameda|Travessa|Rodovia|Praça)\b",
    re.IGNORECASE,
)
COORD_RE = re.compile(r"\b-?\d{1,2}\.\d{3,}\s*,\s*-?\d{1,3}\.\d{3,}\b")
_CLOSED_HOURS = frozenset({"fechado", "closed", "fechado."})
_DAY_ORDER = (
    "monday",
    "tuesday",
    "wednesday",
    "thursday",
    "friday",
    "saturday",
    "sunday",
)
_DAY_CANON = {
    "monday": "monday",
    "mon": "monday",
    "segunda": "monday",
    "segunda-feira": "monday",
    "tuesday": "tuesday",
    "tue": "tuesday",
    "terça": "tuesday",
    "terca": "tuesday",
    "terça-feira": "tuesday",
    "terca-feira": "tuesday",
    "wednesday": "wednesday",
    "wed": "wednesday",
    "quarta": "wednesday",
    "quarta-feira": "wednesday",
    "thursday": "thursday",
    "thu": "thursday",
    "quinta": "thursday",
    "quinta-feira": "thursday",
    "friday": "friday",
    "fri": "friday",
    "sexta": "friday",
    "sexta-feira": "friday",
    "saturday": "saturday",
    "sat": "saturday",
    "sábado": "saturday",
    "sabado": "saturday",
    "sunday": "sunday",
    "sun": "sunday",
    "domingo": "sunday",
}

_SECTION_FACTS = {
    "pricing": "prices",
    "hours": "openingHours",
    "reviews": "googleReviews",
    "equipment": "equipment",
    "map": "map",
}

_COPY_FACT_KEYS = {
    "pricing": "prices",
    "hours": "openingHours",
    "reviews": "googleReviews",
    "equipment": "equipment",
}


def validate_generated(generated: dict[str, Any], dossier: dict[str, Any]) -> None:
    """Raise ``PipelineError(FACT_WITHOUT_EVIDENCE)`` if copy is not evidenced."""
    if not isinstance(generated, dict) or not isinstance(dossier, dict):
        raise PipelineError(
            FACT_WITHOUT_EVIDENCE,
            "generated and dossier must be JSON objects",
        )
    facts = dossier.get("facts") if isinstance(dossier.get("facts"), dict) else {}
    copy = generated.get("copy") if isinstance(generated.get("copy"), dict) else {}
    sections = generated.get("sections") if isinstance(generated.get("sections"), list) else []
    claims = generated.get("factualClaims") if isinstance(generated.get("factualClaims"), list) else []
    index = _EvidenceIndex(dossier)

    _check_enabled_sections(sections, facts)
    _check_copy_requires_facts(copy, facts)
    _check_structured_copy(copy, claims, index, facts)
    _check_text_claims(copy, claims, index)


def _check_enabled_sections(sections: list[Any], facts: dict[str, Any]) -> None:
    for item in sections:
        if not isinstance(item, dict) or not item.get("enabled"):
            continue
        section_id = str(item.get("id") or "")
        fact_key = _SECTION_FACTS.get(section_id)
        if not fact_key:
            continue
        rows = facts.get(fact_key)
        if not isinstance(rows, list) or not rows:
            raise PipelineError(
                FACT_WITHOUT_EVIDENCE,
                f"section {section_id!r} is enabled but dossier.facts.{fact_key} is empty",
            )


def _check_copy_requires_facts(copy: dict[str, Any], facts: dict[str, Any]) -> None:
    for copy_key, fact_key in _COPY_FACT_KEYS.items():
        if copy_key not in copy:
            continue
        rows = facts.get(fact_key)
        if not isinstance(rows, list) or not rows:
            raise PipelineError(
                FACT_WITHOUT_EVIDENCE,
                f"copy.{copy_key} is present but dossier.facts.{fact_key} is empty",
            )


def _check_structured_copy(
    copy: dict[str, Any],
    claims: list[Any],
    index: "_EvidenceIndex",
    facts: dict[str, Any],
) -> None:
    pricing = copy.get("pricing")
    if isinstance(pricing, dict):
        items = pricing.get("items") or []
        if isinstance(items, list):
            for offset, item in enumerate(items):
                if not isinstance(item, dict):
                    continue
                path = f"copy.pricing.items[{offset}]"
                value = str(item.get("value") or "")
                label = str(item.get("label") or "")
                _require_supported(path, value, claims, index, kind="price")
                if label:
                    _require_supported(f"{path}.label", label, claims, index, kind="generic")

    hours = copy.get("hours")
    if isinstance(hours, dict):
        items = hours.get("items") or []
        if isinstance(items, list):
            for offset, item in enumerate(items):
                if not isinstance(item, dict):
                    continue
                path = f"copy.hours.items[{offset}]"
                value_text = str(item.get("value") or "")
                if _normalize(value_text) in _CLOSED_HOURS:
                    _require_closed_hours(
                        path,
                        str(item.get("day") or ""),
                        claims,
                        index,
                    )
                    continue
                _require_claim(path, claims, index)
                _require_supported(
                    f"{path}.value",
                    value_text,
                    claims,
                    index,
                    kind="hours",
                )

    equipment = copy.get("equipment")
    if isinstance(equipment, dict):
        items = equipment.get("items") or []
        if isinstance(items, list):
            blob = _fact_blob(facts.get("equipment"))
            for offset, item in enumerate(items):
                text = str(item or "").strip()
                if not text:
                    continue
                path = f"copy.equipment.items[{offset}]"
                _require_claim(path, claims, index)
                if _normalize(text) not in _normalize(blob):
                    raise PipelineError(
                        FACT_WITHOUT_EVIDENCE,
                        f"{path}: equipment item {text!r} is not present in dossier.facts.equipment",
                    )

    reviews = copy.get("reviews")
    if isinstance(reviews, dict):
        _require_claim("copy.reviews", claims, index)
        rating = reviews.get("rating")
        if isinstance(rating, (int, float)):
            _require_supported(
                "copy.reviews.rating",
                str(rating),
                claims,
                index,
                kind="rating",
            )
        count = reviews.get("count")
        if isinstance(count, int):
            _require_supported(
                "copy.reviews.count",
                str(count),
                claims,
                index,
                kind="count",
            )
        for offset, excerpt in enumerate(reviews.get("excerpts") or []):
            text = str(excerpt or "").strip()
            if text:
                _require_supported(
                    f"copy.reviews.excerpts[{offset}]",
                    text,
                    claims,
                    index,
                    kind="quote",
                )


def _check_text_claims(
    copy: dict[str, Any],
    claims: list[Any],
    index: "_EvidenceIndex",
) -> None:
    for path, value in _walk(copy, "copy"):
        if isinstance(value, (int, float)) and "reviews" in path and "rating" in path:
            _require_supported(path, str(value), claims, index, kind="rating")
            continue
        if not isinstance(value, str) or not value.strip():
            continue
        for match in PRICE_RE.finditer(value):
            _require_supported(path, match.group(), claims, index, kind="price")
        if "pricing" not in path:
            for match in RATING_RE.finditer(value):
                _require_supported(path, match.group(), claims, index, kind="rating")
        if "hours" not in path:
            for match in HOURS_RE.finditer(value):
                _require_supported(path, match.group(), claims, index, kind="hours")
        for span in _address_spans(value):
            _require_supported(path, span, claims, index, kind="address")


def _require_claim(path: str, claims: list[Any], index: "_EvidenceIndex") -> list[str]:
    refs: list[str] = []
    for claim in claims:
        if not isinstance(claim, dict):
            continue
        claim_path = str(claim.get("path") or "")
        if not _path_covers(claim_path, path):
            continue
        evidence_refs = claim.get("evidenceRefs") or []
        if not isinstance(evidence_refs, list) or not evidence_refs:
            continue
        refs.extend(str(item) for item in evidence_refs if str(item).strip())
    if not refs:
        raise PipelineError(
            FACT_WITHOUT_EVIDENCE,
            f"{path}: missing factualClaims with resolving evidenceRefs",
        )
    unresolved = [ref for ref in refs if not index.resolve(ref)]
    if unresolved:
        raise PipelineError(
            FACT_WITHOUT_EVIDENCE,
            f"{path}: evidenceRefs do not resolve in dossier ({unresolved[0]})",
        )
    return refs


def _require_supported(
    path: str,
    text: str,
    claims: list[Any],
    index: "_EvidenceIndex",
    *,
    kind: str,
) -> None:
    snippet = str(text or "").strip()
    if not snippet:
        return
    refs = _require_claim(path, claims, index)
    if kind == "generic":
        return
    raw_blobs = [index.blob(ref) for ref in refs]
    blobs = [_normalize(raw) for raw in raw_blobs]
    needle = _normalize(snippet)
    if kind == "hours":
        needle = needle.replace("–", "-").replace("—", "-")
        blobs = [blob.replace("–", "-").replace("—", "-") for blob in blobs]
    if kind in {"rating", "count"}:
        if any(_number_mentioned(needle, blob) for blob in blobs):
            return
        raise PipelineError(
            FACT_WITHOUT_EVIDENCE,
            f"{path}: {kind} value {snippet!r} is not supported by evidenceRefs",
        )
    if kind == "price":
        snippet_prices = _price_tokens(snippet)
        evidence_prices: set[str] = set()
        for raw in raw_blobs:
            evidence_prices.update(_price_tokens(raw))
        if snippet_prices and snippet_prices <= evidence_prices:
            return
        raise PipelineError(
            FACT_WITHOUT_EVIDENCE,
            f"{path}: {kind} value {snippet!r} is not supported by evidenceRefs",
        )
    if any(needle and needle in blob for blob in blobs):
        return
    if kind == "address":
        tokens = [
            token
            for token in re.split(r"[\s,;]+", snippet)
            if len(_normalize(token)) > 3
        ]
        if tokens and all(
            any(_normalize(token) in blob for blob in blobs) for token in tokens
        ):
            return
    raise PipelineError(
        FACT_WITHOUT_EVIDENCE,
        f"{path}: {kind} value {snippet!r} is not supported by evidenceRefs",
    )


def _require_closed_hours(
    path: str,
    day_label: str,
    claims: list[Any],
    index: "_EvidenceIndex",
) -> None:
    refs = _require_claim(path, claims, index)
    nodes: list[Any] = []
    for ref in refs:
        nodes.extend(index.nodes(ref))
    by_day = _opening_hours_by_day(nodes)
    days = _parse_hour_days(day_label)
    if days:
        open_days = [
            day
            for day in days
            if day in by_day and not _intervals_closed(by_day[day])
        ]
        if open_days:
            raise PipelineError(
                FACT_WITHOUT_EVIDENCE,
                f"{path}: closed hours value 'Fechado' is not supported by evidence for {open_days[0]}",
            )
        if any(day in by_day for day in days):
            return
    blobs = [_normalize(index.blob(ref)) for ref in refs]
    if any(re.search(r"\b(fechado|closed)\b", blob) for blob in blobs):
        return
    if by_day and all(_intervals_closed(intervals) for intervals in by_day.values()):
        return
    raise PipelineError(
        FACT_WITHOUT_EVIDENCE,
        f"{path}: closed hours value 'Fechado' is not supported by evidenceRefs",
    )


def _opening_hours_by_day(nodes: list[Any]) -> dict[str, list[Any]]:
    by_day: dict[str, list[Any]] = {}

    def visit(value: Any) -> None:
        if isinstance(value, dict):
            day = _canon_day(value.get("day"))
            if day is not None and "intervals" in value:
                intervals = value.get("intervals")
                by_day[day] = intervals if isinstance(intervals, list) else []
            for child in value.values():
                visit(child)
        elif isinstance(value, list):
            for child in value:
                visit(child)

    for node in nodes:
        visit(node)
    return by_day


def _canon_day(raw: object) -> str | None:
    text = _normalize(str(raw or ""))
    if not text:
        return None
    return _DAY_CANON.get(text) or _DAY_CANON.get(text.replace("feira", "").strip(" -"))


def _parse_hour_days(label: str) -> list[str] | None:
    text = _normalize(label)
    if not text:
        return None
    hits: list[tuple[int, str]] = []
    for alias, canon in sorted(_DAY_CANON.items(), key=lambda item: -len(item[0])):
        pattern = rf"(?<![a-zà-ú]){re.escape(alias)}(?![a-zà-ú])"
        for match in re.finditer(pattern, text):
            hits.append((match.start(), canon))
    hits.sort()
    days: list[str] = []
    for _, canon in hits:
        if canon not in days:
            days.append(canon)
    if not days:
        return None
    if len(days) >= 2 and re.search(r"\ba\b", text):
        first = _DAY_ORDER.index(days[0])
        last = _DAY_ORDER.index(days[-1])
        if first <= last:
            return list(_DAY_ORDER[first : last + 1])
    return days


def _intervals_closed(intervals: list[Any]) -> bool:
    return not any(str(item).strip() for item in intervals)


def _address_spans(text: str) -> list[str]:
    spans: list[str] = []
    for match in ADDRESS_RE.finditer(text):
        stop = len(text)
        for idx in range(match.start(), len(text)):
            if text[idx] in ".!?\n":
                stop = idx
                break
        span = text[match.start() : stop].strip(" ,;")
        if span:
            spans.append(span)
    for match in COORD_RE.finditer(text):
        spans.append(match.group())
    return spans


def _number_mentioned(needle: str, blob: str) -> bool:
    if not needle:
        return False
    variants = {needle, needle.replace(".", ","), needle.replace(",", ".")}
    for item in variants:
        if not item:
            continue
        if re.search(
            rf"(?<![\d.,]){re.escape(item)}(?![\d]|[.,]\d)",
            blob,
        ):
            return True
    return False


def _path_covers(claim_path: str, field_path: str) -> bool:
    if not claim_path:
        return False
    if field_path == claim_path:
        return True
    return field_path.startswith(claim_path + ".") or field_path.startswith(
        claim_path + "["
    )


def _walk(value: Any, prefix: str) -> list[tuple[str, Any]]:
    found: list[tuple[str, Any]] = []
    if isinstance(value, dict):
        for key, child in value.items():
            path = f"{prefix}.{key}" if prefix else str(key)
            found.extend(_walk(child, path))
    elif isinstance(value, list):
        for offset, child in enumerate(value):
            found.extend(_walk(child, f"{prefix}[{offset}]"))
    else:
        found.append((prefix, value))
    return found


def _fact_blob(rows: object) -> str:
    if not isinstance(rows, list):
        return ""
    return json.dumps(rows, ensure_ascii=False, default=str)


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip().lower()


def _price_tokens(text: str) -> set[str]:
    tokens: set[str] = set()
    for match in PRICE_RE.finditer(str(text or "")):
        tokens.add(re.sub(r"\s+", "", _normalize(match.group())))
    return tokens


class _EvidenceIndex:
    def __init__(self, dossier: dict[str, Any]) -> None:
        self._nodes: dict[str, Any] = {}
        self._url_nodes: dict[str, list[Any]] = {}
        self._index_obj(dossier, "")
        facts = dossier.get("facts") if isinstance(dossier.get("facts"), dict) else {}
        for key, rows in facts.items():
            if not isinstance(rows, list):
                continue
            for offset, row in enumerate(rows):
                pointer = f"facts.{key}[{offset}]"
                self._nodes[pointer] = row
                self._nodes[f"/facts/{key}/{offset}"] = row
                if isinstance(row, dict):
                    url = str(row.get("sourceUrl") or "").strip()
                    if url:
                        self._url_nodes.setdefault(url, []).append(row)
        social = dossier.get("social") if isinstance(dossier.get("social"), dict) else {}
        if isinstance(social.get("bio"), dict):
            self._nodes["social.bio"] = social["bio"]
            self._nodes["/social/bio"] = social["bio"]
            url = str(social["bio"].get("sourceUrl") or "").strip()
            if url:
                self._url_nodes.setdefault(url, []).append(social["bio"])
        for offset, item in enumerate(social.get("highlights") or []):
            self._nodes[f"social.highlights[{offset}]"] = item
            self._nodes[f"/social/highlights/{offset}"] = item
            if isinstance(item, dict):
                url = str(item.get("sourceUrl") or "").strip()
                if url:
                    self._url_nodes.setdefault(url, []).append(item)
        for offset, item in enumerate(social.get("posts") or []):
            self._nodes[f"social.posts[{offset}]"] = item
            self._nodes[f"/social/posts/{offset}"] = item
            if isinstance(item, dict):
                url = str(item.get("url") or item.get("sourceUrl") or "").strip()
                if url:
                    self._url_nodes.setdefault(url, []).append(item)

    def _index_obj(self, value: Any, pointer: str) -> None:
        if pointer:
            self._nodes[pointer] = value
        if isinstance(value, dict):
            url = str(value.get("sourceUrl") or "").strip()
            if url:
                self._url_nodes.setdefault(url, []).append(value)
            for key, child in value.items():
                nxt = f"{pointer}/{key}" if pointer else f"/{key}"
                self._index_obj(child, nxt)
        elif isinstance(value, list):
            for offset, child in enumerate(value):
                nxt = f"{pointer}/{offset}" if pointer else f"/{offset}"
                self._index_obj(child, nxt)

    def resolve(self, ref: str) -> bool:
        return bool(self.nodes(ref))

    def nodes(self, ref: str) -> list[Any]:
        text = str(ref or "").strip()
        if not text:
            return []
        if text in self._nodes:
            return [self._nodes[text]]
        if text in self._url_nodes:
            return list(self._url_nodes[text])
        dotted = _dotted_to_pointer(text)
        if dotted in self._nodes:
            return [self._nodes[dotted]]
        return []

    def blob(self, ref: str) -> str:
        return json.dumps(self.nodes(ref), ensure_ascii=False, default=str)


def _dotted_to_pointer(path: str) -> str:
    if path.startswith("/"):
        return path
    parts: list[str] = []
    for chunk in path.split("."):
        match = re.match(r"^([^\[\]]+)(?:\[(\d+)\])?$", chunk)
        if match is None:
            parts.append(chunk)
            continue
        parts.append(match.group(1))
        if match.group(2) is not None:
            parts.append(match.group(2))
    return "/" + "/".join(parts)
