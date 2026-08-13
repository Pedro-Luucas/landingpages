"""Download logo and select up to 10 varied raster photos (plan §8 etapa E)."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from studio_pipeline.clock import utc_now_iso
from studio_pipeline.errors import DOWNLOAD_INVALID, HTTP_NOT_FOUND, HTTP_TIMEOUT
from studio_pipeline.media.decode import (
    StoredRaster,
    hamming_distance,
    reencode,
    validate_download,
)
from studio_pipeline.media.http import BinaryHttp
from studio_pipeline.media.store import (
    atomic_write_bytes,
    cleanup_tmp_files,
    dossier_local_path,
    safe_studio_id,
    studio_asset_dir,
    write_manifest,
)

DEFAULT_MAX_SELECTED = 10
DEFAULT_MAX_BYTES = 8 * 1024 * 1024
MAX_POST_MEDIA_URLS = 30
NEAR_DUPLICATE_HAMMING = 8
STAGE = "selecting_media"


@dataclass
class _Prepared:
    source_url: str
    stored: StoredRaster
    index: int
    score: float = 0.0
    quality_score: float = 0.0
    relevance_score: float = 0.0
    flags: list[str] = field(default_factory=list)
    usable_as_hero: bool = False
    usable_as_gallery: bool = True
    local_rel: str = ""


def select_assets(
    studio_id: str,
    dossier: dict,
    *,
    assets_dir: Path,
    http: BinaryHttp,
    max_selected: int = DEFAULT_MAX_SELECTED,
    max_bytes: int = DEFAULT_MAX_BYTES,
) -> dict:
    """Return updated dossier['media'] (logo, candidates, selected). Writes files. Does not save dossier.json."""
    studio_id = safe_studio_id(studio_id)
    assets_dir = Path(assets_dir)
    studio_dir = studio_asset_dir(assets_dir, studio_id)
    studio_dir.mkdir(parents=True, exist_ok=True)
    (studio_dir / "images").mkdir(parents=True, exist_ok=True)
    cleanup_tmp_files(studio_dir)

    collected_at = utc_now_iso()
    warnings = [
        item
        for item in (dossier.get("warnings") or [])
        if not (isinstance(item, dict) and item.get("stage") == STAGE)
    ]
    raw_cache: dict[str, tuple[int, Mapping[str, str], bytes] | dict[str, Any]] = {}

    logo_asset: dict[str, Any] | None = None
    profile_url = _profile_image_url(dossier)
    if profile_url:
        stored, warning = _fetch_raster(
            profile_url,
            http=http,
            role="logo",
            max_bytes=max_bytes,
            raw_cache=raw_cache,
            collected_at=collected_at,
        )
        if warning:
            warnings.append(warning)
        elif stored is not None:
            rel = f"logo.{stored.ext}"
            atomic_write_bytes(studio_dir / rel, stored.body)
            logo_asset = _downloaded_asset(
                source_url=profile_url,
                stored=stored,
                local_path=dossier_local_path(assets_dir, studio_id, rel),
                collected_at=collected_at,
                license_or_use="public-profile-image",
            )

    prepared: list[_Prepared] = []
    seen_sha: set[str] = set()
    seen_url: set[str] = set()
    for index, url in enumerate(_post_media_urls(dossier)):
        if url in seen_url:
            continue
        seen_url.add(url)
        stored, warning = _fetch_raster(
            url,
            http=http,
            role="photo",
            max_bytes=max_bytes,
            raw_cache=raw_cache,
            collected_at=collected_at,
        )
        if warning:
            warnings.append(warning)
            continue
        if stored is None:
            continue
        if stored.sha256 in seen_sha:
            continue
        seen_sha.add(stored.sha256)
        item = _Prepared(source_url=url, stored=stored, index=index)
        _score_photo(item)
        prepared.append(item)

    chosen = _pick_diverse(prepared, max_selected=max(0, max_selected))
    chosen_ids = {id(item) for item in chosen}

    selected: list[dict[str, Any]] = []
    for position, item in enumerate(chosen, start=1):
        rel = f"images/{position:02d}.{item.stored.ext}"
        item.local_rel = rel
        atomic_write_bytes(studio_dir / rel, item.stored.body)
        selected.append(
            _downloaded_asset(
                source_url=item.source_url,
                stored=item.stored,
                local_path=dossier_local_path(assets_dir, studio_id, rel),
                collected_at=collected_at,
                license_or_use="public-post-image",
            )
        )

    candidates: list[dict[str, Any]] = []
    for item in prepared:
        if id(item) not in chosen_ids and not item.local_rel:
            item.local_rel = f"images/{item.stored.sha256[:12]}.{item.stored.ext}"
            atomic_write_bytes(studio_dir / item.local_rel, item.stored.body)
        rel = item.local_rel or f"images/{item.stored.sha256[:12]}.{item.stored.ext}"
        asset = _downloaded_asset(
            source_url=item.source_url,
            stored=item.stored,
            local_path=dossier_local_path(assets_dir, studio_id, rel),
            collected_at=collected_at,
            license_or_use="public-post-image",
        )
        candidates.append(_candidate_asset(asset, item))

    media: dict[str, Any] = {"candidates": candidates, "selected": selected}
    if logo_asset is not None:
        media["logo"] = logo_asset

    write_manifest(
        studio_dir,
        {
            "studioId": studio_id,
            "generatedAt": collected_at,
            "files": _manifest_files(logo_asset, selected),
        },
    )
    cleanup_tmp_files(studio_dir)

    dossier["media"] = media
    dossier["warnings"] = warnings
    return media


def _profile_image_url(dossier: Mapping[str, Any]) -> str | None:
    social = dossier.get("social") or {}
    profile = social.get("profileImage")
    if isinstance(profile, str) and profile.strip():
        return profile.strip()
    if isinstance(profile, dict):
        value = profile.get("value")
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _post_media_urls(dossier: Mapping[str, Any]) -> list[str]:
    social = dossier.get("social") or {}
    posts = social.get("posts") or []
    urls: list[str] = []
    for post in posts:
        if not isinstance(post, dict):
            continue
        for item in post.get("media") or []:
            if len(urls) >= MAX_POST_MEDIA_URLS:
                return urls
            if not isinstance(item, dict):
                continue
            if not _is_selectable_photo(item):
                continue
            url = str(item.get("url") or "").strip()
            if url:
                urls.append(url)
    return urls


def _is_selectable_photo(item: Mapping[str, Any]) -> bool:
    if "selectable_photo" in item:
        return bool(item["selectable_photo"])
    flags = item.get("flags") or []
    if isinstance(flags, str):
        flags = [flags]
    if "reel_without_still" in flags:
        return False
    if item.get("type") == "video":
        return False
    return True


def _fetch_raster(
    url: str,
    *,
    http: BinaryHttp,
    role: str,
    max_bytes: int,
    raw_cache: dict[str, tuple[int, Mapping[str, str], bytes] | dict[str, Any]],
    collected_at: str,
) -> tuple[StoredRaster | None, dict[str, Any] | None]:
    if _looks_like_markup_url(url):
        return None, _warning(
            DOWNLOAD_INVALID,
            f"{url}: SVG/HTML is not a raster image",
            collected_at,
        )

    cached = raw_cache.get(url)
    if isinstance(cached, dict):
        return None, cached
    if cached is None:
        try:
            status, headers, body, _final = http.get_bytes(url)
        except Exception as exc:
            warning = _warning(
                HTTP_TIMEOUT,
                f"Fetch failed for {url}: {exc.__class__.__name__}",
                collected_at,
                retryable=True,
            )
            raw_cache[url] = warning
            return None, warning
        if status == 0:
            warning = _warning(
                HTTP_TIMEOUT, f"Timed out fetching {url}", collected_at, retryable=True
            )
            raw_cache[url] = warning
            return None, warning
        if status < 200 or status >= 300:
            warning = _warning(
                HTTP_NOT_FOUND,
                f"HTTP {status} fetching {url}",
                collected_at,
                retryable=status >= 500,
            )
            raw_cache[url] = warning
            return None, warning
        raw_cache[url] = (status, dict(headers), body)
        cached = raw_cache[url]

    status, headers, body = cached  # type: ignore[misc]
    decoded, code, message = validate_download(
        body,
        headers,
        role="logo" if role == "logo" else "photo",
        max_bytes=max_bytes,
    )
    if code or decoded is None:
        return None, _warning(code or DOWNLOAD_INVALID, f"{url}: {message}", collected_at)

    return reencode(decoded), None


def _looks_like_markup_url(url: str) -> bool:
    path = urlparse(url).path.lower()
    return path.endswith((".html", ".htm", ".xhtml", ".svg", ".svgz"))


def _score_photo(item: _Prepared) -> None:
    stored = item.stored
    short = min(stored.width, stored.height)
    long = max(stored.width, stored.height)
    aspect = (long / short) if short else 99.0
    ratio = (stored.width / stored.height) if stored.height else 99.0

    res_score = min(1.0, short / 1200.0)
    size_score = min(1.0, max(0.0, stored.width * stored.height) / (1_200_000))
    if aspect <= 2.0:
        aspect_score = 1.0
    elif aspect <= 3.0:
        aspect_score = 0.45
    else:
        aspect_score = 0.15
    quality = max(0.0, min(1.0, 0.5 * res_score + 0.3 * size_score + 0.2 * aspect_score))

    relevance = 0.7
    if 0.85 <= ratio <= 1.9:
        relevance = 0.88
    elif 0.6 <= ratio < 0.85:
        relevance = 0.72

    flags: list[str] = []
    if short < 600:
        flags.append("low_resolution")
    if aspect > 2.2:
        flags.append("extreme_aspect")

    item.quality_score = round(quality, 4)
    item.relevance_score = round(relevance, 4)
    item.score = round(max(0.0, min(1.0, 0.65 * quality + 0.35 * relevance)), 4)
    item.usable_as_hero = short >= 600 and 1.05 <= ratio <= 2.1
    item.usable_as_gallery = True
    item.flags = flags


def _pick_diverse(items: list[_Prepared], *, max_selected: int) -> list[_Prepared]:
    if max_selected <= 0 or not items:
        return []
    ranked = sorted(items, key=lambda item: (-item.score, item.index))
    chosen: list[_Prepared] = []
    for item in ranked:
        if any(
            hamming_distance(item.stored.ahash, other.stored.ahash) <= NEAR_DUPLICATE_HAMMING
            for other in chosen
        ):
            if "near_duplicate" not in item.flags:
                item.flags.append("near_duplicate")
            continue
        chosen.append(item)
        if len(chosen) >= max_selected:
            break
    chosen.sort(key=lambda item: item.index)
    return chosen


def _downloaded_asset(
    *,
    source_url: str,
    stored: StoredRaster,
    local_path: str,
    collected_at: str,
    license_or_use: str,
) -> dict[str, Any]:
    return {
        "sourceUrl": source_url,
        "sha256": stored.sha256,
        "mime": stored.mime,
        "sizeBytes": len(stored.body),
        "width": stored.width,
        "height": stored.height,
        "localPath": local_path,
        "licenseOrUse": license_or_use,
        "collectedAt": collected_at,
    }


def _candidate_asset(asset: dict[str, Any], item: _Prepared) -> dict[str, Any]:
    payload = dict(asset)
    payload["score"] = item.score
    payload["qualityScore"] = item.quality_score
    payload["relevanceScore"] = item.relevance_score
    payload["flags"] = list(item.flags)
    payload["usableAsHero"] = item.usable_as_hero
    payload["usableAsGallery"] = item.usable_as_gallery
    return payload


def _manifest_files(
    logo: dict[str, Any] | None,
    selected: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    files: list[dict[str, Any]] = []
    for asset in ([logo] if logo else []) + selected:
        rel = asset["localPath"].rsplit("/", 2)
        if len(rel) >= 2 and rel[-2] == "images":
            path = f"images/{rel[-1]}"
        else:
            path = rel[-1]
        files.append(
            {
                "path": path,
                "sha256": asset["sha256"],
                "mime": asset["mime"],
                "sizeBytes": asset["sizeBytes"],
                "width": asset.get("width"),
                "height": asset.get("height"),
            }
        )
    return files


def _warning(code: str, message: str, collected_at: str, *, retryable: bool = False) -> dict[str, Any]:
    return {
        "code": code,
        "message": message,
        "stage": STAGE,
        "at": collected_at,
        "retryable": retryable,
    }

