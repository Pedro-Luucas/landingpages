"""Subprocess helper: acquire a per-studio lock and hold it."""

from __future__ import annotations

import sys
import time
from pathlib import Path


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    data_dir, studio_id, owner = args[0], args[1], args[2]
    ttl_seconds = int(args[3])
    hold_seconds = float(args[4])
    start_gate = Path(args[5]) if len(args) > 5 else None
    from studio_pipeline.errors import PipelineError
    from studio_pipeline.repositories.state import StateRepository

    repo = StateRepository(data_dir)
    if start_gate is not None:
        deadline = time.monotonic() + 15
        while not start_gate.exists():
            if time.monotonic() > deadline:
                print("TIMEOUT", flush=True)
                return 2
            time.sleep(0.001)
    try:
        repo.acquire_lock(studio_id, owner, ttl_seconds=ttl_seconds)
    except PipelineError as exc:
        print(exc.code, flush=True)
        return 1
    print("ACQUIRED", flush=True)
    time.sleep(hold_seconds)
    repo.release_lock(studio_id, owner)
    print("RELEASED", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
