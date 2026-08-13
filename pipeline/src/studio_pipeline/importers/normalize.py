"""Normalize source records: strings, phones, URLs, location, ids."""

from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from typing import Any

from jsonschema.validators import validator_for

_URI_SCHEMA = {"type": "string", "format": "uri"}
_URI_VALIDATOR = validator_for(_URI_SCHEMA)(
    _URI_SCHEMA,
    format_checker=validator_for(_URI_SCHEMA).FORMAT_CHECKER,
)

STUDIO_ID_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")

BRAZIL_UF: dict[str, str] = {
    "acre": "ac",
    "alagoas": "al",
    "amapa": "ap",
    "amazonas": "am",
    "bahia": "ba",
    "ceara": "ce",
    "distrito-federal": "df",
    "espirito-santo": "es",
    "goias": "go",
    "maranhao": "ma",
    "mato-grosso": "mt",
    "mato-grosso-do-sul": "ms",
    "minas-gerais": "mg",
    "para": "pa",
    "paraiba": "pb",
    "parana": "pr",
    "pernambuco": "pe",
    "piaui": "pi",
    "rio-de-janeiro": "rj",
    "rio-grande-do-norte": "rn",
    "rio-grande-do-sul": "rs",
    "rondonia": "ro",
    "roraima": "rr",
    "santa-catarina": "sc",
    "sao-paulo": "sp",
    "sergipe": "se",
    "tocantins": "to",
}


def slugify(value: str) -> str:
    """ASCII, lowercase, hyphenated slug. Accents stripped (São Paulo → sao-paulo)."""
    text = unicodedata.normalize("NFKD", value.strip().lower())
    ascii_text = "".join(ch for ch in text if not unicodedata.combining(ch))
    ascii_text = ascii_text.encode("ascii", "ignore").decode("ascii")
    ascii_text = re.sub(r"[^a-z0-9]+", "-", ascii_text)
    return ascii_text.strip("-")


def collapse_ws(value: str) -> str:
    return " ".join(value.split())


def optional_string(value: Any) -> str | None:
    if value is None:
        return None
    text = collapse_ws(str(value))
    return text or None


def is_uri(value: str) -> bool:
    try:
        _URI_VALIDATOR.validate(value)
    except Exception:
        return False
    return True


def normalize_website(value: Any) -> str | None:
    text = optional_string(value)
    if text is None:
        return None
    if not is_uri(text):
        return None
    scheme = text.split(":", 1)[0].lower()
    if scheme not in {"http", "https"}:
        return None
    rest = text.split(":", 1)[1]
    if not rest.startswith("//"):
        return None
    host = rest[2:].split("/", 1)[0].split("?", 1)[0].split("#", 1)[0]
    if not host:
        return None
    return text


def normalize_phone(value: Any) -> str | None:
    text = optional_string(value)
    if text is None:
        return None
    digits = re.sub(r"\D", "", text)
    if len(digits) < 8:
        return None
    return text


def as_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def normalize_latitude(value: Any) -> float | None:
    number = as_float(value)
    if number is None or number < -90 or number > 90:
        return None
    return number


def normalize_longitude(value: Any) -> float | None:
    number = as_float(value)
    if number is None or number < -180 or number > 180:
        return None
    return number


def normalize_score(value: Any) -> float | None:
    number = as_float(value)
    if number is None or number < 0 or number > 100:
        return None
    return number


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def source_hash(record: Any) -> str:
    payload = canonical_json(record).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def identity_key(record: dict[str, Any]) -> str:
    """Stable reimport key. Prefer city+state+address so a later name change
    still maps to the same studioId (ADR 0002). Title is only used when address
    is missing.
    """
    title = collapse_ws(str(record.get("title") or "")).lower()
    city = collapse_ws(str(record.get("cidade") or "")).lower()
    state = collapse_ws(str(record.get("estado") or "")).lower()
    address = collapse_ws(str(record.get("address") or "")).lower()
    parts = [city, state, address] if address else [title, city, state]
    raw = "|".join(parts).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()[:16]


def state_suffix(state: str | None) -> str:
    if not state:
        return ""
    slug = slugify(state)
    if not slug:
        return ""
    if len(slug) == 2:
        return slug
    if slug in BRAZIL_UF:
        return BRAZIL_UF[slug]
    return slug[:2]


def city_suffix(city: str | None) -> str:
    if not city:
        return ""
    slug = slugify(city)
    if not slug:
        return ""
    words = [part for part in slug.split("-") if part]
    if len(words) >= 2:
        return "".join(word[0] for word in words)[:4]
    return slug[:3]


def preferred_studio_id(name: str, city: str | None, state: str | None) -> str:
    name_slug = slugify(name) or "studio"
    if len(name_slug) > 48:
        name_slug = name_slug[:48].rstrip("-")
    suffix = "-".join(part for part in (city_suffix(city), state_suffix(state)) if part)
    studio_id = f"{name_slug}-{suffix}" if suffix else name_slug
    studio_id = slugify(studio_id)
    if not STUDIO_ID_RE.fullmatch(studio_id):
        studio_id = "studio"
    return studio_id


def allocate_studio_id(preferred: str, used: set[str], source_id: str) -> str:
    if preferred not in used:
        return preferred
    hashed = slugify(source_id[:8]) or "x"
    candidate = f"{preferred}-{hashed}"
    if candidate not in used:
        return candidate
    n = 2
    while True:
        candidate = f"{preferred}-{n}"
        if candidate not in used:
            return candidate
        n += 1
