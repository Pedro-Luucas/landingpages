"""Pipeline tests default to the fake AI provider so pytest never hits a live API."""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _default_ai_provider_fake(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AI_PROVIDER", "fake")
