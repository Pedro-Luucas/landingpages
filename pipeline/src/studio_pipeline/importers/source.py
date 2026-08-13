"""Import and normalize the original studios JSON (plan §8 etapa A)."""

from __future__ import annotations

import json
from copy import deepcopy
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from studio_pipeline.clock import utc_now_iso
from studio_pipeline.errors import INPUT_INVALID, PipelineError
from studio_pipeline.importers.normalize import (
    allocate_studio_id,
    identity_key,
    normalize_latitude,
    normalize_longitude,
    normalize_phone,
    normalize_score,
    normalize_website,
    optional_string,
    preferred_studio_id,
    slugify,
    source_hash,
)
from studio_pipeline.repositories.state import StateRepository
from studio_pipeline.repositories.studio import StudioRepository


@dataclass
class ImportReport:
    imported: list[str] = field(default_factory=list)
    updated: list[str] = field(default_factory=list)
    unchanged: list[str] = field(default_factory=list)
    duplicates: list[str] = field(default_factory=list)
    invalid: list[str] = field(default_factory=list)

    def format(self) -> str:
        lines = [
            f"imported: {len(self.imported)}",
            f"updated: {len(self.updated)}",
            f"unchanged: {len(self.unchanged)}",
            f"duplicates: {len(self.duplicates)}",
            f"invalid: {len(self.invalid)}",
        ]
        if self.imported:
            lines.append("  new: " + ", ".join(self.imported))
        if self.updated:
            lines.append("  updated ids: " + ", ".join(self.updated))
        if self.unchanged:
            lines.append("  unchanged ids: " + ", ".join(self.unchanged))
        if self.duplicates:
            lines.append("  duplicates: " + ", ".join(self.duplicates))
        if self.invalid:
            lines.append("  invalid: " + "; ".join(self.invalid))
        return "\n".join(lines)


def _load_source(input_path: Path) -> Any:
    if not input_path.is_file():
        raise PipelineError(INPUT_INVALID, f"input file not found: {input_path}")
    try:
        with input_path.open(encoding="utf-8-sig") as handle:
            return json.load(handle)
    except json.JSONDecodeError as exc:
        raise PipelineError(INPUT_INVALID, f"invalid JSON: {exc}") from exc
    except OSError as exc:
        raise PipelineError(INPUT_INVALID, f"cannot read input: {exc}") from exc


def extract_records(data: Any) -> list[Any]:
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        musica = data.get("musica")
        if isinstance(musica, list):
            return musica
        raise PipelineError(
            INPUT_INVALID,
            "source JSON must be an array or an object with a 'musica' array",
        )
    raise PipelineError(INPUT_INVALID, "source JSON must be an object or array")


def _build_studio(
    *,
    studio_id: str,
    source_id: str,
    record: dict[str, Any],
    source_file: str,
    digest: str,
    pipeline_status: str,
    imported_at: str,
    updated_at: str,
) -> dict[str, Any]:
    name = optional_string(record.get("title"))
    assert name is not None
    city = optional_string(record.get("cidade"))
    state = optional_string(record.get("estado"))
    address = optional_string(record.get("address"))
    studio_type = optional_string(record.get("type"))
    phone = normalize_phone(record.get("phoneNumber"))
    website = normalize_website(record.get("website"))
    latitude = normalize_latitude(record.get("latitude"))
    longitude = normalize_longitude(record.get("longitude"))
    score = normalize_score(record.get("score_comercial"))

    location: dict[str, Any] = {}
    if city:
        location["city"] = city
    if state:
        location["state"] = state
    if address:
        location["address"] = address
    if latitude is not None:
        location["latitude"] = latitude
    if longitude is not None:
        location["longitude"] = longitude

    contacts: dict[str, Any] = {}
    if phone:
        contacts["phone"] = phone
    if website:
        contacts["website"] = website

    studio: dict[str, Any] = {
        "schemaVersion": 1,
        "studioId": studio_id,
        "sourceId": source_id,
        "name": name,
        "slug": slugify(name) or studio_id,
        "location": location,
        "contacts": contacts,
        "source": {
            "importedAt": imported_at,
            "sourceFile": source_file,
            "sourceHash": digest,
            "originalRecord": deepcopy(record),
        },
        "pipelineStatus": pipeline_status,
        "updatedAt": updated_at,
    }
    if studio_type:
        studio["type"] = studio_type
    if score is not None:
        studio["commercialScore"] = score
    return studio


