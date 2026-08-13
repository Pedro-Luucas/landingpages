"""M3 orchestrator.run: enrich facts and select media. No network."""

from __future__ import annotations

import io
from pathlib import Path

import pytest
from PIL import Image

from studio_pipeline.config import load_config, repo_root
from studio_pipeline.http.binary import MAX_BINARY_BODY_BYTES, FakeBinaryHttp, StdlibBinaryHttp
from studio_pipeline.http.client import (
    DEFAULT_USER_AGENT,
    MAX_BODY_BYTES,
    FakeHttpClient,
    HttpResponse,
)
from studio_pipeline.importers.source import import_source
from studio_pipeline.orchestrator import (
    M3_MEDIA_DONE,
    M4_READY_FOR_REVIEW,
    Orchestrator,
    empty_dossier,
)
from studio_pipeline.repositories.state import StateRepository
from studio_pipeline.repositories.studio import StudioRepository
from studio_pipeline.search.provider import NullSearchProvider

SOURCE = Path(__file__).parent / "fixtures" / "source_musica.json"
SCRAPER_FIXTURES = Path(__file__).parent / "fixtures" / "scrapers"
MEDIA_FIXTURES = Path(__file__).parent / "fixtures" / "media"
ENRICH_FIXTURES = Path(__file__).parent / "fixtures" / "enrichment"
IG_URL = "https://www.instagram.com/aurorasoundlab.cwb/"
SITE = "https://www.aurorasoundlab.example/"
HOURS_URL = "https://www.aurorasoundlab.example/horarios"
ABOUT_URL = "https://www.aurorasoundlab.example/sobre"
CONTACT_URL = "https://www.aurorasoundlab.example/contato"
PRICES_URL = "https://www.aurorasoundlab.example/precos"
PROFILE_JPG = "https://cdn.aurorasoundlab.example/profile.jpg"
PHOTO_1001 = "https://cdn.aurorasoundlab.example/posts/1001.jpg"
PHOTO_1002A = "https://cdn.aurorasoundlab.example/posts/1002a.jpg"
PHOTO_1002B = "https://cdn.aurorasoundlab.example/posts/1002b.jpg"
REEL_THUMB = "https://cdn.aurorasoundlab.example/posts/reel-thumb.jpg"
SVG_URL = "https://cdn.aurorasoundlab.example/mark.svg"


@pytest.fixture
def data_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("ASSETS_DIR", str(tmp_path / "public" / "studios"))
    monkeypatch.delenv("STUDIO_ID", raising=False)
    return tmp_path


def _png_bytes(size: int = 64) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (size, size), (20, 90, 160)).save(buf, format="PNG")
    return buf.getvalue()


def _html_response(path: Path, url: str, status: int = 200) -> HttpResponse:
    return HttpResponse(
        status=status,
        headers={"content-type": "text/html; charset=utf-8"},
        text=path.read_text(encoding="utf-8"),
        final_url=url,
    )


def _enrich_html(name: str, url: str) -> HttpResponse:
    return HttpResponse(
        status=200,
        headers={"content-type": "text/html; charset=utf-8"},
        text=(ENRICH_FIXTURES / name).read_text(encoding="utf-8"),
        final_url=url,
    )


def _queued_aurora(
    tmp_path: Path,
) -> tuple[str, Orchestrator, StudioRepository, StateRepository]:
    report = import_source(SOURCE, data_dir=tmp_path)
    studio_id = next(sid for sid in report.imported if sid.startswith("aurora-sound-lab"))
    studios = StudioRepository(tmp_path)
    state = StateRepository(tmp_path, studio_repo=studios)
    state.transition(studio_id, "queued", actor="cli", reason="test")
    orch = Orchestrator(load_config(), studios=studios, state=state)
    return studio_id, orch, studios, state


def _patch_contacts(
    studios: StudioRepository,
    studio_id: str,
    **fields: str,
) -> None:
    studio = studios.get_studio(studio_id)
    assert studio is not None
    etag = studio.get("updatedAt")
    contacts = dict(studio.get("contacts") or {})
    contacts.update(fields)
    studio["contacts"] = contacts
    studios.save_studio(
        studio,
        expected_updated_at=etag if isinstance(etag, str) else None,
    )


def _ig_http(html: str | None = None) -> FakeHttpClient:
    text = html or (SCRAPER_FIXTURES / "instagram_public.html").read_text(encoding="utf-8")
    responses: dict[str, HttpResponse] = {
        IG_URL: HttpResponse(
            status=200,
            headers={"content-type": "text/html; charset=utf-8"},
            text=text,
            final_url=IG_URL,
        ),
        SITE: _enrich_html("official_site.html", SITE),
        HOURS_URL: _enrich_html("hours.html", HOURS_URL),
        ABOUT_URL: _enrich_html("about.html", ABOUT_URL),
        CONTACT_URL: _enrich_html("contact.html", CONTACT_URL),
        PRICES_URL: _enrich_html("prices.html", PRICES_URL),
    }
    return FakeHttpClient(responses)


