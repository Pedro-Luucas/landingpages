"""Offline AI stub. Schema-valid GeneratedSite, no network (plan §8 F / §17 M4)."""

from __future__ import annotations

import re
from typing import Any, Mapping

from studio_pipeline.ai.base import BrandAnalysis, GeneratedSite, MediaSelection
from studio_pipeline.ai.input_hash import (
    FAKE_MODEL,
    PROMPT_VERSION,
    collect_asset_paths,
    compute_input_hash,
    generation_id_for,
)
from studio_pipeline.clock import utc_now_iso

_PROVIDER = "fake"

_SECTION_IDS = (
    "hero",
    "about",
    "gallery",
    "equipment",
    "pricing",
    "hours",
    "reviews",
    "contact",
    "map",
)

_RESTRICTED = re.compile(
    r"R\$\s*\d[\d.]{0,12}(?:,\d{2})?"
    r"|\b\d{1,6},\d{2}\s*(?:reais)?\b"
    r"|\b\d{1,6}\s*reais\b"
    r"|\b[0-5][.,]\d\s*(?:estrelas|stars)?\b"
    r"|\b[0-5]\s*/\s*5\b"
    r"|\b\d{1,2}:\d{2}\s*(?:[–\-]|às|as|até|ate)\s*\d{1,2}:\d{2}\b"
    r"|\b\d{1,2}\s*h\s*(?:[–\-]|às|as|até|ate)\s*\d{1,2}\s*h\b",
    re.IGNORECASE,
)

