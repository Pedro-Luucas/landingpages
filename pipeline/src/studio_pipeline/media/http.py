"""Injected binary HTTP for media downloads. Tests must never open a socket."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Protocol


class BinaryHttp(Protocol):
    def get_bytes(self, url: str) -> tuple[int, Mapping[str, str], bytes, str]:
        """status, headers, body, final_url"""
        ...