def _binary_http() -> FakeBinaryHttp:
    png = _png_bytes()
    photo_a = (MEDIA_FIXTURES / "photo_a.jpg").read_bytes()
    photo_b = (MEDIA_FIXTURES / "photo_b.jpg").read_bytes()
    photo_c = (MEDIA_FIXTURES / "photo_c.jpg").read_bytes()
    svg = (MEDIA_FIXTURES / "icon.svg").read_bytes()
    return FakeBinaryHttp(
        {
            PROFILE_JPG: png,
            PHOTO_1001: photo_a,
            PHOTO_1002A: photo_b,
            PHOTO_1002B: photo_c,
            REEL_THUMB: photo_a,
            SVG_URL: svg,
        },
        default_body=photo_a,
    )


def _run(
    orch: Orchestrator,
    studio_id: str,
    http: FakeHttpClient,
    binary: FakeBinaryHttp,
) -> str:
    return orch.run(
        studio_id,
        actor="pipeline:test",
        http_client=http,
        search_provider=NullSearchProvider(),
        binary_http=binary,
    )


def _evidence_rows(facts: dict) -> list[dict]:
    rows: list[dict] = []
    for bucket in facts.values():
        if isinstance(bucket, list):
            rows.extend(item for item in bucket if isinstance(item, dict))
    return rows


class _BoomHttp:
    def get(self, url: str) -> HttpResponse:
        raise AssertionError(f"text HTTP should not be called: {url}")


class _BoomBinaryHttp:
    def get_bytes(self, url: str) -> tuple[int, dict[str, str], bytes, str]:
        raise AssertionError(f"binary HTTP should not be called: {url}")


def test_stdlib_binary_http_rejects_private_urls_without_sockets() -> None:
    client = StdlibBinaryHttp()
    assert client.user_agent == DEFAULT_USER_AGENT
    assert client.max_body_bytes == 8 * 1024 * 1024
    assert MAX_BINARY_BODY_BYTES == 8 * 1024 * 1024
    assert MAX_BODY_BYTES == 1_000_000
    assert MAX_BINARY_BODY_BYTES > MAX_BODY_BYTES
    status, headers, body, final_url = client.get_bytes("http://127.0.0.1/logo.png")
    assert status == 0
    assert headers == {}
    assert body == b""
    assert final_url == "http://127.0.0.1/logo.png"


def test_after_scrape_run_continues_to_selecting_media(data_env: Path) -> None:
    studio_id, orch, studios, state = _queued_aurora(data_env)
    _patch_contacts(studios, studio_id, instagram=IG_URL)
    http = _ig_http()
    binary = _binary_http()

    message = _run(orch, studio_id, http, binary)

    assert message == M3_MEDIA_DONE
    item = state.get_item(studio_id)
    assert item is not None
    assert item["status"] == "selecting_media"
    assert item.get("lastSuccessfulStage") == "selecting_media"
    assert "lockedBy" not in item
    assert state.list_locks() == []

    dossier = studios.get_dossier(studio_id)
    assert dossier is not None
    rows = _evidence_rows(dossier["facts"])
    assert rows
    assert all(item.get("sourceUrl") for item in rows)
    selected = dossier["media"]["selected"]
    assert isinstance(selected, list)
    assert len(selected) >= 0
    assert "logo" in dossier["media"]
    assert dossier["media"]["logo"]["sourceUrl"] == PROFILE_JPG
    assert dossier["media"]["logo"]["mime"] == "image/png"
    assert PROFILE_JPG in binary.calls
    assets_root = data_env / "public" / "studios" / studio_id
    assert (assets_root / "logo.png").is_file()
    assert (assets_root / "images" / "01.jpg").is_file()
    assert assets_root.resolve().is_relative_to(data_env.resolve())
    assert not (repo_root() / "public" / "studios" / studio_id).exists()


def test_conflicting_facts_keep_both_evidence_rows(data_env: Path) -> None:
    studio_id, orch, studios, state = _queued_aurora(data_env)
    _patch_contacts(studios, studio_id, instagram=IG_URL, website=PRICES_URL)
    dossier = empty_dossier(studio_id)
    dossier["facts"]["prices"] = [
        {
            "value": [
                {
                    "label": "Ensaio 2 horas",
                    "amountText": "R$ 90",
                    "conditions": "Listagem de diretório.",
                }
            ],
            "sourceUrl": "https://directory.example/aurora-sound-lab",
            "sourceType": "directory",
            "collectedAt": "2026-08-12T15:00:00Z",
            "confidence": 0.35,
            "excerpt": "Ensaio 2 horas — R$ 90",
        }
    ]
    studios.save_dossier(dossier)

    http = _ig_http()
    binary = _binary_http()
    message = _run(orch, studio_id, http, binary)

    assert message == M3_MEDIA_DONE
    saved = studios.get_dossier(studio_id)
    assert saved is not None
    prices = saved["facts"]["prices"]
    assert len(prices) == 2
    types = {item["sourceType"] for item in prices}
    assert types == {"official_site", "directory"}
    assert all(item.get("sourceUrl") for item in prices)
    assert any(warning["code"] == "FACT_CONFLICT" for warning in saved["warnings"])


