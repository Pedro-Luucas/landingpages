"""Deterministic factuality validator (M4). No network."""

from __future__ import annotations

import copy

import pytest

from studio_pipeline.ai.providers.fake import FakeProvider
from studio_pipeline.config import schemas_dir
from studio_pipeline.errors import FACT_WITHOUT_EVIDENCE, PipelineError
from studio_pipeline.orchestrator import empty_dossier
from studio_pipeline.validation.factuality import validate_generated
from studio_pipeline.validation.schemas import load_json

DOSSIER_FIXTURE = schemas_dir() / "fixtures" / "dossier.valid.json"
GENERATED_FIXTURE = schemas_dir() / "fixtures" / "generated.valid.json"


def _fake_site(dossier: dict) -> dict:
    provider = FakeProvider()
    brand = provider.analyze_brand(dossier, [])
    media = provider.select_media(dossier, [])
    return provider.generate_site(dossier, brand, media)


def test_valid_fixture_and_fake_output_pass() -> None:
    dossier = load_json(DOSSIER_FIXTURE)
    generated = load_json(GENERATED_FIXTURE)
    validate_generated(generated, dossier)
    validate_generated(_fake_site(dossier), dossier)


def test_injected_price_without_evidence_is_blocked() -> None:
    dossier = empty_dossier("aurora-sound-lab-cwb")
    generated = _fake_site(dossier)
    generated["copy"]["pricing"] = {
        "title": "Sessões",
        "items": [{"label": "Ensaio 2 horas", "value": "R$ 999"}],
    }
    generated["sections"] = [
        {**item, "enabled": True} if item.get("id") == "pricing" else item
        for item in generated["sections"]
    ]
    with pytest.raises(PipelineError) as excinfo:
        validate_generated(generated, dossier)
    assert excinfo.value.code == FACT_WITHOUT_EVIDENCE
    assert "pric" in excinfo.value.message.lower() or "R$" in excinfo.value.message


def test_price_in_about_without_claim_is_blocked() -> None:
    dossier = empty_dossier("aurora-sound-lab-cwb")
    dossier["social"]["bio"] = {
        "value": "Estúdio de gravação em Curitiba.",
        "sourceUrl": "https://www.instagram.com/example/",
        "sourceType": "instagram",
        "collectedAt": "2026-08-12T12:30:00Z",
        "confidence": 0.9,
    }
    generated = _fake_site(dossier)
    about = dict(generated["copy"].get("about") or {"title": "Sobre", "body": "Estúdio."})
    about["body"] = about.get("body", "Estúdio.") + " Ensaio a R$ 250."
    generated["copy"]["about"] = about
    with pytest.raises(PipelineError) as excinfo:
        validate_generated(generated, dossier)
    assert excinfo.value.code == FACT_WITHOUT_EVIDENCE


def test_enabled_pricing_with_empty_facts_is_blocked() -> None:
    dossier = empty_dossier("aurora-sound-lab-cwb")
    generated = _fake_site(dossier)
    generated["sections"] = [
        {**item, "enabled": True} if item.get("id") == "pricing" else item
        for item in generated["sections"]
    ]
    with pytest.raises(PipelineError) as excinfo:
        validate_generated(generated, dossier)
    assert excinfo.value.code == FACT_WITHOUT_EVIDENCE


def test_unmatched_rating_number_is_blocked() -> None:
    dossier = empty_dossier("aurora-sound-lab-cwb")
    generated = _fake_site(dossier)
    generated["copy"]["hero"]["subtitle"] = "Avaliado em 4.9 pelos clientes."
    with pytest.raises(PipelineError) as excinfo:
        validate_generated(generated, dossier)
    assert excinfo.value.code == FACT_WITHOUT_EVIDENCE


def test_invented_fechado_without_empty_intervals_is_blocked() -> None:
    dossier = load_json(DOSSIER_FIXTURE)
    for row in dossier.get("facts", {}).get("openingHours") or []:
        value = row.get("value") if isinstance(row, dict) else None
        if not isinstance(value, list):
            continue
        for day in value:
            if isinstance(day, dict) and isinstance(day.get("intervals"), list):
                if not day["intervals"]:
                    day["intervals"] = ["10:00-18:00"]
    generated = _fake_site(dossier)
    generated["copy"]["hours"]["items"] = [{"day": "Domingo", "value": "Fechado"}]
    with pytest.raises(PipelineError) as excinfo:
        validate_generated(generated, dossier)
    assert excinfo.value.code == FACT_WITHOUT_EVIDENCE
    assert "Fechado" in excinfo.value.message


