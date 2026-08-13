"""Repo-root .env loading: stdlib parser, env wins, secrets stay redacted."""

from __future__ import annotations

from pathlib import Path

import pytest

from studio_pipeline.config import load_config, parse_dotenv


def test_parse_dotenv_quotes_and_comments(tmp_path: Path) -> None:
    path = tmp_path / ".env"
    path.write_text(
        "# comment\n"
        "LOG_LEVEL=debug\n"
        "export AI_API_KEY='from-file'\n"
        'DASHBOARD_SECRET="quoted"\n'
        'APP_BASE_URL="http://localhost:3000" # trailing comment\n'
        "DATA_DIR=./data # unquoted comment\n"
        'SEARCH_PROVIDER="hash#inside"\n'
        r'AI_MODEL="say \"hello\""' + "\n"
        "NOT A LINE\n",
        encoding="utf-8",
    )
    values = parse_dotenv(path)
    assert values["LOG_LEVEL"] == "debug"
    assert values["AI_API_KEY"] == "from-file"
    assert values["DASHBOARD_SECRET"] == "quoted"
    assert values["APP_BASE_URL"] == "http://localhost:3000"
    assert values["DATA_DIR"] == "./data"
    assert values["SEARCH_PROVIDER"] == "hash#inside"
    assert values["AI_MODEL"] == 'say "hello"'
    assert "NOT" not in values


def test_existing_env_wins_over_dotenv(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(
        "DATA_DIR=from-file\nLOG_LEVEL=debug\nAI_API_KEY=file-secret\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "from-env"))
    monkeypatch.delenv("AI_API_KEY", raising=False)
    monkeypatch.delenv("LOG_LEVEL", raising=False)
    config = load_config(dotenv_path=env_file)
    assert config.data_dir == (tmp_path / "from-env").resolve()
    assert config.log_level == "debug"
    assert config.ai_api_key == "file-secret"
    text = repr(config)
    assert "file-secret" not in text
    assert "ai_api_key='***'" in text
