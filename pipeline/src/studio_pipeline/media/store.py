"""Write logo/images/manifest under assets_dir / studioId. Only delete *.tmp."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from studio_pipeline.config import repo_root
from studio_pipeline.errors import INPUT_INVALID, PipelineError


def safe_studio_id(studio_id: str) -> str:
    text = (studio_id or "").strip()
    if not text or Path(text).name != text or text in {".", ".."}:
        raise PipelineError(INPUT_INVALID, "studioId is not a safe path segment")
    return text


def studio_asset_dir(assets_dir: Path, studio_id: str) -> Path:
    return Path(assets_dir) / safe_studio_id(studio_id)


def cleanup_tmp_files(studio_dir: Path) -> None:
    """Delete leftover `*.tmp` files in this studio dir only."""
    if not studio_dir.is_dir():
        return
    for path in studio_dir.rglob("*.tmp"):
        if path.is_file():
            try:
                path.unlink()
            except OSError:
                pass


def dossier_local_path(assets_dir: Path, studio_id: str, relative: str) -> str:
    """Repo-relative posix path, e.g. public/studios/<id>/logo.jpg."""
    relative = str(relative).replace("\\", "/")
    assets_dir = Path(assets_dir)
    studio_id = safe_studio_id(studio_id)
    try:
        rel_dir = assets_dir.resolve().relative_to(repo_root().resolve())
        return (rel_dir / studio_id / relative).as_posix()
    except ValueError:
        pass
    parts = assets_dir.parts
    for index in range(len(parts) - 1):
        if parts[index] == "public" and parts[index + 1] == "studios":
            suffix = Path(*parts[index:]) / studio_id / relative
            return suffix.as_posix()
    if not assets_dir.is_absolute():
        cleaned = assets_dir.as_posix().lstrip("./")
        return f"{cleaned}/{studio_id}/{relative}".replace("//", "/")
    return f"{assets_dir.name}/{studio_id}/{relative}"


def atomic_write_bytes(path: Path, data: bytes) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_name(path.name + ".tmp")
    flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC
    if hasattr(os, "O_BINARY"):
        flags |= os.O_BINARY
    fd = os.open(tmp_path, flags)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_path, path)
    except Exception:
        try:
            tmp_path.unlink(missing_ok=True)
        except OSError:
            pass
        raise


def write_manifest(studio_dir: Path, payload: dict[str, Any]) -> None:
    studio_dir.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    atomic_write_bytes(studio_dir / "manifest.json", text.encode("utf-8"))
