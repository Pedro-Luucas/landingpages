"""M2 orchestrator.run: discovery + public scrape, then M3. No network."""

from __future__ import annotations

from pathlib import Path

import pytest

from studio_pipeline.config import load_config
from studio_pipeline.errors import PLATFORM_BLOCKED
from studio_pipeline.http.binary import FakeBinaryHttp
from studio_pipeline.http.client import FakeHttpClient, HttpResponse
from studio_pipeline.importers.source import import_source
from studio_pipeline.orchestrator import M3_MEDIA_DONE, M4_READY_FOR_REVIEW, Orchestrator
from studio_pipeline.repositories.state import StateRepository
from studio_pipeline.repositories.studio import StudioRepository
from studio_pipeline.search.provider import NullSearchProvider

SOURCE = Path(__file__).parent / "fixtures" / "source_musica.json"
DISCOVERY_FIXTURES = Path(__file__).parent / "fixtures" / "discovery"
SCRAPER_FIXTURES = Path(__file__).parent / "fixtures" / "scrapers"
MEDIA_FIXTURES = Path(__file__).parent / "fixtures" / "media"
IG_URL = "https://www.instagram.com/aurorasoundlab.cwb/"
AMBIGUOUS_URL = "https://linktr.ee/aurora-ambiguous"
BLOCK_TOKEN = "UNIQUE_BLOCK_HTML_DUMP_TOKEN"
PROFILE_JPG = "https://cdn.aurorasoundlab.example/profile.jpg"


@pytest.fixture
def data_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("ASSETS_DIR", str(tmp_path / "public" / "studios"))
    monkeypatch.delenv("STUDIO_ID", raising=False)
    return tmp_path


