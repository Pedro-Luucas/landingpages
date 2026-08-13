"""Studio JSON repository (studio.json and sibling documents)."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from studio_pipeline.errors import INPUT_INVALID, SCHEMA_INVALID, STATE_CONFLICT, PipelineError
from studio_pipeline.persistence import atomic_write_json, read_json
from studio_pipeline.validation.schema_store import load_schema

STUDIO_ID_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


def require_studio_id(studio_id: str) -> str:
    if not studio_id or not STUDIO_ID_RE.fullmatch(studio_id):
        raise PipelineError(INPUT_INVALID, f"invalid studioId: {studio_id!r}")
    return studio_id


class StudioRepository:
    """Read/write per-studio JSON under `data/studios/<studioId>/`."""

    def __init__(self, data_dir: str | Path) -> None:
        self.data_dir = Path(data_dir)

    def studios_dir(self) -> Path:
        return self.data_dir / "studios"

    def studio_dir(self, studio_id: str) -> Path:
        return self.studios_dir() / require_studio_id(studio_id)

    def _path(self, studio_id: str, filename: str) -> Path:
        return self.studio_dir(studio_id) / filename

    def _get(self, studio_id: str, filename: str) -> dict[str, Any] | None:
        path = self._path(studio_id, filename)
        if not path.is_file():
            return None
        document = read_json(path)
        if not isinstance(document, dict):
            raise PipelineError(
                SCHEMA_INVALID,
                f"{path.name} for {studio_id} is not a JSON object",
            )
        return document

    def _save(
        self,
        studio_id: str,
        filename: str,
        document: dict[str, Any],
        *,
        schema_kind: str | None,
        expected_updated_at: str | None = None,
    ) -> None:
        require_studio_id(studio_id)
        doc_id = document.get("studioId")
        if doc_id is not None and doc_id != studio_id:
            raise PipelineError(
                INPUT_INVALID,
                f"{filename} studioId {doc_id!r} does not match {studio_id!r}",
            )
        path = self._path(studio_id, filename)
        if expected_updated_at is not None and path.is_file():
            current = read_json(path)
            current_ts = current.get("updatedAt") if isinstance(current, dict) else None
            if current_ts != expected_updated_at:
                raise PipelineError(
                    STATE_CONFLICT,
                    f"{filename} updatedAt mismatch "
                    f"(expected {expected_updated_at!r}, found {current_ts!r})",
                )
        schema = load_schema(schema_kind) if schema_kind else None
        atomic_write_json(path, document, schema=schema)

    def get_studio(self, studio_id: str) -> dict[str, Any] | None:
        return self._get(studio_id, "studio.json")

    def save_studio(
        self,
        studio: dict[str, Any],
        *,
        expected_updated_at: str | None = None,
    ) -> None:
        studio_id = require_studio_id(str(studio.get("studioId") or ""))
        self._save(
            studio_id,
            "studio.json",
            studio,
            schema_kind="studio",
            expected_updated_at=expected_updated_at,
        )

    def get_dossier(self, studio_id: str) -> dict[str, Any] | None:
        return self._get(studio_id, "dossier.json")

    def save_dossier(self, dossier: dict[str, Any]) -> None:
        studio_id = require_studio_id(str(dossier.get("studioId") or ""))
        self._save(studio_id, "dossier.json", dossier, schema_kind="dossier")

    def get_generated(self, studio_id: str) -> dict[str, Any] | None:
        return self._get(studio_id, "generated.json")

    def save_generated(self, generated: dict[str, Any]) -> None:
        studio_id = require_studio_id(str(generated.get("studioId") or ""))
        self._save(studio_id, "generated.json", generated, schema_kind="generated")

    def get_approved(self, studio_id: str) -> dict[str, Any] | None:
        return self._get(studio_id, "approved.json")

    def save_approved(self, approved: dict[str, Any]) -> None:
        studio_id = require_studio_id(str(approved.get("studioId") or ""))
        # approved.schema.json lands in M6; persist atomically without that schema.
        self._save(studio_id, "approved.json", approved, schema_kind=None)

    def get_deployment(self, studio_id: str) -> dict[str, Any] | None:
        return self._get(studio_id, "deployment.json")

    def save_deployment(self, deployment: dict[str, Any]) -> None:
        studio_id = require_studio_id(str(deployment.get("studioId") or ""))
        self._save(studio_id, "deployment.json", deployment, schema_kind="deployment")

    def get(self, studio_id: str) -> dict[str, Any] | None:
        return self.get_studio(studio_id)

    def save(self, studio: dict[str, Any]) -> None:
        self.save_studio(studio)

    def iter_studios(self) -> list[dict[str, Any]]:
        root = self.studios_dir()
        if not root.is_dir():
            return []
        found: list[dict[str, Any]] = []
        for path in sorted(root.glob("*/studio.json")):
            document = read_json(path)
            if isinstance(document, dict):
                found.append(document)
        return found
