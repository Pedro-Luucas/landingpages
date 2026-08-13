"""Pipeline state repository (pipeline.json and per-studio locks)."""

from __future__ import annotations

import errno
import json
import os
import time
from copy import deepcopy
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from studio_pipeline.clock import format_iso, parse_iso, utc_now, utc_now_iso
from studio_pipeline.errors import (
    INPUT_INVALID,
    LOCKED,
    LOCK_EXPIRED,
    SCHEMA_INVALID,
    STATE_CONFLICT,
    PipelineError,
)
from studio_pipeline.persistence import atomic_write_json, read_json
from studio_pipeline.repositories.studio import StudioRepository, require_studio_id
from studio_pipeline.state_machine import (
    IDEMPOTENT_TRANSITIONS,
    assert_transition,
)
from studio_pipeline.validation.schema_store import load_schema

DEFAULT_LOCK_TTL_SECONDS = 900
LOCK_ACQUIRE_ATTEMPTS = 4


def empty_pipeline() -> dict[str, Any]:
    return {
        "schemaVersion": 1,
        "updatedAt": utc_now_iso(),
        "items": [],
    }


class StateRepository:
    """Read/write queue state, transitions, and exclusive per-studio locks."""

    def __init__(
        self,
        data_dir: str | Path,
        *,
        studio_repo: StudioRepository | None = None,
    ) -> None:
        self.data_dir = Path(data_dir)
        self.state_dir = self.data_dir / "state"
        self.locks_dir = self.state_dir / "locks"
        self.pipeline_path = self.state_dir / "pipeline.json"
        self._studios = studio_repo or StudioRepository(data_dir)

    def get_pipeline(self) -> dict[str, Any]:
        if not self.pipeline_path.is_file():
            return empty_pipeline()
        document = read_json(self.pipeline_path)
        if not isinstance(document, dict):
            raise PipelineError(SCHEMA_INVALID, "pipeline.json is not a JSON object")
        return document

    def save_pipeline(
        self,
        pipeline: dict[str, Any],
        *,
        expected_updated_at: str | None = None,
    ) -> None:
        if self.pipeline_path.is_file():
            current = read_json(self.pipeline_path)
            current_ts = current.get("updatedAt") if isinstance(current, dict) else None
            if expected_updated_at is not None and current_ts != expected_updated_at:
                raise PipelineError(
                    STATE_CONFLICT,
                    "pipeline.json updatedAt mismatch "
                    f"(expected {expected_updated_at!r}, found {current_ts!r})",
                )
        now = utc_now_iso()
        document = deepcopy(pipeline)
        document["schemaVersion"] = 1
        document["updatedAt"] = now
        if "items" not in document:
            document["items"] = []
        atomic_write_json(
            self.pipeline_path,
            document,
            schema=load_schema("pipeline"),
        )

    def get_item(self, studio_id: str) -> dict[str, Any] | None:
        require_studio_id(studio_id)
        pipeline = self.get_pipeline()
        return deepcopy(self._find_item(pipeline, studio_id))

    def save_item(
        self,
        item: dict[str, Any],
        *,
        expected_updated_at: str | None = None,
    ) -> None:
        studio_id = require_studio_id(str(item.get("studioId") or ""))
        pipeline = self.get_pipeline()
        existing = self._find_item(pipeline, studio_id)
        file_exists = self.pipeline_path.is_file()
        if expected_updated_at is not None and file_exists:
            if existing is not None:
                if existing.get("updatedAt") != expected_updated_at:
                    raise PipelineError(
                        STATE_CONFLICT,
                        f"pipeline item {studio_id} updatedAt mismatch "
                        f"(expected {expected_updated_at!r}, "
                        f"found {existing.get('updatedAt')!r})",
                    )
            elif pipeline.get("updatedAt") != expected_updated_at:
                raise PipelineError(
                    STATE_CONFLICT,
                    "pipeline.json updatedAt mismatch "
                    f"(expected {expected_updated_at!r}, "
                    f"found {pipeline.get('updatedAt')!r})",
                )

        now = utc_now_iso()
        stored = deepcopy(item)
        stored["studioId"] = studio_id
        stored["updatedAt"] = now
        items = list(pipeline.get("items") or [])
        replaced = False
        for index, current in enumerate(items):
            if current.get("studioId") == studio_id:
                items[index] = stored
                replaced = True
                break
        if not replaced:
            items.append(stored)
        pipeline["items"] = items
        pipeline["schemaVersion"] = 1
        pipeline["updatedAt"] = now
        atomic_write_json(
            self.pipeline_path,
            pipeline,
            schema=load_schema("pipeline"),
        )

    def transition(
        self,
        studio_id: str,
        to: str,
        actor: str,
        reason: str | None = None,
    ) -> dict[str, Any]:
        require_studio_id(studio_id)
        if not actor or not str(actor).strip():
            raise PipelineError(INPUT_INVALID, "transition actor is required")
        item = self.get_item(studio_id)
        if item is None:
            raise PipelineError(
                INPUT_INVALID,
                f"no pipeline item for studio {studio_id}",
            )
        frm = str(item.get("status") or "")
        if (frm, to) in IDEMPOTENT_TRANSITIONS:
            return item
        assert_transition(frm, to, actor)

        now = utc_now_iso()
        etag = item.get("updatedAt")
        history = list(item.get("history") or [])
        entry: dict[str, Any] = {
            "from": frm,
            "to": to,
            "at": now,
            "actor": actor,
        }
        if reason:
            entry["reason"] = reason
        history.append(entry)
        item["history"] = history
        item["status"] = to
        item["updatedAt"] = now
        if frm == "failed" and to == "queued":
            item["attempt"] = int(item.get("attempt") or 0) + 1
            item.pop("error", None)

        self.save_item(item, expected_updated_at=etag if isinstance(etag, str) else None)

        studio = self._studios.get_studio(studio_id)
        if studio is not None:
            studio = deepcopy(studio)
            studio_etag = studio.get("updatedAt")
            studio["pipelineStatus"] = to
            studio["updatedAt"] = now
            self._studios.save_studio(
                studio,
                expected_updated_at=studio_etag if isinstance(studio_etag, str) else None,
            )
        return item

    def acquire_lock(
        self,
        studio_id: str,
        owner: str,
        ttl_seconds: int = DEFAULT_LOCK_TTL_SECONDS,
    ) -> dict[str, Any]:
        require_studio_id(studio_id)
        if not owner or not str(owner).strip():
            raise PipelineError(INPUT_INVALID, "lock owner is required")
        if ttl_seconds <= 0:
            raise PipelineError(INPUT_INVALID, "ttl_seconds must be positive")

        self.locks_dir.mkdir(parents=True, exist_ok=True)
        path = self._lock_path(studio_id)

        for _attempt in range(LOCK_ACQUIRE_ATTEMPTS):
            now = utc_now()
            payload = {
                "owner": owner,
                "lockedAt": format_iso(now),
                "expiresAt": format_iso(now + timedelta(seconds=ttl_seconds)),
                "studioId": studio_id,
            }

            takeover_existing: dict[str, Any] | None = None
            taking_over = False
            stale_path: Path | None = None
            if path.exists():
                existing = self._read_lock(path)
                if existing is not None and not self._lock_expired(existing, now):
                    if existing.get("owner") == owner:
                        self._write_lock_replace(path, payload)
                        self._touch_item_lock(studio_id, payload)
                        return payload
                    raise PipelineError(
                        LOCKED,
                        f"studio {studio_id} is locked by {existing.get('owner')!r}",
                    )
                taking_over = True
                takeover_existing = existing
                stale_path = path.with_name(
                    f"{path.name}.stale-{os.getpid()}-{time.time_ns()}"
                )
                try:
                    os.rename(path, stale_path)
                except FileNotFoundError:
                    continue
                except OSError as exc:
                    if exc.errno == errno.ENOENT:
                        continue
                    raise PipelineError(
                        LOCKED,
                        f"studio {studio_id} is locked "
                        "(could not take over expired lock)",
                    ) from exc

            try:
                self._create_lock_exclusive(path, payload)
            except FileExistsError:
                continue
            except OSError as exc:
                if exc.errno == errno.EEXIST:
                    continue
                raise

            if taking_over:
                self._record_lock_expired(studio_id, takeover_existing, owner, now)
            if stale_path is not None:
                try:
                    stale_path.unlink(missing_ok=True)
                except OSError:
                    pass
            self._touch_item_lock(studio_id, payload)
            return payload

        raise PipelineError(LOCKED, f"studio {studio_id} is locked")

    def release_lock(self, studio_id: str, owner: str) -> None:
        require_studio_id(studio_id)
        path = self._lock_path(studio_id)
        if not path.is_file():
            self._clear_item_lock(studio_id, owner)
            return
        existing = self._read_lock(path)
        if existing is not None and existing.get("owner") != owner:
            raise PipelineError(
                LOCKED,
                f"studio {studio_id} is locked by {existing.get('owner')!r}",
            )
        path.unlink(missing_ok=True)
        self._clear_item_lock(studio_id, owner)

    def list_locks(self) -> list[dict[str, Any]]:
        if not self.locks_dir.is_dir():
            return []
        locks: list[dict[str, Any]] = []
        now = utc_now()
        for path in sorted(self.locks_dir.glob("*.lock")):
            data = self._read_lock(path)
            if data is None:
                locks.append(
                    {
                        "studioId": path.stem,
                        "path": str(path),
                        "invalid": True,
                        "expired": True,
                    }
                )
                continue
            data = dict(data)
            data["path"] = str(path)
            data["expired"] = self._lock_expired(data, now)
            data["invalid"] = False
            locks.append(data)
        return locks

    def _lock_path(self, studio_id: str) -> Path:
        return self.locks_dir / f"{studio_id}.lock"

    def _read_lock(self, path: Path) -> dict[str, Any] | None:
        try:
            document = read_json(path)
        except (OSError, json.JSONDecodeError, UnicodeError):
            return None
        if not isinstance(document, dict):
            return None
        return document

    def _lock_expired(self, lock: dict[str, Any], now: datetime) -> bool:
        expires = lock.get("expiresAt")
        if not isinstance(expires, str):
            return True
        try:
            return parse_iso(expires) <= now
        except ValueError:
            return True

    def _create_lock_exclusive(self, path: Path, payload: dict[str, Any]) -> None:
        flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY
        if hasattr(os, "O_BINARY"):
            flags |= os.O_BINARY
        text = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
        fd = os.open(path, flags)
        try:
            with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
                handle.write(text)
                handle.flush()
                os.fsync(handle.fileno())
        except Exception:
            try:
                path.unlink(missing_ok=True)
            except OSError:
                pass
            raise

    def _write_lock_replace(self, path: Path, payload: dict[str, Any]) -> None:
        atomic_write_json(path, payload, schema=None, backup=False)

    def _record_lock_expired(
        self,
        studio_id: str,
        existing: dict[str, Any] | None,
        new_owner: str,
        now: datetime,
    ) -> None:
        item = self.get_item(studio_id)
        if item is None:
            return
        etag = item.get("updatedAt")
        at = format_iso(now)
        previous = (existing or {}).get("owner")
        warnings = list(item.get("warnings") or [])
        warnings.append(
            {
                "code": LOCK_EXPIRED,
                "message": (
                    f"Took over expired lock from {previous!r}"
                    if previous
                    else "Took over expired lock"
                ),
                "stage": "lock",
                "at": at,
                "retryable": False,
            }
        )
        history = list(item.get("history") or [])
        status = str(item.get("status") or "queued")
        history.append(
            {
                "from": status,
                "to": status,
                "at": at,
                "actor": new_owner,
                "reason": f"{LOCK_EXPIRED}: previous lock expired",
            }
        )
        item["warnings"] = warnings
        item["history"] = history
        self.save_item(item, expected_updated_at=etag if isinstance(etag, str) else None)

    def _touch_item_lock(self, studio_id: str, payload: dict[str, Any]) -> None:
        item = self.get_item(studio_id)
        if item is None:
            return
        etag = item.get("updatedAt")
        item["lockedBy"] = payload["owner"]
        item["lockExpiresAt"] = payload["expiresAt"]
        self.save_item(item, expected_updated_at=etag if isinstance(etag, str) else None)

    def _clear_item_lock(self, studio_id: str, owner: str) -> None:
        item = self.get_item(studio_id)
        if item is None:
            return
        if item.get("lockedBy") not in {None, owner}:
            return
        etag = item.get("updatedAt")
        item.pop("lockedBy", None)
        item.pop("lockExpiresAt", None)
        self.save_item(item, expected_updated_at=etag if isinstance(etag, str) else None)

    @staticmethod
    def _find_item(pipeline: dict[str, Any], studio_id: str) -> dict[str, Any] | None:
        for item in pipeline.get("items") or []:
            if isinstance(item, dict) and item.get("studioId") == studio_id:
                return item
        return None
