"""Deterministic generation identity (plan §6.3 / §8 F)."""

from __future__ import annotations

import hashlib
import json
from typing import Any

PROMPT_VERSION = "m4.v1"
FAKE_MODEL = "fake-m4"


def collect_asset_paths(dossier: dict[str, Any] | None) -> list[str]:
    """Logo then selected media localPath values. Never invents paths."""
    if not isinstance(dossier, dict):
        return []
    media = dossier.get("media") if isinstance(dossier.get("media"), dict) else {}
    paths: list[str] = []
    seen: set[str] = set()

    def add(raw: object) -> None:
        if not isinstance(raw, dict):
            return
        path = str(raw.get("localPath") or "").strip()
        if not path or path in seen:
            return
        seen.add(path)
        paths.append(path)

    add(media.get("logo"))
    for item in media.get("selected") or []:
        add(item)
    return paths


def canonical_dumps(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )


def compute_input_hash(
    dossier: dict[str, Any],
    *,
    assets: list[str] | None = None,
    prompt_version: str = PROMPT_VERSION,
) -> str:
    """sha256 of canonical dossier + asset paths + promptVersion."""
    dossier_for_hash = {
        key: value
        for key, value in dossier.items()
        if key not in {"warnings", "completedAt"}
    }
    payload = {
        "assets": list(assets if assets is not None else collect_asset_paths(dossier)),
        "dossier": dossier_for_hash,
        "promptVersion": prompt_version,
    }
    return hashlib.sha256(canonical_dumps(payload).encode("utf-8")).hexdigest()


def generation_id_for(input_hash: str) -> str:
    digest = (input_hash or "").strip().lower()
    return f"gen-{digest}" if digest else "gen-unknown"