def test_rerun_when_selecting_media_complete_does_not_call_http(data_env: Path) -> None:
    studio_id, orch, studios, state = _queued_aurora(data_env)
    _patch_contacts(studios, studio_id, instagram=IG_URL)
    http = _ig_http()
    binary = _binary_http()
    first = _run(orch, studio_id, http, binary)
    assert first == M3_MEDIA_DONE
    text_calls = list(http.requested)
    binary_calls = list(binary.calls)
    assert text_calls
    assert binary_calls

    second = orch.run(
        studio_id,
        actor="pipeline:test",
        http_client=_BoomHttp(),  # type: ignore[arg-type]
        search_provider=NullSearchProvider(),
        binary_http=_BoomBinaryHttp(),  # type: ignore[arg-type]
    )
    assert second == M4_READY_FOR_REVIEW
    item = state.get_item(studio_id)
    assert item is not None
    assert item["status"] == "ready_for_review"
    assert item.get("lastSuccessfulStage") == "ready_for_review"
    assert http.requested == text_calls
    assert binary.calls == binary_calls


def test_svg_url_in_posts_is_not_selected(data_env: Path) -> None:
    studio_id, orch, studios, state = _queued_aurora(data_env)
    _patch_contacts(studios, studio_id, instagram=IG_URL)
    html = (SCRAPER_FIXTURES / "instagram_public.html").read_text(encoding="utf-8")
    html = html.replace(
        "</body>",
        (
            '<article data-post data-id="svgmark" '
            'data-url="https://www.instagram.com/p/svgmark/" '
            'data-media-type="image">'
            f'<img data-media src="{SVG_URL}" alt="">'
            "</article></body>"
        ),
    )
    http = _ig_http(html)
    binary = _binary_http()

    message = _run(orch, studio_id, http, binary)

    assert message == M3_MEDIA_DONE
    dossier = studios.get_dossier(studio_id)
    assert dossier is not None
    post_urls = [
        item.get("url")
        for post in dossier["social"]["posts"]
        for item in post.get("media") or []
    ]
    assert SVG_URL in post_urls
    selected_urls = [item["sourceUrl"] for item in dossier["media"]["selected"]]
    candidate_urls = [item["sourceUrl"] for item in dossier["media"]["candidates"]]
    assert SVG_URL not in selected_urls
    assert SVG_URL not in candidate_urls
    assert SVG_URL not in binary.calls


def test_m2_complete_skips_rescrape_and_continues_m3(data_env: Path) -> None:
    studio_id, orch, studios, state = _queued_aurora(data_env)
    _patch_contacts(studios, studio_id, instagram=IG_URL)
    http = _ig_http()
    binary = _binary_http()
    first = _run(orch, studio_id, http, binary)
    assert first == M3_MEDIA_DONE

    item = state.get_item(studio_id)
    assert item is not None
    etag = item["updatedAt"]
    item["status"] = "scraping"
    item["lastSuccessfulStage"] = "scraping"
    state.save_item(item, expected_updated_at=etag if isinstance(etag, str) else None)

    http.requested.clear()
    binary.calls.clear()
    second = _run(orch, studio_id, http, binary)

    assert second == M3_MEDIA_DONE
    assert IG_URL not in http.requested
    item = state.get_item(studio_id)
    assert item is not None
    assert item["status"] == "selecting_media"
    assert item.get("lastSuccessfulStage") == "selecting_media"


def test_enriching_complete_skips_enrich_and_runs_media(data_env: Path) -> None:
    studio_id, orch, studios, state = _queued_aurora(data_env)
    _patch_contacts(studios, studio_id, instagram=IG_URL)
    http = _ig_http()
    binary = _binary_http()
    first = _run(orch, studio_id, http, binary)
    assert first == M3_MEDIA_DONE

    item = state.get_item(studio_id)
    assert item is not None
    etag = item["updatedAt"]
    item["status"] = "enriching"
    item["lastSuccessfulStage"] = "enriching"
    state.save_item(item, expected_updated_at=etag if isinstance(etag, str) else None)

    boom_text = _BoomHttp()
    binary.calls.clear()
    second = orch.run(
        studio_id,
        actor="pipeline:test",
        http_client=boom_text,  # type: ignore[arg-type]
        search_provider=NullSearchProvider(),
        binary_http=binary,
    )
    assert second == M3_MEDIA_DONE
    assert binary.calls
    item = state.get_item(studio_id)
    assert item is not None
    assert item["status"] == "selecting_media"
    assert item.get("lastSuccessfulStage") == "selecting_media"
    assert "lockedBy" not in item
