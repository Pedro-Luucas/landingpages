"""FakeProvider and AI factory (M4). No network."""

from __future__ import annotations

from pathlib import Path

import pytest

from studio_pipeline.ai.factory import create_provider
from studio_pipeline.ai.input_hash import PROMPT_VERSION, compute_input_hash
from studio_pipeline.ai.providers.fake import FakeProvider
from studio_pipeline.config import load_config, schemas_dir
from studio_pipeline.errors import AI_PROVIDER_ERROR, PipelineError
from studio_pipeline.orchestrator import empty_dossier
from studio_pipeline.validation.factuality import validate_generated
from studio_pipeline.validation.schemas import load_json, validate_instance

SCHEMA = schemas_dir() / "generated.schema.json"
DOSSIER_FIXTURE = schemas_dir() / "fixtures" / "dossier.valid.json"


@pytest.fixture(autouse=True)
def no_network(monkeypatch: pytest.MonkeyPatch) -> None:
    def blocked(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("network access is forbidden in AI tests")

    monkeypatch.setattr("urllib.request.urlopen", blocked)
    monkeypatch.setattr("socket.create_connection", blocked)


def _generate(dossier: dict) -> dict:
    provider = FakeProvider()
    brand = provider.analyze_brand(dossier, [])
    media = provider.select_media(dossier, list((dossier.get("media") or {}).get("candidates") or []))
    return provider.generate_site(dossier, brand, media)


def test_fake_output_validates_against_generated_schema() -> None:
    dossier = load_json(DOSSIER_FIXTURE)
    generated = _generate(dossier)
    validate_instance(load_json(SCHEMA), generated)
    validate_generated(generated, dossier)
    assert generated["provider"] == "fake"
    assert generated["model"] == "fake-m4"
    assert generated["promptVersion"] == PROMPT_VERSION
    assert generated["inputHash"] == compute_input_hash(
        dossier,
        assets=generated["assetPaths"],
        prompt_version=PROMPT_VERSION,
    )
    assert generated["copy"]["hero"]["title"]
    assert generated["copy"]["contact"]["cta"]
    assert generated["copy"]["pricing"]["items"]
    assert any(item["id"] == "pricing" and item["enabled"] for item in generated["sections"])
    prompt = Path(__file__).resolve().parents[1] / "src" / "studio_pipeline" / "ai" / "prompts" / "m4.v1.md"
    assert prompt.is_file()
    assert "m4.v1" in prompt.read_text(encoding="utf-8")


def test_dossier_without_prices_omits_pricing_copy() -> None:
    dossier = empty_dossier("aurora-sound-lab-cwb")
    dossier["social"]["bio"] = {
        "value": "Estúdio de gravação e ensaio em Curitiba, com cabine isolada.",
        "sourceUrl": "https://www.instagram.com/aurorasoundlab.cwb/",
        "sourceType": "instagram",
        "collectedAt": "2026-08-12T12:30:00Z",
        "confidence": 0.9,
    }
    generated = _generate(dossier)
    validate_instance(load_json(SCHEMA), generated)
    validate_generated(generated, dossier)
    assert "pricing" not in generated["copy"]
    assert any(item["id"] == "pricing" and item["enabled"] is False for item in generated["sections"])
    assert "hours" not in generated["copy"]
    assert any(item["id"] == "hours" and item["enabled"] is False for item in generated["sections"])


def test_few_images_select_minimal_template() -> None:
    dossier = empty_dossier("estudio-poucas-fotos")
    generated = _generate(dossier)
    assert generated["templateId"] == "minimal"


def test_many_images_select_immersive_template() -> None:
    dossier = empty_dossier("estudio-muitas-fotos")
    dossier["media"]["selected"] = [
        {"localPath": f"public/studios/estudio-muitas-fotos/images/{index:02d}.jpg"}
        for index in range(1, 8)
    ]
    generated = _generate(dossier)
    assert generated["templateId"] == "immersive"
    assert generated["assetPaths"] == [
        item["localPath"] for item in dossier["media"]["selected"]
    ]


def test_create_provider_fake(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AI_PROVIDER", "fake")
    provider = create_provider(load_config())
    assert isinstance(provider, FakeProvider)


def test_create_provider_empty_defaults_to_fake(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("AI_PROVIDER", raising=False)
    provider = create_provider(load_config())
    assert isinstance(provider, FakeProvider)


def test_create_provider_unknown_name(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AI_PROVIDER", "not-a-provider")
    with pytest.raises(PipelineError) as excinfo:
        create_provider(load_config())
    assert excinfo.value.code == AI_PROVIDER_ERROR


def test_create_provider_openai_missing_module(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AI_PROVIDER", "openai")

    def _boom(name: str):
        raise ImportError("hidden for test")

    monkeypatch.setattr("studio_pipeline.ai.factory.importlib.import_module", _boom)
    with pytest.raises(PipelineError) as excinfo:
        create_provider(load_config())
    assert excinfo.value.code == AI_PROVIDER_ERROR
    assert "openai_compatible" in excinfo.value.message


def test_create_provider_openai_lazy_import_does_not_call_network(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AI_PROVIDER", "openai")
    monkeypatch.setenv("AI_API_KEY", "sk-test-not-used")
    provider = create_provider(load_config())
    assert type(provider).__name__ == "OpenAICompatibleProvider"


def test_input_hash_ignores_warning_timestamps() -> None:
    dossier = load_json(DOSSIER_FIXTURE)
    first = compute_input_hash(dossier)
    dossier["warnings"][0]["at"] = "2099-01-01T00:00:00Z"
    dossier["completedAt"] = "2099-01-01T00:00:00Z"
    assert compute_input_hash(dossier) == first