def _html_response(path: Path, url: str, status: int = 200) -> HttpResponse:
    return HttpResponse(
        status=status,
        headers={"content-type": "text/html; charset=utf-8"},
        text=path.read_text(encoding="utf-8"),
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


def _binary_http() -> FakeBinaryHttp:
    logo = (MEDIA_FIXTURES / "logo.png").read_bytes()
    photo = (MEDIA_FIXTURES / "photo_a.jpg").read_bytes()
    return FakeBinaryHttp({PROFILE_JPG: logo}, default_body=photo)


def _run(
    orch: Orchestrator,
    studio_id: str,
    http: FakeHttpClient,
    *,
    binary_http: FakeBinaryHttp | None = None,
) -> str:
    return orch.run(
        studio_id,
        actor="pipeline:test",
        http_client=http,
        search_provider=NullSearchProvider(),
        binary_http=binary_http or _binary_http(),
    )


class _BoomHttp:
    def get(self, url: str) -> HttpResponse:
        raise AssertionError(f"HTTP should not be called on idempotent re-run: {url}")


class _BoomBinaryHttp:
    def get_bytes(self, url: str) -> tuple[int, dict[str, str], bytes, str]:
        raise AssertionError(f"binary HTTP should not be called on idempotent re-run: {url}")


def test_direct_instagram_url_scrapes_and_leaves_selecting_media(data_env: Path) -> None:
    studio_id, orch, studios, state = _queued_aurora(data_env)
    _patch_contacts(studios, studio_id, instagram=IG_URL)
    http = FakeHttpClient(
        {
            IG_URL: _html_response(
                SCRAPER_FIXTURES / "instagram_public.html",
                IG_URL,
            )
        }
    )

    message = _run(orch, studio_id, http)

    assert message == M3_MEDIA_DONE
    item = state.get_item(studio_id)
    assert item is not None
    assert item["status"] == "selecting_media"
    assert item.get("lastSuccessfulStage") == "selecting_media"
    assert "lockedBy" not in item
    assert state.list_locks() == []

    dossier = studios.get_dossier(studio_id)
    assert dossier is not None
    assert dossier["discovery"]["requiresHumanReview"] is False
    assert dossier["discovery"]["selectedProfiles"]["instagram"]["value"] == IG_URL
    assert "Cabine isolada" in dossier["social"]["bio"]["value"]
    assert dossier["social"]["posts"]
    studio = studios.get_studio(studio_id)
    assert studio is not None
    assert studio["pipelineStatus"] == "selecting_media"
    assert studio["contacts"]["instagram"] == IG_URL


def test_ambiguous_discovery_pauses_without_silent_profile(data_env: Path) -> None:
    studio_id, orch, studios, state = _queued_aurora(data_env)
    _patch_contacts(studios, studio_id, website=AMBIGUOUS_URL)
    http = FakeHttpClient(
        {
            AMBIGUOUS_URL: _html_response(
                DISCOVERY_FIXTURES / "linktree_ambiguous.html",
                AMBIGUOUS_URL,
            )
        }
    )

    message = _run(orch, studio_id, http)

    assert "needs_social_review" in message
    assert "silently" in message
    item = state.get_item(studio_id)
    assert item is not None
    assert item["status"] == "needs_social_review"
    assert item.get("lastSuccessfulStage") == "discovering"
    dossier = studios.get_dossier(studio_id)
    assert dossier is not None
    assert dossier["discovery"]["requiresHumanReview"] is True
    assert dossier["discovery"]["selectedProfiles"] == {}
    assert dossier["social"]["posts"] == []
    assert "bio" not in dossier["social"]
    studio = studios.get_studio(studio_id)
    assert studio is not None
    assert "instagram" not in studio["contacts"]
    assert "facebook" not in studio["contacts"]


def test_blocked_instagram_finishes_m2_without_html_in_message(data_env: Path) -> None:
    studio_id, orch, studios, state = _queued_aurora(data_env)
    _patch_contacts(studios, studio_id, instagram=IG_URL)
    blocked = _html_response(
        SCRAPER_FIXTURES / "instagram_blocked.html",
        IG_URL,
        status=403,
    )
    assert BLOCK_TOKEN in blocked.text
    http = FakeHttpClient({IG_URL: blocked})

    message = _run(orch, studio_id, http)

    assert message == M3_MEDIA_DONE
    assert BLOCK_TOKEN not in message
    assert "<html" not in message.lower()
    assert "<form" not in message.lower()
    item = state.get_item(studio_id)
    assert item is not None
    assert item["status"] == "selecting_media"
    assert item.get("lastSuccessfulStage") == "selecting_media"
    dossier = studios.get_dossier(studio_id)
    assert dossier is not None
    assert any(warning["code"] == PLATFORM_BLOCKED for warning in dossier["warnings"])
    dumped = str(dossier["warnings"])
    assert BLOCK_TOKEN not in dumped
    assert "<html" not in dumped.lower()
    social = dossier["social"]
    assert social["posts"] == []
    assert "bio" not in social


def test_rerun_when_media_complete_does_not_require_http(data_env: Path) -> None:
    studio_id, orch, studios, state = _queued_aurora(data_env)
    _patch_contacts(studios, studio_id, instagram=IG_URL)
    http = FakeHttpClient(
        {
            IG_URL: _html_response(
                SCRAPER_FIXTURES / "instagram_public.html",
                IG_URL,
            )
        }
    )
    first = _run(orch, studio_id, http)
    assert first == M3_MEDIA_DONE
    item = state.get_item(studio_id)
    assert item is not None
    assert item["status"] == "selecting_media"
    assert item.get("lastSuccessfulStage") == "selecting_media"

    second = orch.run(
        studio_id,
        actor="pipeline:test",
        http_client=_BoomHttp(),  # type: ignore[arg-type]
        search_provider=NullSearchProvider(),
        binary_http=_BoomBinaryHttp(),  # type: ignore[arg-type]
    )
    assert second == M4_READY_FOR_REVIEW
    again = state.get_item(studio_id)
    assert again is not None
    assert again["status"] == "ready_for_review"
    assert again.get("lastSuccessfulStage") == "ready_for_review"


def test_blocked_scrape_rerun_is_idempotent(data_env: Path) -> None:
    studio_id, orch, studios, state = _queued_aurora(data_env)
    _patch_contacts(studios, studio_id, instagram=IG_URL)
    blocked = _html_response(
        SCRAPER_FIXTURES / "instagram_blocked.html",
        IG_URL,
        status=403,
    )
    first = _run(orch, studio_id, FakeHttpClient({IG_URL: blocked}))
    assert first == M3_MEDIA_DONE
    item = state.get_item(studio_id)
    assert item is not None
    assert item["status"] == "selecting_media"
    assert item.get("lastSuccessfulStage") == "selecting_media"
    dossier = studios.get_dossier(studio_id)
    assert dossier is not None
    assert dossier["social"]["posts"] == []
    assert "bio" not in dossier["social"]

    second = orch.run(
        studio_id,
        actor="pipeline:test",
        http_client=_BoomHttp(),  # type: ignore[arg-type]
        search_provider=NullSearchProvider(),
        binary_http=_BoomBinaryHttp(),  # type: ignore[arg-type]
    )
    assert second == M4_READY_FOR_REVIEW
    again = state.get_item(studio_id)
    assert again is not None
    assert again["status"] == "ready_for_review"


def test_incomplete_scrape_does_not_use_illegal_review_transition(
    data_env: Path,
) -> None:
    studio_id, orch, studios, state = _queued_aurora(data_env)
    _patch_contacts(studios, studio_id, website=AMBIGUOUS_URL)
    item = state.get_item(studio_id)
    assert item is not None
    state.transition(studio_id, "discovering", actor="pipeline:test", reason="setup")
    state.transition(studio_id, "scraping", actor="pipeline:test", reason="setup")
    item = state.get_item(studio_id)
    assert item is not None
    etag = item["updatedAt"]
    item["lastSuccessfulStage"] = "discovering"
    state.save_item(item, expected_updated_at=etag if isinstance(etag, str) else None)

    http = FakeHttpClient(
        {
            AMBIGUOUS_URL: _html_response(
                DISCOVERY_FIXTURES / "linktree_ambiguous.html",
                AMBIGUOUS_URL,
            )
        }
    )
    message = _run(orch, studio_id, http)

    assert "needs review" in message
    assert "scraping→needs_social_review" in message or "not a legal transition" in message
    item = state.get_item(studio_id)
    assert item is not None
    assert item["status"] == "scraping"
    pairs = [(h.get("from"), h["to"]) for h in item["history"] if "from" in h]
    assert ("scraping", "needs_social_review") not in pairs