_CITY_IN_ADDRESS = re.compile(
    r"(.+?)\s*-\s*[A-Za-z]{2}\s*$",
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

_DAY_ORDER = (
    "monday",
    "tuesday",
    "wednesday",
    "thursday",
    "friday",
    "saturday",
    "sunday",
)

_DAY_PT = {
    "monday": "Segunda",
    "tuesday": "Terça",
    "wednesday": "Quarta",
    "thursday": "Quinta",
    "friday": "Sexta",
    "saturday": "Sábado",
    "sunday": "Domingo",
}

_BRAND_BY_TEMPLATE: dict[str, dict[str, Any]] = {
    "minimal": {
        "colors": {
            "background": "#F6F1E8",
            "surface": "#FFFFFF",
            "primary": "#1F3A5F",
            "secondary": "#C45C26",
            "text": "#1A1A1A",
            "mutedText": "#5C6570",
        },
        "fontHeading": "IBM Plex Serif",
        "fontBody": "IBM Plex Sans",
        "radius": "small",
        "mood": ["quiet", "daylight"],
    },
    "editorial": {
        "colors": {
            "background": "#0F1419",
            "surface": "#1A2330",
            "primary": "#E8A54B",
            "secondary": "#4A7C9B",
            "text": "#F4F1EA",
            "mutedText": "#9AA4B2",
        },
        "fontHeading": "Fraunces",
        "fontBody": "Source Sans 3",
        "radius": "medium",
        "mood": ["nocturnal", "focused", "warm"],
        "imageTreatment": "soft-grain-shadow",
    },
    "immersive": {
        "colors": {
            "background": "#0B0B0F",
            "surface": "#16161E",
            "primary": "#FF5A36",
            "secondary": "#7C5CFF",
            "text": "#F7F4EE",
            "mutedText": "#A39E96",
        },
        "fontHeading": "Outfit",
        "fontBody": "Source Sans 3",
        "radius": "large",
        "mood": ["cinematic", "dense", "loud"],
        "imageTreatment": "cinematic-shadow",
    },
    "bold": {
        "colors": {
            "background": "#111111",
            "surface": "#1C1C1C",
            "primary": "#FFE14D",
            "secondary": "#FF2E63",
            "text": "#FAFAFA",
            "mutedText": "#B5B5B5",
        },
        "fontHeading": "Archivo Black",
        "fontBody": "Inter",
        "radius": "none",
        "mood": ["graphic", "high-contrast"],
    },
}


def _facts(dossier: Mapping[str, Any]) -> dict[str, Any]:
    raw = dossier.get("facts")
    return raw if isinstance(raw, dict) else {}


def _social(dossier: Mapping[str, Any]) -> dict[str, Any]:
    raw = dossier.get("social")
    return raw if isinstance(raw, dict) else {}


def _rows(facts: Mapping[str, Any], key: str) -> list[dict[str, Any]]:
    items = facts.get(key) or []
    if not isinstance(items, list):
        return []
    return [item for item in items if isinstance(item, dict)]


def _best_row(rows: list[dict[str, Any]]) -> tuple[dict[str, Any], int] | None:
    ranked: list[tuple[float, int, dict[str, Any]]] = []
    for index, row in enumerate(rows):
        try:
            confidence = float(row.get("confidence") or 0)
        except (TypeError, ValueError):
            confidence = 0.0
        ranked.append((confidence, index, row))
    if not ranked:
        return None
    ranked.sort(key=lambda item: item[0], reverse=True)
    _, index, row = ranked[0]
    return row, index


def _selected_count(dossier: Mapping[str, Any], asset_paths: list[str]) -> int:
    media = dossier.get("media") if isinstance(dossier.get("media"), dict) else {}
    selected = media.get("selected") or []
    if isinstance(selected, list) and selected:
        return len([item for item in selected if isinstance(item, dict)])
    return len(asset_paths)


def choose_template(dossier: Mapping[str, Any], asset_paths: list[str]) -> str:
    count = _selected_count(dossier, asset_paths)
    if count <= 2:
        return "minimal"
    if count >= 6:
        return "immersive"
    return "editorial" if count % 2 else "bold"


def _complete_branding(brand: Mapping[str, Any] | None, template_id: str) -> dict[str, Any]:
    defaults = _BRAND_BY_TEMPLATE.get(template_id) or _BRAND_BY_TEMPLATE["minimal"]
    incoming = brand if isinstance(brand, Mapping) else {}
    colors_in = incoming.get("colors") if isinstance(incoming.get("colors"), dict) else {}
    colors = dict(defaults["colors"])
    for key in ("background", "surface", "primary", "secondary", "text", "mutedText"):
        value = colors_in.get(key)
        if isinstance(value, str) and value.strip():
            colors[key] = value.strip()
    font_heading = incoming.get("fontHeading")
    font_body = incoming.get("fontBody")
    radius = incoming.get("radius")
    mood = incoming.get("mood")
    branding: dict[str, Any] = {
        "colors": colors,
        "fontHeading": (
            font_heading.strip()
            if isinstance(font_heading, str) and font_heading.strip()
            else defaults["fontHeading"]
        ),
        "fontBody": (
            font_body.strip()
            if isinstance(font_body, str) and font_body.strip()
            else defaults["fontBody"]
        ),
        "radius": (
            radius
            if radius in {"none", "small", "medium", "large"}
            else defaults["radius"]
        ),
        "mood": (
            [str(item) for item in mood if str(item).strip()]
            if isinstance(mood, list) and mood
            else list(defaults["mood"])
        ),
    }
    treatment = incoming.get("imageTreatment")
    if isinstance(treatment, str) and treatment.strip():
        branding["imageTreatment"] = treatment.strip()
    elif defaults.get("imageTreatment"):
        branding["imageTreatment"] = defaults["imageTreatment"]
    return branding


def _display_name(studio_id: str) -> str:
    parts = [part for part in str(studio_id or "").split("-") if part]
    if len(parts) > 1 and len(parts[-1]) <= 3 and parts[-1].isalpha():
        parts = parts[:-1]
    if not parts:
        return "Estúdio"
    return " ".join(part.capitalize() for part in parts)


def _evidence_text(item: object) -> str:
    if isinstance(item, dict) and "value" in item:
        item = item.get("value")
    if isinstance(item, str):
        return item.strip()
    return ""


def _strip_restricted(text: str) -> str:
    cleaned = _RESTRICTED.sub(" ", text)
    return re.sub(r"\s+", " ", cleaned).strip(" ,;.-")


def _bio_text(dossier: Mapping[str, Any]) -> str:
    return _evidence_text(_social(dossier).get("bio"))


def _highlight_texts(dossier: Mapping[str, Any]) -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    for index, item in enumerate(_social(dossier).get("highlights") or []):
        if not isinstance(item, dict):
            continue
        value = item.get("value")
        chunks: list[str] = []
        if isinstance(value, dict):
            for key in ("title", "text"):
                raw = value.get(key)
                if isinstance(raw, str) and raw.strip():
                    chunks.append(raw.strip())
        elif isinstance(value, str) and value.strip():
            chunks.append(value.strip())
        text = _strip_restricted(" ".join(chunks))
        if text:
            out.append((text, f"social.highlights[{index}]"))
    return out


def _caption_texts(dossier: Mapping[str, Any], *, limit: int = 30) -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    for index, post in enumerate(_social(dossier).get("posts") or []):
        if len(out) >= limit:
            break
        if not isinstance(post, dict):
            continue
        caption = post.get("caption")
        if isinstance(caption, str) and caption.strip():
            text = _strip_restricted(caption)
            if text:
                out.append((text, f"social.posts[{index}]"))
    return out


def _city_from_map(facts: Mapping[str, Any]) -> tuple[str | None, str | None]:
    rows = _rows(facts, "map")
    best = _best_row(rows)
    if best is None:
        return None, None
    row, index = best
    value = row.get("value")
    address = ""
    if isinstance(value, dict):
        address = str(value.get("address") or "").strip()
    elif isinstance(value, str):
        address = value.strip()
    if not address:
        return None, None
    parts = [part.strip() for part in address.split(",") if part.strip()]
    if not parts:
        return None, None
    last = parts[-1]
    match = _CITY_IN_ADDRESS.match(last)
    city = match.group(1).strip() if match else last.split("-")[0].strip()
    if city.isdigit():
        return None, None
    return city, f"facts.map[{index}]"


def _map_address(facts: Mapping[str, Any]) -> tuple[str | None, str | None]:
    rows = _rows(facts, "map")
    best = _best_row(rows)
    if best is None:
        return None, None
    row, index = best
    value = row.get("value")
    address = ""
    if isinstance(value, dict):
        address = str(value.get("address") or "").strip()
    elif isinstance(value, str):
        address = value.strip()
    if not address:
        return None, None
    return address, f"facts.map[{index}]"


def _claim(path: str, *refs: str) -> dict[str, Any]:
    evidence = [ref for ref in refs if ref]
    return {"path": path, "evidenceRefs": evidence}


def _paths_from_media(selected_media: Mapping[str, Any] | None, dossier: Mapping[str, Any]) -> list[str]:
    paths: list[str] = []
    seen: set[str] = set()

    def add(path: object) -> None:
        text = str(path or "").strip()
        if not text or text in seen:
            return
        seen.add(text)
        paths.append(text)

    media = dossier.get("media") if isinstance(dossier.get("media"), dict) else {}
    logo = media.get("logo")
    if isinstance(logo, dict):
        add(logo.get("localPath"))
    selected = []
    if isinstance(selected_media, Mapping):
        selected = list(selected_media.get("selected") or [])
    if not selected:
        selected = list(media.get("selected") or [])
    for item in selected:
        if isinstance(item, str):
            add(item)
        elif isinstance(item, dict):
            add(item.get("localPath") or item.get("path"))
    if not paths:
        for path in collect_asset_paths(dict(dossier)):
            add(path)
    return paths


def _equipment_items(facts: Mapping[str, Any]) -> tuple[list[str], str | None]:
    rows = _rows(facts, "equipment")
    best = _best_row(rows)
    if best is None:
        return [], None
    row, index = best
    value = row.get("value")
    items: list[str] = []
    if isinstance(value, list):
        items = [str(item).strip() for item in value if str(item).strip()]
    elif isinstance(value, str) and value.strip():
        items = [value.strip()]
    return items, f"facts.equipment[{index}]" if items else None


def _price_items(facts: Mapping[str, Any]) -> tuple[list[dict[str, str]], str | None]:
    rows = _rows(facts, "prices")
    best = _best_row(rows)
    if best is None:
        return [], None
    row, index = best
    value = row.get("value")
    items: list[dict[str, str]] = []
    if isinstance(value, list):
        for item in value:
            if not isinstance(item, dict):
                continue
            label = str(item.get("label") or "").strip()
            amount = str(item.get("amountText") or item.get("value") or "").strip()
            if not label or not amount:
                continue
            payload = {"label": label, "value": amount}
            note = str(item.get("conditions") or item.get("note") or "").strip()
            if note:
                payload["note"] = note
            items.append(payload)
    return items, f"facts.prices[{index}]" if items else None


def _canon_day(raw: object) -> str | None:
    text = str(raw or "").strip().lower()
    if not text:
        return None
    return _DAY_CANON.get(text) or _DAY_CANON.get(text.replace("feira", "").strip(" -"))


def _format_intervals(intervals: list[Any]) -> str:
    parts = [str(item).strip().replace("-", "–") for item in intervals if str(item).strip()]
    if not parts:
        return "Fechado"
    return ", ".join(parts)


def _hours_items(facts: Mapping[str, Any]) -> tuple[list[dict[str, str]], str | None]:
    rows = _rows(facts, "openingHours")
    best = _best_row(rows)
    if best is None:
        return [], None
    row, index = best
    value = row.get("value")
    by_day: dict[str, str] = {}
    if isinstance(value, list):
        for item in value:
            if not isinstance(item, dict):
                continue
            day = _canon_day(item.get("day"))
            if day is None:
                continue
            intervals = item.get("intervals")
            if not isinstance(intervals, list):
                raw_value = str(item.get("value") or "").strip()
                if raw_value:
                    by_day[day] = raw_value
            else:
                by_day[day] = _format_intervals(intervals)
    if not by_day:
        return [], None
    ordered = [(day, by_day[day]) for day in _DAY_ORDER if day in by_day]
    groups: list[dict[str, Any]] = []
    for day, value_text in ordered:
        if groups and groups[-1]["value"] == value_text:
            groups[-1]["days"].append(day)
        else:
            groups.append({"days": [day], "value": value_text})
    items: list[dict[str, str]] = []
    for group in groups:
        days: list[str] = group["days"]
        if len(days) == 1:
            label = _DAY_PT[days[0]]
        elif len(days) == 2:
            label = f"{_DAY_PT[days[0]]} e {_DAY_PT[days[1]]}"
        else:
            label = f"{_DAY_PT[days[0]]} a {_DAY_PT[days[-1]]}"
        items.append({"day": label, "value": group["value"]})
    return items, f"facts.openingHours[{index}]"


def _reviews_copy(facts: Mapping[str, Any]) -> tuple[dict[str, Any] | None, str | None]:
    rows = _rows(facts, "googleReviews")
    best = _best_row(rows)
    if best is None:
        return None, None
    row, index = best
    value = row.get("value")
    payload: dict[str, Any] = {"title": "Quem já gravou aqui"}
    if isinstance(value, dict):
        rating = value.get("rating")
        if isinstance(rating, (int, float)) and 0 <= float(rating) <= 5:
            payload["rating"] = float(rating)
        count = value.get("count")
        if isinstance(count, int) and count >= 0:
            payload["count"] = count
        elif isinstance(count, float) and count >= 0 and count == int(count):
            payload["count"] = int(count)
        excerpts = value.get("excerpts")
        if isinstance(excerpts, list):
            cleaned = [str(item).strip() for item in excerpts if str(item).strip()]
            if cleaned:
                payload["excerpts"] = cleaned
    elif isinstance(value, (int, float)) and 0 <= float(value) <= 5:
        payload["rating"] = float(value)
    if set(payload.keys()) == {"title"}:
        return None, None
    return payload, f"facts.googleReviews[{index}]"


def _about_body(dossier: Mapping[str, Any]) -> tuple[str, list[str]]:
    parts: list[str] = []
    refs: list[str] = []
    bio = _strip_restricted(_bio_text(dossier))
    if bio:
        parts.append(bio)
        refs.append("social.bio")
    for text, ref in _highlight_texts(dossier):
        if text and text not in parts:
            parts.append(text)
            refs.append(ref)
    facts = _facts(dossier)
    desc_rows = _rows(facts, "description")
    best = _best_row(desc_rows)
    if best is not None:
        row, index = best
        text = _strip_restricted(_evidence_text(row))
        if text and text not in parts:
            parts.append(text)
            refs.append(f"facts.description[{index}]")
    for text, ref in _caption_texts(dossier)[:3]:
        if text and text not in parts:
            parts.append(text)
            refs.append(ref)
            if len(parts) >= 4:
                break
    body = " ".join(parts).strip()
    if len(body) > 800:
        body = body[:797].rsplit(" ", 1)[0] + "."
    return body, refs


class FakeProvider:
    """Deterministic, evidence-bound copy. No network."""

    def analyze_brand(
        self,
        dossier: dict[str, Any],
        asset_paths: list[str],
    ) -> BrandAnalysis:
        template_id = choose_template(dossier, asset_paths)
        branding = _complete_branding({}, template_id)
        result: BrandAnalysis = {
            "colors": branding["colors"],
            "fontHeading": branding["fontHeading"],
            "fontBody": branding["fontBody"],
            "radius": branding["radius"],
            "mood": list(branding["mood"]),
        }
        if branding.get("imageTreatment"):
            result["imageTreatment"] = branding["imageTreatment"]
        return result

    def select_media(
        self,
        dossier: dict[str, Any],
        candidates: list[Any],
    ) -> MediaSelection:
        media = dossier.get("media") if isinstance(dossier.get("media"), dict) else {}
        existing = [
            item
            for item in (media.get("selected") or [])
            if isinstance(item, dict) and str(item.get("localPath") or "").strip()
        ]
        if existing:
            rejected = [
                item
                for item in (media.get("candidates") or [])
                if isinstance(item, dict)
            ]
            return {"selected": existing, "rejected": rejected, "warnings": []}
        selected: list[Any] = []
        for item in candidates:
            if not isinstance(item, dict):
                continue
            if not str(item.get("localPath") or "").strip():
                continue
            selected.append(item)
            if len(selected) >= 10:
                break
        rejected = [item for item in candidates if item not in selected]
        return {"selected": selected, "rejected": rejected, "warnings": []}

    def generate_site(
        self,
        dossier: dict[str, Any],
        brand: BrandAnalysis,
        selected_media: MediaSelection,
    ) -> GeneratedSite:
        studio_id = str(dossier.get("studioId") or "").strip()
        asset_paths = _paths_from_media(selected_media, dossier)
        template_id = choose_template(dossier, asset_paths)
        branding = _complete_branding(brand, template_id)
        facts = _facts(dossier)
        claims: list[dict[str, Any]] = []
        warnings: list[str] = []
        copy: dict[str, Any] = {}
        enabled = {
            "hero": True,
            "about": False,
            "gallery": bool(asset_paths),
            "equipment": False,
            "pricing": False,
            "hours": False,
            "reviews": False,
            "contact": True,
            "map": False,
        }

        name = _display_name(studio_id)
        city, city_ref = _city_from_map(facts)
        hero: dict[str, Any] = {
            "title": name,
            "primaryCta": "Pedir horário",
        }
        if city:
            hero["eyebrow"] = f"Estúdio em {city}"
            if city_ref:
                claims.append(_claim("copy.hero.eyebrow", city_ref))
        about_body, about_refs = _about_body(dossier)
        subtitle_source = _strip_restricted(_bio_text(dossier))
        subtitle_ref = "social.bio" if subtitle_source else None
        if not subtitle_source:
            desc_rows = _rows(facts, "description")
            best = _best_row(desc_rows)
            if best is not None:
                subtitle_source = _strip_restricted(_evidence_text(best[0]))
                subtitle_ref = f"facts.description[{best[1]}]"
        if subtitle_source:
            hero["subtitle"] = subtitle_source
            if subtitle_ref:
                claims.append(_claim("copy.hero.subtitle", subtitle_ref))
        copy["hero"] = hero

        if about_body:
            copy["about"] = {"title": "Sobre", "body": about_body}
            enabled["about"] = True
            if about_refs:
                claims.append(_claim("copy.about.body", *about_refs))

        equipment, equipment_ref = _equipment_items(facts)
        if equipment and equipment_ref:
            copy["equipment"] = {
                "title": "O que está na sala",
                "intro": "Lista publicada nas fontes coletadas do estúdio.",
                "items": equipment,
            }
            enabled["equipment"] = True
            claims.append(_claim("copy.equipment.items", equipment_ref))
            claims.append(_claim("copy.equipment.intro", equipment_ref))
        else:
            warnings.append("Equipment omitted because dossier.facts.equipment is empty.")

        prices, price_ref = _price_items(facts)
        if prices and price_ref:
            copy["pricing"] = {"title": "Sessões", "items": prices}
            enabled["pricing"] = True
            claims.append(_claim("copy.pricing.items", price_ref))
        else:
            warnings.append("Pricing omitted because dossier.facts.prices is empty.")

        hours, hours_ref = _hours_items(facts)
        if hours and hours_ref:
            copy["hours"] = {"title": "Horários", "items": hours}
            enabled["hours"] = True
            claims.append(_claim("copy.hours.items", hours_ref))
        else:
            warnings.append("Hours omitted because dossier.facts.openingHours is empty.")

        reviews, reviews_ref = _reviews_copy(facts)
        if reviews and reviews_ref:
            copy["reviews"] = reviews
            enabled["reviews"] = True
            claims.append(_claim("copy.reviews", reviews_ref))
        else:
            warnings.append("Reviews omitted because dossier.facts.googleReviews is empty.")

        address, address_ref = _map_address(facts)
        contact: dict[str, Any] = {
            "title": "Contato",
            "cta": "Falar com o estúdio",
        }
        if address and address_ref:
            contact["body"] = address
            claims.append(_claim("copy.contact.body", address_ref))
            enabled["map"] = True
        else:
            warnings.append("Map omitted because dossier.facts.map is empty.")
        copy["contact"] = contact

        sections = [
            {"id": section_id, "enabled": enabled[section_id], "order": order}
            for order, section_id in enumerate(_SECTION_IDS)
        ]
        input_hash = compute_input_hash(
            dossier,
            assets=asset_paths,
            prompt_version=PROMPT_VERSION,
        )
        return {
            "schemaVersion": 1,
            "studioId": studio_id,
            "generationId": generation_id_for(input_hash),
            "inputHash": input_hash,
            "provider": _PROVIDER,
            "model": FAKE_MODEL,
            "promptVersion": PROMPT_VERSION,
            "templateId": template_id,
            "branding": branding,
            "copy": copy,
            "sections": sections,
            "assetPaths": asset_paths,
            "factualClaims": claims,
            "warnings": warnings,
            "createdAt": utc_now_iso(),
        }
