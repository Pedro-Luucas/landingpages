"""Atomic writes leave the last valid JSON in place if a .tmp is leftover."""

from __future__ import annotations

import os
from copy import deepcopy
from pathlib import Path

import pytest

from studio_pipeline.clock import utc_now_iso
from studio_pipeline.errors import SCHEMA_INVALID, PipelineError
from studio_pipeline.persistence import atomic_write_json, read_json
from studio_pipeline.repositories.studio import StudioRepository


def _studio(studio_id: str, name: str) -> dict:
    now = utc_now_iso()
    return {
        "schemaVersion": 1,
        "studioId": studio_id,
        "name": name,
        "slug": studio_id,
        "location": {"city": "Curitiba", "state": "Paraná"},
        "contacts": {},
        "source": {
            "importedAt": now,
            "sourceFile": "fixture.json",
            "sourceHash": "a" * 64,
            "originalRecord": {"title": name},
        },
        "pipelineStatus": "imported",
        "updatedAt": now,
    }


def test_interrupted_tmp_does_not_replace_valid_json(tmp_path: Path) -> None:
    repo = StudioRepository(tmp_path)
    original = _studio("aurora-sound-lab-cur-pr", "Aurora Sound Lab")
    repo.save_studio(original)

    target = tmp_path / "studios" / "aurora-sound-lab-cur-pr" / "studio.json"
    tmp_file = target.with_name(target.name + ".tmp")
    tmp_file.write_text("{this is not json", encoding="utf-8")

    loaded = repo.get_studio("aurora-sound-lab-cur-pr")
    assert loaded is not None
    assert loaded["name"] == "Aurora Sound Lab"
    assert read_json(target)["name"] == "Aurora Sound Lab"


def test_failed_replace_keeps_last_valid_json(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "doc.json"
    atomic_write_json(path, {"n": 1})
    real_replace = os.replace

    def boom(src: str | os.PathLike[str], dst: str | os.PathLike[str]) -> None:
        if Path(dst).name.endswith(".bak"):
            real_replace(src, dst)
            return
        raise OSError("simulated interrupt before replace")

    monkeypatch.setattr(os, "replace", boom)
    with pytest.raises(OSError, match="simulated interrupt"):
        atomic_write_json(path, {"n": 2})
    assert read_json(path) == {"n": 1}


def test_schema_invalid_does_not_replace_existing(tmp_path: Path) -> None:
    repo = StudioRepository(tmp_path)
    original = _studio("aurora-sound-lab-cur-pr", "Aurora Sound Lab")
    repo.save_studio(original)
    bad = deepcopy(original)
    bad["pipelineStatus"] = "not-a-real-status"
    with pytest.raises(PipelineError) as excinfo:
        repo.save_studio(bad)
    assert excinfo.value.code == SCHEMA_INVALID
    loaded = repo.get_studio("aurora-sound-lab-cur-pr")
    assert loaded is not None
    assert loaded["pipelineStatus"] == "imported"
    assert loaded["name"] == "Aurora Sound Lab"


def test_atomic_write_creates_backup(tmp_path: Path) -> None:
    path = tmp_path / "doc.json"
    atomic_write_json(path, {"n": 1}, backup=True)
    atomic_write_json(path, {"n": 2}, backup=True)
    assert read_json(path) == {"n": 2}
    assert read_json(path.with_name(path.name + ".bak")) == {"n": 1}
