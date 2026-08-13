"""CLI --help must exit 0 for the module and every M0 subcommand."""

from __future__ import annotations

import subprocess
import sys

import pytest

from studio_pipeline.cli import build_parser, main
from studio_pipeline.config import load_config

SUBCOMMANDS = ("import", "queue", "run", "retry", "validate", "doctor")


def _run_module(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "studio_pipeline", *args],
        capture_output=True,
        text=True,
        check=False,
    )


def test_module_help_exits_zero() -> None:
    result = _run_module("--help")
    assert result.returncode == 0
    assert "usage" in result.stdout.lower()
    for name in SUBCOMMANDS:
        assert name in result.stdout


def test_no_args_prints_help_and_exits_zero() -> None:
    result = _run_module()
    assert result.returncode == 0
    assert "usage" in result.stdout.lower()


@pytest.mark.parametrize("command", SUBCOMMANDS)
def test_subcommand_help_exits_zero(command: str) -> None:
    result = _run_module(command, "--help")
    assert result.returncode == 0
    assert "usage" in result.stdout.lower()


@pytest.mark.parametrize("command", SUBCOMMANDS)
def test_parser_subcommand_help_exits_zero(command: str) -> None:
    parser = build_parser()
    with pytest.raises(SystemExit) as excinfo:
        parser.parse_args([command, "--help"])
    assert excinfo.value.code == 0


def test_validate_missing_studio_exits_nonzero(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    code = main(["validate", "--studio-id", "demo"])
    assert code == 1


def test_doctor_and_validate_succeed_for_m0_fixtures() -> None:
    assert main(["doctor"]) == 0
    assert main(["validate"]) == 0


def test_config_repr_does_not_log_secrets(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AI_API_KEY", "sk-secret-value")
    monkeypatch.setenv("SEARCH_API_KEY", "search-secret")
    monkeypatch.setenv("VERCEL_TOKEN", "vercel-secret")
    monkeypatch.setenv("DASHBOARD_SECRET", "dash-secret")
    text = repr(load_config())
    assert "sk-secret-value" not in text
    assert "search-secret" not in text
    assert "vercel-secret" not in text
    assert "dash-secret" not in text
    assert "ai_api_key='***'" in text
    assert "vercel_token='***'" in text
