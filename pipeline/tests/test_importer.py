"""M1 importer: idempotent reimport, ids, website normalization."""

from __future__ import annotations

import json
from pathlib import Path

from studio_pipeline.importers.normalize import preferred_studio_id, slugify
from studio_pipeline.importers.source import import_source
from studio_pipeline.persistence import read_json
from studio_pipeline.repositories.studio import StudioRepository

FIXTURE = Path(__file__).parent / "fixtures" / "source_musica.json"


def test_slugify_strips_accents() -> None:
    assert slugify("São Paulo") == "sao-paulo"
    assert slugify("Estúdio Lagoa Azul") == "estudio-lagoa-azul"


def test_preferred_studio_id_uses_city_state_suffix() -> None:
    studio_id = preferred_studio_id("Aurora Sound Lab", "Curitiba", "Paraná")
    assert studio_id == "aurora-sound-lab-cur-pr"
    assert studio_id == slugify(studio_id)


def test_reimport_same_fixture_is_idempotent(tmp_path: Path) -> None:
    first = import_source(FIXTURE, data_dir=tmp_path)
    second = import_source(FIXTURE, data_dir=tmp_path)

    assert len(first.imported) == 3
    assert first.updated == []
    assert first.unchanged == []
    assert first.invalid == []

    assert second.imported == []
    assert second.updated == []
    assert len(second.unchanged) == 3
    assert set(second.unchanged) == set(first.imported)

    studio_dirs = sorted(p.name for p in (tmp_path / "studios").iterdir() if p.is_dir())
    assert studio_dirs == sorted(first.imported)

    repo = StudioRepository(tmp_path)
    aurora_id = next(sid for sid in first.imported if sid.startswith("aurora-sound-lab"))
    studio = repo.get_studio(aurora_id)
    assert studio is not None
    original = studio["source"]["originalRecord"]
    assert original["title"] == "Aurora Sound Lab"
    assert original["website"] == "https://www.aurorasoundlab.example/"
    assert studio["source"]["sourceHash"]
    assert len(studio["source"]["sourceHash"]) == 64


def test_invalid_website_omitted_valid_https_kept(tmp_path: Path) -> None:
    report = import_source(FIXTURE, data_dir=tmp_path)
    repo = StudioRepository(tmp_path)

    aurora_id = next(sid for sid in report.imported if sid.startswith("aurora-sound-lab"))
    norte_id = next(sid for sid in report.imported if sid.startswith("norte-wave-studio"))

    aurora = repo.get_studio(aurora_id)
    norte = repo.get_studio(norte_id)
    assert aurora is not None
    assert norte is not None
    assert aurora["contacts"]["website"] == "https://www.aurorasoundlab.example/"
    assert "website" not in norte["contacts"]


def test_non_http_uris_omitted(tmp_path: Path) -> None:
    payload = {
        "musica": [
            {
                "title": "Script Studio",
                "cidade": "Curitiba",
                "estado": "Paraná",
                "address": "Rua C, 3",
                "website": "javascript:alert(1)",
            }
        ]
    }
    source = tmp_path / "js.json"
    source.write_text(json.dumps(payload), encoding="utf-8")
    report = import_source(source, data_dir=tmp_path)
    studio = StudioRepository(tmp_path).get_studio(report.imported[0])
    assert studio is not None
    assert "website" not in studio["contacts"]


def test_hash_change_updates_without_deleting_dossier(tmp_path: Path) -> None:
    report = import_source(FIXTURE, data_dir=tmp_path)
    studio_id = report.imported[0]
    dossier_path = tmp_path / "studios" / studio_id / "dossier.json"
    dossier_path.write_text('{"keep": true}', encoding="utf-8")

    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    payload["musica"][0]["phoneNumber"] = "+55 41 90000-9999"
    changed = tmp_path / "changed.json"
    changed.write_text(json.dumps(payload), encoding="utf-8")

    second = import_source(changed, data_dir=tmp_path)
    assert studio_id in second.updated
    assert json.loads(dossier_path.read_text(encoding="utf-8"))["keep"] is True
    studio = read_json(tmp_path / "studios" / studio_id / "studio.json")
    assert studio["contacts"]["phone"] == "+55 41 90000-9999"
    assert studio["source"]["originalRecord"]["phoneNumber"] == "+55 41 90000-9999"


def test_name_change_keeps_studio_id(tmp_path: Path) -> None:
    report = import_source(FIXTURE, data_dir=tmp_path)
    aurora_id = next(sid for sid in report.imported if sid.startswith("aurora-sound-lab"))
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    payload["musica"][0]["title"] = "Aurora Sound Lab Renamed"
    changed = tmp_path / "renamed.json"
    changed.write_text(json.dumps(payload), encoding="utf-8")

    second = import_source(changed, data_dir=tmp_path)
    assert aurora_id in second.updated
    assert aurora_id not in second.imported
    studio = StudioRepository(tmp_path).get_studio(aurora_id)
    assert studio is not None
    assert studio["studioId"] == aurora_id
    assert studio["name"] == "Aurora Sound Lab Renamed"
    assert studio["source"]["originalRecord"]["title"] == "Aurora Sound Lab Renamed"


def test_update_preserves_enriched_contacts(tmp_path: Path) -> None:
    report = import_source(FIXTURE, data_dir=tmp_path)
    studio_id = report.imported[0]
    path = tmp_path / "studios" / studio_id / "studio.json"
    studio = json.loads(path.read_text(encoding="utf-8"))
    studio["contacts"]["instagram"] = "https://www.instagram.com/aurora.example/"
    path.write_text(json.dumps(studio, indent=2) + "\n", encoding="utf-8")

    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    payload["musica"][0]["phoneNumber"] = "+55 41 90000-0000"
    changed = tmp_path / "phone.json"
    changed.write_text(json.dumps(payload), encoding="utf-8")

    import_source(changed, data_dir=tmp_path)
    updated = json.loads(path.read_text(encoding="utf-8"))
    assert updated["contacts"]["instagram"] == "https://www.instagram.com/aurora.example/"
    assert updated["contacts"]["phone"] == "+55 41 90000-0000"


def test_collision_does_not_merge_different_records(tmp_path: Path) -> None:
    payload = {
        "musica": [
            {
                "title": "Twin Studio",
                "cidade": "Curitiba",
                "estado": "Paraná",
                "address": "Rua A, 1",
                "website": "https://twin-a.example/",
            },
            {
                "title": "Twin Studio",
                "cidade": "Curitiba",
                "estado": "Paraná",
                "address": "Rua B, 2",
                "website": "https://twin-b.example/",
            },
        ]
    }
    source = tmp_path / "twins.json"
    source.write_text(json.dumps(payload), encoding="utf-8")
    report = import_source(source, data_dir=tmp_path)
    assert len(report.imported) == 2
    assert len(set(report.imported)) == 2
    repo = StudioRepository(tmp_path)
    sites = {repo.get_studio(sid)["contacts"]["website"] for sid in report.imported}
    assert sites == {"https://twin-a.example/", "https://twin-b.example/"}
