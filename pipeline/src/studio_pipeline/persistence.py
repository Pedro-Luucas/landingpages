"""Atomic JSON writes: temp file, fsync, os.replace (plan §12)."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from jsonschema.exceptions import ValidationError

from studio_pipeline.errors import SCHEMA_INVALID, PipelineError
from studio_pipeline.validation.schemas import validate_instance


def atomic_write_text(path: Path, text: str, *, backup: bool = True) -> None:
    """Write `text` to `path` via a sibling `*.tmp`, then `os.replace`.

    A leftover `*.tmp` is never treated as the live document. If `path`
    already exists, a short `*.bak` copy of the last valid file is kept.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_name(path.name + ".tmp")

    flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC
    if hasattr(os, "O_BINARY"):
        flags |= os.O_BINARY

    fd = os.open(tmp_path, flags)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
    except Exception:
        try:
            tmp_path.unlink(missing_ok=True)
        except OSError:
            pass
        raise

    if backup and path.is_file():
        bak_path = path.with_name(path.name + ".bak")
        bak_tmp = bak_path.with_name(bak_path.name + ".tmp")
        data = path.read_bytes()
        bak_flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC
        if hasattr(os, "O_BINARY"):
            bak_flags |= os.O_BINARY
        bak_fd = os.open(bak_tmp, bak_flags)
        try:
            with os.fdopen(bak_fd, "wb") as handle:
                handle.write(data)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(bak_tmp, bak_path)
        except Exception:
            try:
                bak_tmp.unlink(missing_ok=True)
            except OSError:
                pass
            raise

    os.replace(tmp_path, path)


def atomic_write_json(
    path: Path,
    document: Any,
    *,
    schema: dict[str, Any] | None = None,
    backup: bool = True,
) -> None:
    if schema is not None:
        try:
            validate_instance(schema, document)
        except ValidationError as exc:
            raise PipelineError(
                SCHEMA_INVALID,
                f"{Path(path).name}: {exc.message}",
            ) from exc
    text = json.dumps(document, ensure_ascii=False, indent=2) + "\n"
    atomic_write_text(path, text, backup=backup)


def read_json(path: Path) -> Any:
    with Path(path).open(encoding="utf-8") as handle:
        return json.load(handle)
