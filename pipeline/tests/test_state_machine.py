"""State machine, optimistic concurrency, queue/retry history."""

from __future__ import annotations

from pathlib import Path

import pytest

from studio_pipeline.clock import utc_now_iso
from studio_pipeline.errors import INPUT_INVALID, STATE_CONFLICT, PipelineError
from studio_pipeline.importers.source import import_source
from studio_pipeline.repositories.state import StateRepository
from studio_pipeline.repositories.studio import StudioRepository
from studio_pipeline.state_machine import assert_transition

FIXTURE = Path(__file__).parent / "fixtures" / "source_musica.json"


def test_forbidden_transition_raises() -> None:
    with pytest.raises(PipelineError) as excinfo:
        assert_transition("imported", "deployed", "cli")
    assert excinfo.value.code == INPUT_INVALID
    assert "forbidden transition" in excinfo.value.message


def test_pipeline_cannot_auto_approve() -> None:
    with pytest.raises(PipelineError) as excinfo:
        assert_transition("ready_for_review", "approved", "pipeline")
    assert excinfo.value.code == INPUT_INVALID
    with pytest.raises(PipelineError):
        assert_transition("ready_for_review", "approved", "cli")
    assert_transition("ready_for_review", "approved", "dashboard")


def test_queue_then_retry_preserves_history(tmp_path: Path) -> None:
    report = import_source(FIXTURE, data_dir=tmp_path)
    studio_id = report.imported[0]
    studios = StudioRepository(tmp_path)
    state = StateRepository(tmp_path, studio_repo=studios)

    state.transition(studio_id, "queued", actor="cli", reason="enqueue")
    queued = state.get_item(studio_id)
    assert queued is not None
    assert queued["status"] == "queued"
    again = state.transition(studio_id, "queued", actor="cli")
    assert again["status"] == "queued"
    assert len(again["history"]) == len(queued["history"])

    etag = again["updatedAt"]
    again["lastSuccessfulStage"] = "discovering"
    state.save_item(again, expected_updated_at=etag)

    state.transition(studio_id, "failed", actor="pipeline", reason="simulated")
    retried = state.transition(studio_id, "queued", actor="cli", reason="retry")
    assert retried["status"] == "queued"
    assert retried["attempt"] >= 1
    assert retried.get("lastSuccessfulStage") == "discovering"
    assert len(retried["history"]) >= 2
    pairs = [(h.get("from"), h["to"]) for h in retried["history"] if "from" in h]
    assert ("imported", "queued") in pairs
    assert ("failed", "queued") in pairs

    studio = studios.get_studio(studio_id)
    assert studio is not None
    assert studio["pipelineStatus"] == "queued"


def test_forbidden_transition_via_repository(tmp_path: Path) -> None:
    report = import_source(FIXTURE, data_dir=tmp_path)
    state = StateRepository(tmp_path)
    with pytest.raises(PipelineError) as excinfo:
        state.transition(report.imported[0], "deployed", actor="cli")
    assert excinfo.value.code == INPUT_INVALID


def test_state_conflict_on_stale_etag(tmp_path: Path) -> None:
    report = import_source(FIXTURE, data_dir=tmp_path)
    studio_id = report.imported[0]
    state = StateRepository(tmp_path)
    item = state.get_item(studio_id)
    assert item is not None
    item["attempt"] = 9
    with pytest.raises(PipelineError) as excinfo:
        state.save_item(item, expected_updated_at="2000-01-01T00:00:00Z")
    assert excinfo.value.code == STATE_CONFLICT


def test_save_pipeline_conflict(tmp_path: Path) -> None:
    state = StateRepository(tmp_path)
    state.save_pipeline(
        {"schemaVersion": 1, "updatedAt": utc_now_iso(), "items": []}
    )
    with pytest.raises(PipelineError) as excinfo:
        state.save_pipeline(
            {"schemaVersion": 1, "updatedAt": utc_now_iso(), "items": []},
            expected_updated_at="1999-01-01T00:00:00Z",
        )
    assert excinfo.value.code == STATE_CONFLICT


def test_studio_save_conflict(tmp_path: Path) -> None:
    report = import_source(FIXTURE, data_dir=tmp_path)
    studios = StudioRepository(tmp_path)
    studio = studios.get_studio(report.imported[0])
    assert studio is not None
    with pytest.raises(PipelineError) as excinfo:
        studios.save_studio(studio, expected_updated_at="1999-01-01T00:00:00Z")
    assert excinfo.value.code == STATE_CONFLICT
