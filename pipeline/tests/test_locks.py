"""Per-studio lock files: exclusive acquire, expired takeover."""

from __future__ import annotations

import os
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest

from studio_pipeline.clock import parse_iso
from studio_pipeline.errors import LOCKED, LOCK_EXPIRED, PipelineError
from studio_pipeline.persistence import atomic_write_json
from studio_pipeline.repositories.state import StateRepository

WORKER = Path(__file__).parent / "lock_worker.py"


def _write_expired_lock(tmp_path: Path, studio_id: str, owner: str = "stale") -> Path:
    path = tmp_path / "state" / "locks" / f"{studio_id}.lock"
    path.parent.mkdir(parents=True, exist_ok=True)
    past = "2000-01-01T00:00:00Z"
    atomic_write_json(
        path,
        {
            "owner": owner,
            "lockedAt": past,
            "expiresAt": past,
            "studioId": studio_id,
        },
        backup=False,
    )
    return path


def test_two_processes_cannot_acquire_same_lock(tmp_path: Path) -> None:
    studio_id = "aurora-sound-lab-cur-pr"
    holder = subprocess.Popen(
        [
            sys.executable,
            str(WORKER),
            str(tmp_path),
            studio_id,
            "worker-a",
            "30",
            "20",
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    assert holder.stdout is not None
    line = holder.stdout.readline().strip()
    if line != "ACQUIRED":
        holder.kill()
        stderr = holder.stderr.read() if holder.stderr else ""
        pytest.fail(f"holder failed to acquire: {line!r} stderr={stderr!r}")

    challenger = subprocess.run(
        [
            sys.executable,
            str(WORKER),
            str(tmp_path),
            studio_id,
            "worker-b",
            "30",
            "0",
        ],
        capture_output=True,
        text=True,
        check=False,
        timeout=15,
    )
    holder.terminate()
    holder.wait(timeout=10)
    assert LOCKED in challenger.stdout
    assert challenger.returncode != 0


def test_same_process_second_owner_is_locked(tmp_path: Path) -> None:
    repo = StateRepository(tmp_path)
    repo.acquire_lock("norte-wave-studio-cur-pr", "owner-a", ttl_seconds=30)
    with pytest.raises(PipelineError) as excinfo:
        repo.acquire_lock("norte-wave-studio-cur-pr", "owner-b", ttl_seconds=30)
    assert excinfo.value.code == LOCKED
    repo.release_lock("norte-wave-studio-cur-pr", "owner-a")
    repo.acquire_lock("norte-wave-studio-cur-pr", "owner-b", ttl_seconds=30)
    repo.release_lock("norte-wave-studio-cur-pr", "owner-b")


def test_same_owner_refresh_extends_ttl(tmp_path: Path) -> None:
    repo = StateRepository(tmp_path)
    first = repo.acquire_lock("norte-wave-studio-cur-pr", "owner-a", ttl_seconds=30)
    second = repo.acquire_lock("norte-wave-studio-cur-pr", "owner-a", ttl_seconds=120)
    assert second["owner"] == "owner-a"
    assert parse_iso(second["expiresAt"]) > parse_iso(first["expiresAt"])
    repo.release_lock("norte-wave-studio-cur-pr", "owner-a")


def test_expired_lock_can_be_taken_over(tmp_path: Path) -> None:
    repo = StateRepository(tmp_path)
    studio_id = "estudio-lagoa-azul-sp-sp"
    _write_expired_lock(tmp_path, studio_id)
    repo.acquire_lock(studio_id, "fresh", ttl_seconds=30)
    data = tmp_path / "state" / "locks" / f"{studio_id}.lock"
    assert data.is_file()
    leftovers = list((tmp_path / "state" / "locks").glob("*.stale-*"))
    assert leftovers == []
    repo.release_lock(studio_id, "fresh")


def test_expired_takeover_renames_live_path(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = StateRepository(tmp_path)
    studio_id = "estudio-lagoa-azul-sp-sp"
    lock_path = _write_expired_lock(tmp_path, studio_id)
    renamed: list[tuple[str, str]] = []
    real_rename = os.rename

    def tracking_rename(src: os.PathLike[str] | str, dst: os.PathLike[str] | str, *args: object, **kwargs: object) -> None:
        renamed.append((os.fspath(src), os.fspath(dst)))
        real_rename(src, dst, *args, **kwargs)

    monkeypatch.setattr("studio_pipeline.repositories.state.os.rename", tracking_rename)
    repo.acquire_lock(studio_id, "fresh", ttl_seconds=30)
    assert any(
        Path(src) == lock_path and ".stale-" in dst for src, dst in renamed
    ), renamed
    repo.release_lock(studio_id, "fresh")


def test_two_workers_racing_expired_takeover_only_one_succeeds(tmp_path: Path) -> None:
    studio_id = "estudio-lagoa-azul-sp-sp"
    _write_expired_lock(tmp_path, studio_id)
    gate = tmp_path / "start-gate"
    workers: list[subprocess.Popen[str]] = []
    try:
        for owner in ("worker-a", "worker-b"):
            workers.append(
                subprocess.Popen(
                    [
                        sys.executable,
                        str(WORKER),
                        str(tmp_path),
                        studio_id,
                        owner,
                        "30",
                        "3",
                        str(gate),
                    ],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                )
            )
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline and not all(
            proc.poll() is None for proc in workers
        ):
            time.sleep(0.01)
        time.sleep(0.4)
        gate.write_text("go", encoding="utf-8")

        lines: list[str] = ["", ""]

        def _read(index: int) -> None:
            proc = workers[index]
            assert proc.stdout is not None
            lines[index] = proc.stdout.readline().strip()

        threads = [threading.Thread(target=_read, args=(i,)) for i in range(2)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=20)

        acquired = sum(1 for line in lines if line == "ACQUIRED")
        locked = sum(1 for line in lines if LOCKED in line)
        assert acquired == 1, f"expected one winner, got {lines!r}"
        assert locked == 1, f"expected one LOCKED, got {lines!r}"
    finally:
        for proc in workers:
            proc.terminate()
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=5)


def test_expired_lock_records_audit_when_item_exists(tmp_path: Path) -> None:
    repo = StateRepository(tmp_path)
    studio_id = "estudio-lagoa-azul-sp-sp"
    now = "2026-08-12T12:00:00Z"
    repo.save_item(
        {
            "studioId": studio_id,
            "status": "queued",
            "attempt": 0,
            "warnings": [],
            "history": [{"to": "queued", "at": now, "actor": "cli"}],
            "createdAt": now,
            "updatedAt": now,
        }
    )
    _write_expired_lock(tmp_path, studio_id)
    repo.acquire_lock(studio_id, "fresh", ttl_seconds=30)
    item = repo.get_item(studio_id)
    assert item is not None
    assert any(warning.get("code") == LOCK_EXPIRED for warning in item["warnings"])
    assert any(
        (entry.get("reason") or "").startswith(LOCK_EXPIRED) for entry in item["history"]
    )
    assert item.get("lockedBy") == "fresh"
    repo.release_lock(studio_id, "fresh")