def test_fechado_supported_by_empty_intervals() -> None:
    dossier = load_json(DOSSIER_FIXTURE)
    generated = _fake_site(dossier)
    values = [item.get("value") for item in generated["copy"]["hours"]["items"]]
    assert "Fechado" in values
    validate_generated(generated, dossier)


def test_fake_contact_body_does_not_invent_appointment_policy() -> None:
    dossier = load_json(DOSSIER_FIXTURE)
    generated = _fake_site(dossier)
    body = str(generated["copy"]["contact"].get("body") or "")
    assert "hora marcada" not in body.lower()
    empty = _fake_site(empty_dossier("aurora-sound-lab-cwb"))
    assert "body" not in empty["copy"]["contact"]


def test_price_with_resolving_evidence_passes() -> None:
    dossier = load_json(DOSSIER_FIXTURE)
    generated = _fake_site(dossier)
    validate_generated(generated, dossier)
    poisoned = copy.deepcopy(generated)
    poisoned["copy"]["pricing"]["items"][0]["value"] = "R$ 1"
    with pytest.raises(PipelineError) as excinfo:
        validate_generated(poisoned, dossier)
    assert excinfo.value.code == FACT_WITHOUT_EVIDENCE


def test_invented_address_sharing_city_is_blocked() -> None:
    dossier = load_json(DOSSIER_FIXTURE)
    generated = _fake_site(dossier)
    generated["copy"]["contact"]["body"] = (
        "Atendimento com hora marcada. Rua Inventada, 1, Curitiba - PR."
    )
    with pytest.raises(PipelineError) as excinfo:
        validate_generated(generated, dossier)
    assert excinfo.value.code == FACT_WITHOUT_EVIDENCE


def test_portuguese_hours_in_about_without_evidence_are_blocked() -> None:
    dossier = load_json(DOSSIER_FIXTURE)
    generated = _fake_site(dossier)
    about = dict(generated["copy"]["about"])
    about["body"] = about["body"] + " Aberto das 8h às 11h."
    generated["copy"]["about"] = about
    with pytest.raises(PipelineError) as excinfo:
        validate_generated(generated, dossier)
    assert excinfo.value.code == FACT_WITHOUT_EVIDENCE


def test_invented_review_count_is_blocked() -> None:
    dossier = load_json(DOSSIER_FIXTURE)
    generated = _fake_site(dossier)
    generated["copy"]["reviews"]["count"] = 9999
    with pytest.raises(PipelineError) as excinfo:
        validate_generated(generated, dossier)
    assert excinfo.value.code == FACT_WITHOUT_EVIDENCE


def test_truncated_rating_is_blocked() -> None:
    dossier = load_json(DOSSIER_FIXTURE)
    generated = _fake_site(dossier)
    generated["copy"]["reviews"]["rating"] = 4
    with pytest.raises(PipelineError) as excinfo:
        validate_generated(generated, dossier)
    assert excinfo.value.code == FACT_WITHOUT_EVIDENCE


def test_price_in_reais_without_comma_is_blocked() -> None:
    dossier = load_json(DOSSIER_FIXTURE)
    generated = _fake_site(dossier)
    about = dict(generated["copy"]["about"])
    about["body"] = about["body"] + " Custa 250 reais."
    generated["copy"]["about"] = about
    with pytest.raises(PipelineError) as excinfo:
        validate_generated(generated, dossier)
    assert excinfo.value.code == FACT_WITHOUT_EVIDENCE


def test_fechado_on_open_days_is_blocked() -> None:
    dossier = load_json(DOSSIER_FIXTURE)
    generated = _fake_site(dossier)
    generated["copy"]["hours"]["items"][0]["value"] = "Fechado"
    with pytest.raises(PipelineError) as excinfo:
        validate_generated(generated, dossier)
    assert excinfo.value.code == FACT_WITHOUT_EVIDENCE