_ENRICHED_CONTACT_KEYS = ("instagram", "facebook")


def _preserve_enrichment(current: dict[str, Any], studio: dict[str, Any]) -> dict[str, Any]:
    """Keep social handles added after import; source JSON has no such fields."""
    prev = current.get("contacts")
    if not isinstance(prev, dict):
        return studio
    contacts = dict(studio.get("contacts") or {})
    for key in _ENRICHED_CONTACT_KEYS:
        value = prev.get(key)
        if key not in contacts and isinstance(value, str) and value:
            contacts[key] = value
    studio["contacts"] = contacts
    return studio


def _new_pipeline_item(studio_id: str, actor: str, now: str) -> dict[str, Any]:
    return {
        "studioId": studio_id,
        "status": "imported",
        "attempt": 0,
        "warnings": [],
        "history": [
            {
                "to": "imported",
                "at": now,
                "actor": actor,
                "reason": "Imported from source JSON.",
            }
        ],
        "createdAt": now,
        "updatedAt": now,
    }


def import_source(
    input_path: str | Path,
    *,
    data_dir: str | Path,
    actor: str = "cli",
) -> ImportReport:
    path = Path(input_path)
    studios = StudioRepository(data_dir)
    state = StateRepository(data_dir, studio_repo=studios)
    report = ImportReport()

    records = extract_records(_load_source(path))
    source_file = path.name

    existing = studios.iter_studios()
    by_source_id: dict[str, dict[str, Any]] = {}
    used_ids: set[str] = set()
    for studio in existing:
        studio_id = str(studio.get("studioId") or "")
        if studio_id:
            used_ids.add(studio_id)
        sid = studio.get("sourceId")
        if isinstance(sid, str) and sid:
            by_source_id[sid] = studio

    seen_source_ids: set[str] = set()
    seen_hashes: set[str] = set()

    for index, raw in enumerate(records):
        if not isinstance(raw, dict):
            report.invalid.append(f"index {index}: record is not an object")
            continue
        name = optional_string(raw.get("title"))
        if name is None:
            report.invalid.append(f"index {index}: missing title")
            continue

        digest = source_hash(raw)
        source_id = identity_key(raw)
        if source_id in seen_source_ids or digest in seen_hashes:
            report.duplicates.append(source_id)
            continue
        seen_source_ids.add(source_id)
        seen_hashes.add(digest)

        now = utc_now_iso()
        city = optional_string(raw.get("cidade"))
        region = optional_string(raw.get("estado"))
        preferred = preferred_studio_id(name, city, region)

        current = by_source_id.get(source_id)
        if current is not None:
            studio_id = str(current["studioId"])
            previous_hash = (current.get("source") or {}).get("sourceHash")
            if previous_hash == digest:
                report.unchanged.append(studio_id)
                continue
            imported_at = (current.get("source") or {}).get("importedAt") or now
            pipeline_status = str(
                current.get("pipelineStatus")
                or (state.get_item(studio_id) or {}).get("status")
                or "imported"
            )
            studio = _build_studio(
                studio_id=studio_id,
                source_id=source_id,
                record=raw,
                source_file=source_file,
                digest=digest,
                pipeline_status=pipeline_status,
                imported_at=imported_at,
                updated_at=now,
            )
            studio = _preserve_enrichment(current, studio)
            studios.save_studio(studio)
            report.updated.append(studio_id)
            continue

        studio_id = allocate_studio_id(preferred, used_ids, source_id)
        used_ids.add(studio_id)
        studio = _build_studio(
            studio_id=studio_id,
            source_id=source_id,
            record=raw,
            source_file=source_file,
            digest=digest,
            pipeline_status="imported",
            imported_at=now,
            updated_at=now,
        )
        studios.save_studio(studio)
        by_source_id[source_id] = studio
        if state.get_item(studio_id) is None:
            state.save_item(_new_pipeline_item(studio_id, actor, now))
        report.imported.append(studio_id)

    return report
