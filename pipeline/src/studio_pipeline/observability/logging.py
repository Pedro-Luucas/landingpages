"""JSONL logging stub. Do not log secrets, tokens, or full captions."""

from __future__ import annotations

from typing import Any


def log_event(event: str, **fields: Any) -> None:
    """Structured JSONL lands with observability work; M1 callers must not crash."""
    _ = (event, fields)
