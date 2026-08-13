"""M4 orchestrator: selecting_media → generating → validating → ready_for_review."""

from __future__ import annotations

from pathlib import Path

import pytest

from studio_pipeline.config import load_config
from studio_pipeline.errors import FACT_WITHOUT_EVIDENCE, PipelineError
from studio_pipeline.orchestrator import (
    M3_MEDIA_DONE,
    M4_ALREADY_READY,
    M4_READY_FOR_REVIEW,
)
from studio_pipeline.validation.factuality import validate_generated
from studio_pipeline.validation.schema_store import load_schema
from studio_pipeline.validation.schemas import validate_instance

from test_orchestrator_m3 import (
    IG_URL,
    _binary_http,
    _ig_http,
    _patch_contacts,
    _queued_aurora,
    _run,
)


@pytest.fixture
def data_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("ASSETS_DIR", str(tmp_path / "public" / "studios"))
    monkeypatch.setenv("AI_PROVIDER", "fake")
    monkeypatch.delenv("STUDIO_ID", raising=False)
    return tmp_path


def test_run_from_selecting_media_reaches_ready_for_review(data_env: Path) -> None:
    studio_id, orch, studios, state = _queued_aurora(data_env)
    _patch_contacts(studios, studio_id, instagram=IG_URL)
    first = _run(orch, studio_id, _ig_http(), _binary_http())
    assert first == M3_MEDIA_DONE
    item = state.get_item(studio_id)
    assert item is not None
    assert item["status"] == "selecting_media"

    second = _run(orch, studio_id, _ig_http(), _binary_http())
    assert second == M4_READY_FOR_REVIEW
    item = state.get_item(studio_id)
    assert item is not None
    assert item["status"] == "ready_for_review"
    assert item.get("lastSuccessfulStage") == "ready_for_review"
    assert "lockedBy" not in item
    assert state.list_locks() == []
    pairs = [(entry.get("from"), entry["to"]) for entry in item["history"] if "from" in entry]
    assert ("selecting_media", "generating") in pairs
    assert ("generating", "validating") in pairs
    assert ("validating", "ready_for_review") in pairs
    assert ("ready_for_review", "approved") not in pairs

    generated = studios.get_generated(studio_id)
    assert generated is not None
    validate_instance(load_schema("generated"), generated)
    dossier = studios.get_dossier(studio_id)
    assert dossier is not None
    validate_generated(generated, dossier)
    assert generated["provider"] == "fake"
    path = studios.studio_dir(studio_id) / "generated.json"
    assert path.is_file()


def test_ready_for_review_run_is_noop(data_env: Path) -> None:
    studio_id, orch, studios, state = _queued_aurora(data_env)
    _patch_contacts(studios, studio_id, instagram=IG_URL)
    _run(orch, studio_id, _ig_http(), _binary_http())
    _run(orch, studio_id, _ig_http(), _binary_http())
    generated = studios.get_generated(studio_id)
    assert generated is not None
    generation_id = generated["generationId"]

    third = orch.run(
        studio_id,
        actor="pipeline:test",
        http_client=_ig_http(),
        binary_http=_binary_http(),
    )
    assert third == M4_ALREADY_READY
    item = state.get_item(studio_id)
    assert item is not None
    assert item["status"] == "ready_for_review"
    again = studios.get_generated(studio_id)
    assert again is not None
    assert again["generationId"] == generation_id
    assert "lockedBy" not in item


def test_injected_price_does_not_reach_ready_for_review(
    data_env: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from studio_pipeline.ai.providers.fake import FakeProvider

    class PoisonProvider(FakeProvider):
        def generate_site(self, dossier, brand, selected_media):
            site = super().generate_site(dossier, brand, selected_media)
            site["copy"]["pricing"] = {
                "title": "Sessões",
                "items": [{"label": "Ensaio inventado", "value": "R$ 999"}],
            }
            site["sections"] = [
                {**item, "enabled": True} if item.get("id") == "pricing" else item
                for item in site["sections"]
            ]
            return site

    monkeypatch.setattr(
        "studio_pipeline.orchestrator.create_provider",
        lambda config=None: PoisonProvider(),
    )
    studio_id, orch, studios, state = _queued_aurora(data_env)
    _patch_contacts(studios, studio_id, instagram=IG_URL)
    _run(orch, studio_id, _ig_http(), _binary_http())

    with pytest.raises(PipelineError) as excinfo:
        _run(orch, studio_id, _ig_http(), _binary_http())
    assert excinfo.value.code == FACT_WITHOUT_EVIDENCE
    item = state.get_item(studio_id)
    assert item is not None
    assert item["status"] != "ready_for_review"
    assert studios.get_generated(studio_id) is None
    rejected = studios.studio_dir(studio_id) / "generated.rejected.json"
    assert rejected.is_file()
    assert "lockedBy" not in item
    assert state.list_locks() == []


def test_same_input_hash_skips_regeneration(data_env: Path) -> None:
    studio_id, orch, studios, state = _queued_aurora(data_env)
    _patch_contacts(studios, studio_id, instagram=IG_URL)
    _run(orch, studio_id, _ig_http(), _binary_http())
    _run(orch, studio_id, _ig_http(), _binary_http())
    item = state.get_item(studio_id)
    assert item is not None
    etag = item["updatedAt"]
    item["status"] = "generating"
    item["lastSuccessfulStage"] = "generating"
    state.save_item(item, expected_updated_at=etag if isinstance(etag, str) else None)

    message = _run(orch, studio_id, _ig_http(), _binary_http())
    assert message == M4_READY_FOR_REVIEW
    item = state.get_item(studio_id)
    assert item is not None
    assert item["status"] == "ready_for_review"
