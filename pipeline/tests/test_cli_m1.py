"""CLI import/queue/run/retry/doctor/validate against a temp DATA_DIR."""

from __future__ import annotations

from pathlib import Path

import pytest

from studio_pipeline.cli import main
from studio_pipeline.repositories.state import StateRepository
from studio_pipeline.repositories.studio import StudioRepository

FIXTURE = Path(__file__).parent / "fixtures" / "source_musica.json"


@pytest.fixture
def data_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("ASSETS_DIR", str(tmp_path / "public" / "studios"))
    monkeypatch.delenv("STUDIO_ID", raising=False)

    class _NoNetworkHttp:
        def __init__(self, *args: object, **kwargs: object) -> None:
            pass

        def get(self, url: str, timeout: float | None = None) -> object:
            from studio_pipeline.http.client import HttpResponse

            _ = timeout
            return HttpResponse(status=404, headers={}, text="", final_url=url)

    class _NoNetworkBinaryHttp:
        def __init__(self, *args: object, **kwargs: object) -> None:
            pass

        def get_bytes(self, url: str) -> tuple[int, dict[str, str], bytes, str]:
            raise AssertionError(f"CLI *.example path must not download media: {url}")

    monkeypatch.setattr("studio_pipeline.cli.StdlibHttpClient", _NoNetworkHttp)
    monkeypatch.setattr("studio_pipeline.orchestrator.StdlibHttpClient", _NoNetworkHttp)
    monkeypatch.setattr("studio_pipeline.cli.StdlibBinaryHttp", _NoNetworkBinaryHttp)
    monkeypatch.setattr("studio_pipeline.orchestrator.StdlibBinaryHttp", _NoNetworkBinaryHttp)
    return tmp_path


def test_cli_import_queue_run_retry_doctor_validate(data_env: Path) -> None:
    assert main(["import", "--input", str(FIXTURE)]) == 0
    studio_id = next(p.name for p in (data_env / "studios").iterdir() if p.is_dir())

    assert main(["queue", "--studio-id", studio_id]) == 0
    assert main(["queue", "--studio-id", studio_id]) == 0
    assert main(["run", "--studio-id", studio_id]) == 0

    studios = StudioRepository(data_env)
    state = StateRepository(data_env, studio_repo=studios)
    after_run = state.get_item(studio_id)
    assert after_run is not None
    assert after_run["status"] == "needs_social_review"
    state.transition(studio_id, "failed", actor="pipeline", reason="test")
    assert main(["retry", "--studio-id", studio_id]) == 0

    assert main(["validate", "--studio-id", studio_id]) == 0
    assert main(["doctor"]) == 0

    studio = studios.get_studio(studio_id)
    item = state.get_item(studio_id)
    assert studio is not None
    assert item is not None
    assert item["status"] == "queued"
    assert studio["pipelineStatus"] == "queued"


def test_cli_queue_accepts_rejected_then_noop_when_queued(data_env: Path) -> None:
    assert main(["import", "--input", str(FIXTURE)]) == 0
    studio_id = next(p.name for p in (data_env / "studios").iterdir() if p.is_dir())
    studios = StudioRepository(data_env)
    state = StateRepository(data_env, studio_repo=studios)
    item = state.get_item(studio_id)
    assert item is not None
    item["status"] = "rejected"
    state.save_item(item, expected_updated_at=str(item["updatedAt"]))

    assert main(["queue", "--studio-id", studio_id]) == 0
    queued = state.get_item(studio_id)
    assert queued is not None
    assert queued["status"] == "queued"
    assert main(["queue", "--studio-id", studio_id]) == 0
    again = state.get_item(studio_id)
    assert again is not None
    assert len(again["history"]) == len(queued["history"])


def test_cli_queue_rejects_failed_and_retry_rejects_rejected(
    data_env: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert main(["import", "--input", str(FIXTURE)]) == 0
    studio_id = next(p.name for p in (data_env / "studios").iterdir() if p.is_dir())
    studios = StudioRepository(data_env)
    state = StateRepository(data_env, studio_repo=studios)
    item = state.get_item(studio_id)
    assert item is not None
    item["status"] = "failed"
    state.save_item(item, expected_updated_at=str(item["updatedAt"]))

    assert main(["queue", "--studio-id", studio_id]) == 1
    err = capsys.readouterr().err
    assert "INPUT_INVALID" in err
    assert "imported or rejected" in err

    item = state.get_item(studio_id)
    assert item is not None
    item["status"] = "rejected"
    state.save_item(item, expected_updated_at=str(item["updatedAt"]))
    assert main(["retry", "--studio-id", studio_id]) == 1
    err = capsys.readouterr().err
    assert "INPUT_INVALID" in err
    assert "retry requires failed" in err


def test_cli_run_without_queue_fails(data_env: Path) -> None:
    assert main(["import", "--input", str(FIXTURE)]) == 0
    studio_id = next(p.name for p in (data_env / "studios").iterdir() if p.is_dir())
    assert main(["run", "--studio-id", studio_id]) == 1


def test_cli_import_missing_file(
    data_env: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert main(["import", "--input", str(data_env / "missing.json")]) == 1
    err = capsys.readouterr().err
    assert "INPUT_INVALID" in err
    assert "Traceback" not in err


def test_cli_errors_include_stable_codes(
    data_env: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    code = main(["queue", "--studio-id", "no-such-studio"])
    err = capsys.readouterr().err
    assert code == 1
    assert "INPUT_INVALID" in err
    assert "Traceback" not in err


def test_cli_redacts_secrets_in_error_text(
    data_env: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    secret = "sk-should-never-appear-in-cli"
    monkeypatch.setenv("AI_API_KEY", secret)
    code = main(["import", "--input", str(data_env / f"{secret}.json")])
    err = capsys.readouterr().err
    assert code == 1
    assert "INPUT_INVALID" in err
    assert secret not in err
    assert "***" in err
    assert "Traceback" not in err
