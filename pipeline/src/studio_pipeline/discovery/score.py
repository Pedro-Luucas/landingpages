"""Score social profile candidates against studio identity fields."""

from __future__ import annotations

from dataclasses import dataclass, field

from studio_pipeline.discovery.normalize import digits_only, slugify

STOPWORDS = frozenset(
    {
        "estudio",
        "studio",
        "the",
        "de",
        "da",
        "do",
        "dos",
        "das",
        "e",
        "em",
        "rec",
        "recording",
        "music",
        "musica",
        "som",
        "audio",
        "lab",
        "wave",
        "ensaio",
        "ensaios",
        "gravacao",
        "gravacoes",
        "oficial",
        "official",
        "page",
        "pagina",
    }
)

SOURCE_PRIOR = {
    "direct_url": 0.70,
    "source_field": 0.70,
    "intermediate": 0.52,
    "web_search": 0.18,
}

NAME_WEIGHT = 0.35
CITY_WEIGHT = 0.12
ADDRESS_WEIGHT = 0.08
PHONE_WEIGHT = 0.08
DOMAIN_WEIGHT = 0.07


@dataclass
class ScoreContext:
    name: str
    city: str = ""
    state: str = ""
    address: str = ""
    phone: str = ""
    website_host: str = ""


@dataclass
class ScoredCandidate:
    platform: str
    url: str
    handle: str
    score: float
    rationale: list[str] = field(default_factory=list)
    method: str = ""
    source_url: str = ""
    title: str = ""
    snippet: str = ""
    first_party: bool = False


def _tokens(text: str) -> set[str]:
    parts = [part for part in slugify(text).split("-") if part]
    meaningful = {part for part in parts if part not in STOPWORDS and len(part) >= 3}
    if meaningful:
        return meaningful
    return {part for part in parts if len(part) >= 2}


def _haystack(*parts: str) -> str:
    return slugify(" ".join(part for part in parts if part))


def name_overlap(studio_name: str, handle: str, extra: str = "") -> float:
    tokens = _tokens(studio_name)
    if not tokens:
        return 0.0
    blob = _haystack(handle.replace(".", " "), extra)
    compact_handle = slugify(handle.replace(".", " "))
    matched = 0
    for token in tokens:
        if token in blob or token in compact_handle:
            matched += 1
    return matched / len(tokens)


def city_overlap(city: str, handle: str, extra: str = "") -> float:
    if not city:
        return 0.0
    token = slugify(city)
    if len(token) < 3:
        return 0.0
    blob = _haystack(handle.replace(".", " "), extra)
    if token in blob:
        return 1.0
    extra_lower = extra.lower()
    if city.lower() in extra_lower:
        return 1.0
    return 0.0


def address_overlap(address: str, extra: str = "") -> float:
    tokens = {token for token in _tokens(address) if len(token) >= 4}
    if not tokens:
        return 0.0
    blob = _haystack(extra)
    matched = sum(1 for token in tokens if token in blob)
    if matched >= 2:
        return 1.0
    if matched == 1:
        return 0.5
    return 0.0


def phone_overlap(phone: str, extra: str = "") -> float:
    want = digits_only(phone)
    if len(want) < 8:
        return 0.0
    found = digits_only(extra)
    if want[-8:] in found:
        return 1.0
    return 0.0


def domain_overlap(website_host: str, handle: str) -> float:
    host = website_host.lower()
    if not host or "instagram.com" in host or "facebook.com" in host or "fb.com" in host:
        return 0.0
    if host.startswith("www."):
        host = host[4:]
    label = host.split(".")[0]
    if len(label) < 4:
        return 0.0
    compact = slugify(handle.replace(".", " "))
    if label in compact or compact in label:
        return 1.0
    return 0.0


def score_candidate(
    *,
    platform: str,
    url: str,
    handle: str,
    method: str,
    source_url: str,
    title: str = "",
    snippet: str = "",
    first_party: bool = False,
    context: ScoreContext,
) -> ScoredCandidate:
    extra = " ".join(part for part in (title, snippet, handle, url) if part)
    name = name_overlap(context.name, handle, extra)
    city = city_overlap(context.city, handle, extra)
    address = address_overlap(context.address, extra)
    phone = phone_overlap(context.phone, extra)
    domain = domain_overlap(context.website_host, handle)
    prior = SOURCE_PRIOR.get(method, 0.18)
    if first_party and method == "intermediate":
        prior = max(prior, 0.52)
    score = min(
        1.0,
        prior
        + NAME_WEIGHT * name
        + CITY_WEIGHT * city
        + ADDRESS_WEIGHT * address
        + PHONE_WEIGHT * phone
        + DOMAIN_WEIGHT * domain,
    )
    rationale = [
        f"prior({method})={prior:.2f}",
        f"name={name:.2f}",
        f"city={city:.2f}",
        f"address={address:.2f}",
        f"phone={phone:.2f}",
        f"domain={domain:.2f}",
        f"score={score:.2f}",
    ]
    return ScoredCandidate(
        platform=platform,
        url=url,
        handle=handle,
        score=round(score, 4),
        rationale=rationale,
        method=method,
        source_url=source_url,
        title=title,
        snippet=snippet,
        first_party=first_party,
    )
