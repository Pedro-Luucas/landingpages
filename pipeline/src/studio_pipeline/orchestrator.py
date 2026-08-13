"""Pipeline orchestrator.

M2: lock, discover public Instagram/Facebook profiles, scrape selected pages.
M3: enrich facts and select media, then stop in ``selecting_media``.
M4: FakeProvider generation, schema + factuality, then ``ready_for_review``.
Lock is always released.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from jsonschema.exceptions import ValidationError

from studio_pipeline.ai.factory import create_provider
from studio_pipeline.ai.input_hash import (
    PROMPT_VERSION,
    collect_asset_paths,
    compute_input_hash,
    generation_id_for,
)
from studio_pipeline.clock import utc_now_iso
from studio_pipeline.config import Config, load_config, repo_root
from studio_pipeline.discovery import DiscoveryOutcome, discover_profiles
from studio_pipeline.enrichment import create_places_provider, enrich_facts
from studio_pipeline.errors import (
    AI_OUTPUT_INVALID,
    AI_PROVIDER_ERROR,
    ASSET_TOO_LARGE,
    DOWNLOAD_INVALID,
    HTTP_NOT_FOUND,
    HTTP_TIMEOUT,
    INPUT_INVALID,
    PLATFORM_BLOCKED,
    RATE_LIMITED,
    SOCIAL_AMBIGUOUS,
    SOCIAL_NOT_FOUND,
    PipelineError,
)
from studio_pipeline.persistence import atomic_write_json
from studio_pipeline.http import HttpClient, StdlibBinaryHttp, StdlibHttpClient
from studio_pipeline.http.adapter import ScraperHttpAdapter
from studio_pipeline.media import BinaryHttp, select_assets
from studio_pipeline.repositories.state import DEFAULT_LOCK_TTL_SECONDS, StateRepository
from studio_pipeline.repositories.studio import StudioRepository
from studio_pipeline.scrapers import merge_social, scrape_facebook, scrape_instagram
from studio_pipeline.search import create_search_provider
from studio_pipeline.search.provider import SearchProvider
from studio_pipeline.state_machine import is_allowed_transition
from studio_pipeline.validation.factuality import validate_generated
from studio_pipeline.validation.schema_store import load_schema
from studio_pipeline.validation.schemas import validate_instance

ALLOWED_RUN_STATUSES = frozenset(
    {
        "queued",
        "discovering",
        "needs_social_review",
        "scraping",
        "enriching",
        "selecting_media",
        "generating",
        "validating",
        "ready_for_review",
    }
)
_SCRAPE_SOFT_FAIL = frozenset(
    {PLATFORM_BLOCKED, RATE_LIMITED, HTTP_TIMEOUT, HTTP_NOT_FOUND}
)
_SCRAPE_RETRYABLE = frozenset({RATE_LIMITED, HTTP_TIMEOUT})
_M3_SOFT_FAIL = frozenset(
    {PLATFORM_BLOCKED, HTTP_TIMEOUT, DOWNLOAD_INVALID, ASSET_TOO_LARGE, HTTP_NOT_FOUND}
)
_STAGE_ORDER = (
    "scraping",
    "enriching",
    "selecting_media",
    "generating",
    "validating",
    "ready_for_review",
)
_M2_DONE_STAGES = frozenset({"scraping", "enriching", "selecting_media"})

M3_MEDIA_DONE = (
    "M3: media selection finished. Generation is M4. "
    "Studio left in selecting_media; lock released."
)
M3_ALREADY_COMPLETE = (
    "M3: media already selected. Generation is M4. "
    "Studio left in selecting_media; lock released. No HTTP was performed."
)
M4_READY_FOR_REVIEW = "M4 ready_for_review; build/Lighthouse is M5."
M4_ALREADY_READY = (
    "M4: already ready_for_review. Lock released. No generation was performed."
)


def empty_dossier(studio_id: str) -> dict[str, Any]:
    """Minimal dossier that satisfies ``dossier.schema.json``."""
    return {
        "schemaVersion": 1,
        "studioId": studio_id,
        "discovery": {
            "attempts": [],
            "selectedProfiles": {},
            "requiresHumanReview": False,
        },
        "social": {"highlights": [], "posts": []},
        "facts": {
            "description": [],
            "equipment": [],
            "prices": [],
            "openingHours": [],
            "googleReviews": [],
            "map": [],
        },
        "media": {"candidates": [], "selected": []},
        "warnings": [],
    }


def _selected_profile_url(evidence: object) -> str | None:
    if not isinstance(evidence, dict):
        return None
    value = evidence.get("value")
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def _has_selected_social(selected: object) -> bool:
    if not isinstance(selected, dict):
        return False
    return bool(
        _selected_profile_url(selected.get("instagram"))
        or _selected_profile_url(selected.get("facebook"))
    )


def _review_reason(outcome: DiscoveryOutcome) -> str:
    codes = {
        warning.get("code")
        for warning in outcome.warnings
        if isinstance(warning, dict)
    }
    if SOCIAL_AMBIGUOUS in codes:
        return SOCIAL_AMBIGUOUS
    if SOCIAL_NOT_FOUND in codes:
        return SOCIAL_NOT_FOUND
    if not _has_selected_social(outcome.discovery.get("selectedProfiles")):
        return SOCIAL_NOT_FOUND
    return SOCIAL_AMBIGUOUS


def _warning(
    code: str,
    message: str,
    *,
    stage: str,
    retryable: bool = False,
) -> dict[str, Any]:
    return {
        "code": code,
        "message": message,
        "stage": stage,
        "at": utc_now_iso(),
        "retryable": retryable,
    }


def _needs_review_message(reason: str) -> str:
    return (
        f"M2: paused for human social review ({reason}). "
        "Studio left in needs_social_review; lock released. "
        "No profile was chosen silently."
    )


class Orchestrator:
    """Coordinates one-studio-at-a-time processing."""

    def __init__(
        self,
        config: Config | None = None,
        *,
        studios: StudioRepository | None = None,
        state: StateRepository | None = None,
    ) -> None:
        self.config = config or load_config()
        self.studios = studios or StudioRepository(self.config.data_dir)
        self.state = state or StateRepository(
            self.config.data_dir,
            studio_repo=self.studios,
        )

    def run(
        self,
        studio_id: str,
        *,
        actor: str | None = None,
        http_client: HttpClient | None = None,
        search_provider: SearchProvider | None = None,
        binary_http: BinaryHttp | None = None,
        places_provider: Any | None = None,
    ) -> str:
        owner = actor or f"pipeline:{os.getpid()}"
        client = http_client or StdlibHttpClient(
            timeout=self.config.discovery_http_timeout_seconds,
            max_redirects=self.config.discovery_max_redirects,
        )
        binary = binary_http or StdlibBinaryHttp(
            timeout=self.config.discovery_http_timeout_seconds,
            max_redirects=self.config.discovery_max_redirects,
        )
        search = search_provider or create_search_provider(self.config)
        places = places_provider or create_places_provider(self.config)
        acquired = False
        try:
            self.state.acquire_lock(
                studio_id,
                owner,
                ttl_seconds=DEFAULT_LOCK_TTL_SECONDS,
            )
            acquired = True
            item = self.state.get_item(studio_id)
            if item is None:
                raise PipelineError(
                    INPUT_INVALID,
                    f"no pipeline item for studio {studio_id}",
                )
            status = str(item.get("status") or "")
            if status not in ALLOWED_RUN_STATUSES:
                raise PipelineError(
                    INPUT_INVALID,
                    f"studio {studio_id} is {status}; run accepts queued, "
                    "discovering, needs_social_review, scraping, enriching, "
                    "selecting_media, generating, validating, or ready_for_review",
                )

            if status == "ready_for_review":
                return M4_ALREADY_READY

            last_stage = item.get("lastSuccessfulStage")
            dossier_exists = self.studios.get_dossier(studio_id) is not None
            if self._should_run_m4(status, last_stage, dossier_exists):
                return self._run_m4(studio_id, owner)

            skip_m2 = (
                status in {"scraping", "enriching", "selecting_media"}
                and last_stage in _M2_DONE_STAGES
                and dossier_exists
            )

            if not skip_m2:
                if status == "queued":
                    self.state.transition(
                        studio_id,
                        "discovering",
                        actor=owner,
                        reason="M2 discovery",
                    )
                    status = "discovering"
                elif status == "needs_social_review":
                    self.state.transition(
                        studio_id,
                        "discovering",
                        actor=owner,
                        reason="M2 re-enter discovery",
                    )
                    status = "discovering"

                studio = self.studios.get_studio(studio_id)
                if studio is None:
                    raise PipelineError(
                        INPUT_INVALID,
                        f"studio.json not found for {studio_id}",
                    )

                dossier = self._ensure_dossier(studio_id)
                outcome = discover_profiles(
                    studio,
                    http_client=client,
                    search_provider=search,
                    config=self.config,
                )
                dossier["discovery"] = outcome.discovery
                warnings = list(dossier.get("warnings") or [])
                warnings.extend(outcome.warnings)
                dossier["warnings"] = warnings
                self.studios.save_dossier(dossier)
                self._set_last_successful_stage(studio_id, "discovering")

                selected = outcome.discovery.get("selectedProfiles") or {}
                if outcome.discovery.get("requiresHumanReview") or not _has_selected_social(
                    selected
                ):
                    reason = _review_reason(outcome)
                    if status == "scraping":
                        # Plan §7: scraping → needs_social_review is not allowed.
                        return (
                            f"M2: discovery needs review ({reason}). "
                            "Studio left in scraping; lock released. "
                            "scraping→needs_social_review is not a legal transition. "
                            "No profile was chosen silently."
                        )
                    self.state.transition(
                        studio_id,
                        "needs_social_review",
                        actor=owner,
                        reason=reason,
                    )
                    return _needs_review_message(reason)

                if status != "scraping":
                    self.state.transition(
                        studio_id,
                        "scraping",
                        actor=owner,
                        reason="M2 scrape",
                    )

                self._scrape_selected(studio_id, selected, client)

            skip_enrich = (
                skip_m2
                and self._last_successful_stage(studio_id) == "enriching"
            )
            return self._run_m3(
                studio_id,
                owner,
                client,
                binary,
                places,
                skip_enrich=skip_enrich,
            )
        finally:
            if acquired:
                self.state.release_lock(studio_id, owner)

    def _last_successful_stage(self, studio_id: str) -> str | None:
        item = self.state.get_item(studio_id)
        if item is None:
            return None
        stage = item.get("lastSuccessfulStage")
        return str(stage) if stage else None

    def _ensure_dossier(self, studio_id: str) -> dict[str, Any]:
        existing = self.studios.get_dossier(studio_id)
        if existing is not None:
            return existing
        dossier = empty_dossier(studio_id)
        self.studios.save_dossier(dossier)
        return dossier

    def _set_last_successful_stage(self, studio_id: str, stage: str) -> None:
        item = self.state.get_item(studio_id)
        if item is None:
            return
        if item.get("lastSuccessfulStage") == stage:
            return
        etag = item.get("updatedAt")
        item["lastSuccessfulStage"] = stage
        self.state.save_item(
            item,
            expected_updated_at=etag if isinstance(etag, str) else None,
        )

    def _advance_status(
        self,
        studio_id: str,
        current: str,
        target: str,
        owner: str,
        reason: str,
    ) -> str:
        if current == target:
            return current
        try:
            from_idx = _STAGE_ORDER.index(current)
            to_idx = _STAGE_ORDER.index(target)
        except ValueError:
            if is_allowed_transition(current, target, owner):
                self.state.transition(
                    studio_id, target, actor=owner, reason=reason
                )
                return target
            return current
        if to_idx <= from_idx:
            return current
        status = current
        for nxt in _STAGE_ORDER[from_idx + 1 : to_idx + 1]:
            if not is_allowed_transition(status, nxt, owner):
                return status
            self.state.transition(studio_id, nxt, actor=owner, reason=reason)
            status = nxt
        return status

    def _should_run_m4(
        self,
        status: str,
        last_stage: object,
        dossier_exists: bool,
    ) -> bool:
        if not dossier_exists:
            return False
        if status in {"generating", "validating"}:
            return True
        stage = str(last_stage or "")
        if stage in {"generating", "validating", "ready_for_review"}:
            return True
        return stage == "selecting_media" and status in {
            "selecting_media",
            "scraping",
            "enriching",
            "generating",
            "validating",
        }

    def _run_m4(self, studio_id: str, owner: str) -> str:
        item = self.state.get_item(studio_id)
        status = str(item.get("status") or "") if item else ""
        dossier = self.studios.get_dossier(studio_id)
        if dossier is None:
            raise PipelineError(
                INPUT_INVALID,
                f"dossier.json not found for {studio_id}",
            )

        asset_paths = collect_asset_paths(dossier)
        expected_hash = compute_input_hash(
            dossier,
            assets=asset_paths,
            prompt_version=PROMPT_VERSION,
        )
        existing = self.studios.get_generated(studio_id)
        last_stage = str((item or {}).get("lastSuccessfulStage") or "")
        skip_generate = (
            isinstance(existing, dict)
            and str(existing.get("inputHash") or "") == expected_hash
        )
        if skip_generate and last_stage == "ready_for_review":
            if status != "ready_for_review":
                self._advance_status(
                    studio_id,
                    status,
                    "ready_for_review",
                    owner,
                    "M4 resume",
                )
            return M4_ALREADY_READY

        status = self._advance_status(
            studio_id, status, "generating", owner, "M4 generate"
        )

        if skip_generate:
            generated = existing
        else:
            generated = self._generate_validated(
                studio_id,
                dossier,
                asset_paths,
                expected_hash,
            )
            try:
                validate_generated(generated, dossier)
            except PipelineError as exc:
                self._save_rejected(studio_id, generated, exc.code, exc.message)
                raise
            self.studios.save_generated(generated)
            self._set_last_successful_stage(studio_id, "generating")

        item = self.state.get_item(studio_id)
        status = str(item.get("status") or "") if item else status
        status = self._advance_status(
            studio_id, status, "validating", owner, "M4 validate"
        )
        if skip_generate:
            try:
                validate_instance(load_schema("generated"), generated)
            except ValidationError as exc:
                raise PipelineError(
                    AI_OUTPUT_INVALID,
                    f"generated.json schema invalid: {exc.message}",
                ) from exc
            validate_generated(generated, dossier)
        self._assert_assets_exist(studio_id, generated, dossier)
        self._advance_status(
            studio_id,
            status,
            "ready_for_review",
            owner,
            "M4 ready_for_review",
        )
        self._set_last_successful_stage(studio_id, "ready_for_review")
        return M4_READY_FOR_REVIEW

    def _selected_media(self, dossier: dict[str, Any], provider: Any) -> dict[str, Any]:
        media = dossier.get("media") if isinstance(dossier.get("media"), dict) else {}
        selected = [
            item
            for item in (media.get("selected") or [])
            if isinstance(item, dict) and str(item.get("localPath") or "").strip()
        ]
        if selected:
            return {
                "selected": selected,
                "rejected": [
                    item
                    for item in (media.get("candidates") or [])
                    if isinstance(item, dict)
                ],
                "warnings": [],
            }
        return provider.select_media(dossier, list(media.get("candidates") or []))

    def _stamp_generated(
        self,
        generated: dict[str, Any],
        studio_id: str,
        expected_hash: str,
    ) -> dict[str, Any]:
        generated["schemaVersion"] = 1
        generated["studioId"] = studio_id
        generated["inputHash"] = expected_hash
        generated["generationId"] = str(
            generated.get("generationId") or generation_id_for(expected_hash)
        )
        generated["promptVersion"] = str(
            generated.get("promptVersion") or PROMPT_VERSION
        )
        if not str(generated.get("createdAt") or "").strip():
            generated["createdAt"] = utc_now_iso()
        generated.setdefault("warnings", [])
        generated.setdefault("sections", [])
        generated.setdefault("assetPaths", [])
        generated.setdefault("factualClaims", [])
        return generated

    def _generate_validated(
        self,
        studio_id: str,
        dossier: dict[str, Any],
        asset_paths: list[str],
        expected_hash: str,
    ) -> dict[str, Any]:
        provider = create_provider(self.config)
        last_invalid: PipelineError | None = None
        for _attempt in range(2):
            try:
                brand = provider.analyze_brand(dossier, asset_paths)
                media = self._selected_media(dossier, provider)
                raw = provider.generate_site(dossier, brand, media)
            except PipelineError as exc:
                if exc.code != AI_OUTPUT_INVALID:
                    raise
                last_invalid = exc
                self._save_rejected(studio_id, {"error": exc.message}, exc.code, exc.message)
                continue
            except Exception as exc:
                raise PipelineError(
                    AI_PROVIDER_ERROR,
                    f"AI provider failed: {exc}",
                ) from exc
            if not isinstance(raw, dict):
                last_invalid = PipelineError(
                    AI_OUTPUT_INVALID,
                    "AI output is not a JSON object",
                )
                self._save_rejected(
                    studio_id, raw, last_invalid.code, last_invalid.message
                )
                continue
            generated = self._stamp_generated(dict(raw), studio_id, expected_hash)
            try:
                validate_instance(load_schema("generated"), generated)
            except ValidationError as exc:
                last_invalid = PipelineError(
                    AI_OUTPUT_INVALID,
                    f"generated.json schema invalid: {exc.message}",
                )
                self._save_rejected(
                    studio_id, generated, last_invalid.code, last_invalid.message
                )
                continue
            return generated
        if last_invalid is None:
            last_invalid = PipelineError(AI_OUTPUT_INVALID, "AI output was invalid")
        raise last_invalid

    def _save_rejected(
        self,
        studio_id: str,
        payload: Any,
        code: str,
        message: str,
    ) -> None:
        path = self.studios.studio_dir(studio_id) / "generated.rejected.json"
        document = {
            "code": code,
            "message": message,
            "rejectedAt": utc_now_iso(),
            "generated": payload if isinstance(payload, dict) else {"raw": str(payload)},
        }
        atomic_write_json(path, document, schema=None)

    def _resolve_asset_file(self, local_path: str, studio_id: str) -> Path | None:
        posix = local_path.replace("\\", "/")
        candidates: list[Path] = []
        raw = Path(local_path)
        if raw.is_absolute():
            candidates.append(raw)
        candidates.extend(
            [
                Path(posix),
                self.config.data_dir / posix,
                repo_root() / posix,
                self.config.assets_dir / posix,
            ]
        )
        marker = f"{studio_id}/"
        if marker in posix:
            suffix = posix.split(marker, 1)[1]
            candidates.append(self.config.assets_dir / studio_id / suffix)
        else:
            candidates.append(self.config.assets_dir / studio_id / Path(posix).name)
        for path in candidates:
            try:
                if path.is_file():
                    return path
            except OSError:
                continue
        return None

    def _assert_assets_exist(
        self,
        studio_id: str,
        generated: dict[str, Any],
        dossier: dict[str, Any],
    ) -> None:
        paths: list[str] = []
        for item in generated.get("assetPaths") or []:
            text = str(item or "").strip()
            if text:
                paths.append(text)
        media = dossier.get("media") if isinstance(dossier.get("media"), dict) else {}
        extras = [media.get("logo"), *(media.get("selected") or [])]
        for item in extras:
            if isinstance(item, dict):
                text = str(item.get("localPath") or "").strip()
                if text:
                    paths.append(text)
        seen: set[str] = set()
        for path in paths:
            if path in seen:
                continue
            seen.add(path)
            if self._resolve_asset_file(path, studio_id) is None:
                raise PipelineError(
                    INPUT_INVALID,
                    f"generated asset path does not exist on disk: {path}",
                )

    def _run_m3(
        self,
        studio_id: str,
        owner: str,
        http_client: HttpClient,
        binary_http: BinaryHttp,
        places_provider: Any,
        *,
        skip_enrich: bool,
    ) -> str:
        item = self.state.get_item(studio_id)
        status = str(item.get("status") or "") if item else ""
        studio = self.studios.get_studio(studio_id)
        if studio is None:
            raise PipelineError(
                INPUT_INVALID,
                f"studio.json not found for {studio_id}",
            )
        dossier = self.studios.get_dossier(studio_id) or empty_dossier(studio_id)

        if not skip_enrich:
            status = self._advance_status(
                studio_id, status, "enriching", owner, "M3 enrich"
            )
            try:
                result = enrich_facts(
                    studio,
                    dossier,
                    http_client=http_client,
                    places_provider=places_provider,
                    config=self.config,
                )
                dossier["facts"] = result["facts"]
                warnings = [
                    item
                    for item in (dossier.get("warnings") or [])
                    if not (isinstance(item, dict) and item.get("stage") == "enriching")
                ]
                warnings.extend(result["warnings"])
                dossier["warnings"] = warnings
            except PipelineError as exc:
                if exc.code not in _M3_SOFT_FAIL:
                    raise
                warnings = list(dossier.get("warnings") or [])
                warnings.append(
                    _warning(
                        exc.code,
                        exc.message,
                        stage="enriching",
                        retryable=exc.code == HTTP_TIMEOUT,
                    )
                )
                dossier["warnings"] = warnings
            self.studios.save_dossier(dossier)
            self._set_last_successful_stage(studio_id, "enriching")

        item = self.state.get_item(studio_id)
        status = str(item.get("status") or "") if item else status
        status = self._advance_status(
            studio_id, status, "selecting_media", owner, "M3 media"
        )
        dossier = self.studios.get_dossier(studio_id) or dossier
        try:
            media = select_assets(
                studio_id,
                dossier,
                assets_dir=self.config.assets_dir,
                http=binary_http,
            )
            dossier["media"] = media
        except PipelineError as exc:
            if exc.code not in _M3_SOFT_FAIL:
                raise
            warnings = list(dossier.get("warnings") or [])
            warnings.append(
                _warning(
                    exc.code,
                    exc.message,
                    stage="selecting_media",
                    retryable=exc.code == HTTP_TIMEOUT,
                )
            )
            dossier["warnings"] = warnings
        self.studios.save_dossier(dossier)
        self._set_last_successful_stage(studio_id, "selecting_media")
        return M3_MEDIA_DONE

    def _scrape_selected(
        self,
        studio_id: str,
        selected: dict[str, Any],
        http_client: HttpClient,
    ) -> None:
        scraper_http = ScraperHttpAdapter(http_client)
        ig_url = _selected_profile_url(selected.get("instagram"))
        fb_url = _selected_profile_url(selected.get("facebook"))
        dossier = self.studios.get_dossier(studio_id) or empty_dossier(studio_id)
        warnings = list(dossier.get("warnings") or [])

        ig = self._scrape_platform(
            scrape_instagram,
            ig_url,
            scraper_http,
            warnings,
        )
        fb = self._scrape_platform(
            scrape_facebook,
            fb_url,
            scraper_http,
            warnings,
        )
        for scrape in (ig, fb):
            if scrape is None:
                continue
            for item in scrape.warnings:
                warnings.append(item.to_dossier())

        dossier["social"] = merge_social(ig, fb)
        dossier["warnings"] = warnings
        self.studios.save_dossier(dossier)
        self._copy_selected_contacts(studio_id, selected)
        self._set_last_successful_stage(studio_id, "scraping")

    def _scrape_platform(
        self,
        scrape_fn: Any,
        url: str | None,
        http: ScraperHttpAdapter,
        warnings: list[dict[str, Any]],
    ) -> Any:
        if not url:
            return None
        try:
            return scrape_fn(url, http)
        except PipelineError as exc:
            if exc.code not in _SCRAPE_SOFT_FAIL:
                raise
            warnings.append(
                _warning(
                    exc.code,
                    exc.message,
                    stage="scraping",
                    retryable=exc.code in _SCRAPE_RETRYABLE,
                )
            )
            return None

    def _copy_selected_contacts(
        self,
        studio_id: str,
        selected: dict[str, Any],
    ) -> None:
        studio = self.studios.get_studio(studio_id)
        if studio is None:
            return
        contacts = dict(studio.get("contacts") or {})
        changed = False
        for key in ("instagram", "facebook"):
            url = _selected_profile_url(selected.get(key))
            if url and not contacts.get(key):
                contacts[key] = url
                changed = True
        if not changed:
            return
        etag = studio.get("updatedAt")
        studio["contacts"] = contacts
        studio["updatedAt"] = utc_now_iso()
        self.studios.save_studio(
            studio,
            expected_updated_at=etag if isinstance(etag, str) else None,
        )
