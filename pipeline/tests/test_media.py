"""M3 media download and selection. Fixtures only; never the network."""

from __future__ import annotations

import hashlib
import io
import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw

from studio_pipeline.config import repo_root, schemas_dir
from studio_pipeline.errors import ASSET_TOO_LARGE, DOWNLOAD_INVALID
from studio_pipeline.media import select_assets
from studio_pipeline.media.decode import sniff_raster_mime
from studio_pipeline.validation.schemas import load_json, make_validator

FIXTURES = Path(__file__).parent / "fixtures" / "media"
STUDIO_ID = "aurora-sound-lab-cwb"
NOW = "2026-08-12T16:20:00Z"
CDN = "https://cdn.aurorasoundlab.example"

PROFILE_URL = f"{CDN}/profile.png"
PHOTO_A = f"{CDN}/posts/1001.jpg"
PHOTO_B = f"{CDN}/posts/1002.jpg"
PHOTO_C = f"{CDN}/posts/1003.jpg"
PHOTO_A_DUP = f"{CDN}/posts/1001-copy.jpg"
SVG_URL = f"{CDN}/mark.svg"
HTML_URL = f"{CDN}/og.html"
VIDEO_URL = f"{CDN}/reels/9.mp4"
THUMB_URL = f"{CDN}/reels/9.jpg"
MISMATCH_URL = f"{CDN}/posts/mismatch.jpg"
CORRUPT_URL = f"{CDN}/posts/broken.jpg"
OVERSIZE_URL = f"{CDN}/posts/huge.jpg"


class FakeBinaryHttp:
    """Maps URL → bytes. Raises if an unmapped URL is requested (no network)."""

    def __init__(self, routes: dict[str, bytes | tuple[int, Mapping[str, str], bytes, str]]):
        self.routes = dict(routes)
        self.calls: list[str] = []

    def get_bytes(self, url: str) -> tuple[int, Mapping[str, str], bytes, str]:
        self.calls.append(url)
        item = self.routes.get(url)
        if item is None:
            raise AssertionError(f"unexpected URL (no network): {url}")
        if isinstance(item, tuple):
            return item
        mime = sniff_raster_mime(item) or "application/octet-stream"
        head = item.lstrip()[:64].lower()
        if head.startswith(b"<svg") or (head.startswith(b"<?xml") and b"<svg" in item[:512].lower()):
            mime = "image/svg+xml"
        elif head.startswith(b"<!doctype html") or head.startswith(b"<html"):
            mime = "text/html"
        return 200, {"Content-Type": mime}, item, url


def _bytes(name: str) -> bytes:
    return (FIXTURES / name).read_bytes()


def _assets_dir(tmp_path: Path) -> Path:
    path = tmp_path / "public" / "studios"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _post(external_id: str, url: str, media: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "externalId": external_id,
        "url": f"https://www.instagram.com/p/{external_id}/",
        "media": media,
        "collectedAt": NOW,
    }


def _dossier(
    *,
    profile: str | None = PROFILE_URL,
    posts: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    social: dict[str, Any] = {"highlights": [], "posts": posts or []}
    if profile:
        social["profileImage"] = {
            "value": profile,
            "sourceUrl": "https://www.instagram.com/aurorasoundlab.cwb/",
            "sourceType": "instagram",
            "collectedAt": NOW,
            "confidence": 0.9,
        }
    return {
        "schemaVersion": 1,
        "studioId": STUDIO_ID,
        "social": social,
        "media": {"candidates": [], "selected": []},
        "warnings": [],
    }


def _media_validator():
    schema = load_json(schemas_dir() / "dossier.schema.json")
    fragment = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$defs": schema["$defs"],
        **schema["$defs"]["Media"],
    }
    return make_validator(fragment)


def _assert_valid_media(media: dict[str, Any]) -> None:
    _media_validator().validate(media)


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _unique_jpeg(index: int) -> bytes:
    image = Image.new("RGB", (640, 480), (12 + index, 40, 80 + index * 3))
    draw = ImageDraw.Draw(image)
    left = 20 + (index % 8) * 70
    draw.rectangle([left, 40, left + 90, 400], fill=(200, 30 + index * 10, 40))
    draw.rectangle([40, 20 + index * 18, 600, 50 + index * 18], fill=(40, 180, 90 + index))
    buffer = io.BytesIO()
    image.save(buffer, format="JPEG", quality=90)
    return buffer.getvalue()


def _near_jpeg(variant: int) -> bytes:
    image = Image.new("RGB", (640, 480), (30, 80, 120))
    draw = ImageDraw.Draw(image)
    draw.rectangle([80, 60, 560, 420], fill=(180, 90, 40))
    draw.rectangle([0, 0, 28, 28], fill=(variant, 12, 12))
    buffer = io.BytesIO()
    image.save(buffer, format="JPEG", quality=90)
    return buffer.getvalue()


def test_logo_downloaded_from_profile_image(tmp_path: Path) -> None:
    png = _bytes("logo.png")
    http = FakeBinaryHttp({PROFILE_URL: png})
    dossier = _dossier(posts=[])
    assets_dir = _assets_dir(tmp_path)

    media = select_assets(STUDIO_ID, dossier, assets_dir=assets_dir, http=http)

    assert media["logo"]["sourceUrl"] == PROFILE_URL
    assert media["logo"]["localPath"] == f"public/studios/{STUDIO_ID}/logo.png"
    assert media["logo"]["mime"] == "image/png"
    assert len(media["logo"]["sha256"]) == 64
    logo_path = assets_dir / STUDIO_ID / "logo.png"
    assert logo_path.is_file()
    stored = logo_path.read_bytes()
    assert stored.startswith(b"\x89PNG")
    assert media["logo"]["sha256"] == _sha256(stored)
    assert media["logo"]["sizeBytes"] == len(stored)
    assert "score" not in media["logo"]
    _assert_valid_media(media)
    assert http.calls == [PROFILE_URL]
    assert logo_path.resolve().is_relative_to(tmp_path.resolve())
    assert not (repo_root() / "public" / "studios" / STUDIO_ID).exists()


def test_svg_and_html_rejected(tmp_path: Path) -> None:
    http = FakeBinaryHttp(
        {
            PROFILE_URL: _bytes("logo.png"),
            SVG_URL: _bytes("icon.svg"),
            HTML_URL: _bytes("page.html"),
            PHOTO_A: _bytes("photo_a.jpg"),
        }
    )
    dossier = _dossier(
        posts=[
            _post("svg1", SVG_URL, [{"url": SVG_URL, "type": "image"}]),
            _post("html1", HTML_URL, [{"url": HTML_URL, "type": "image"}]),
            _post("ok1", PHOTO_A, [{"url": PHOTO_A, "type": "image"}]),
        ]
    )
    media = select_assets(STUDIO_ID, dossier, assets_dir=_assets_dir(tmp_path), http=http)

    selected_urls = [item["sourceUrl"] for item in media["selected"]]
    assert SVG_URL not in selected_urls
    assert HTML_URL not in selected_urls
    assert selected_urls == [PHOTO_A]
    codes = [item["code"] for item in dossier["warnings"]]
    assert codes.count(DOWNLOAD_INVALID) >= 2
    _assert_valid_media(media)


def test_oversized_rejected(tmp_path: Path) -> None:
    huge = b"\xff\xd8\xff" + b"\x00" * (8 * 1024 * 1024)
    http = FakeBinaryHttp(
        {
            PROFILE_URL: _bytes("logo.png"),
            OVERSIZE_URL: huge,
            PHOTO_A: _bytes("photo_a.jpg"),
        }
    )
    dossier = _dossier(
        posts=[
            _post("huge", OVERSIZE_URL, [{"url": OVERSIZE_URL, "type": "image"}]),
            _post("ok", PHOTO_A, [{"url": PHOTO_A, "type": "image"}]),
        ]
    )
    media = select_assets(STUDIO_ID, dossier, assets_dir=_assets_dir(tmp_path), http=http)

    assert [item["sourceUrl"] for item in media["selected"]] == [PHOTO_A]
    assert any(item["code"] == ASSET_TOO_LARGE for item in dossier["warnings"])
    _assert_valid_media(media)


def test_duplicate_sha256_not_selected_twice(tmp_path: Path) -> None:
    photo = _bytes("photo_a.jpg")
    http = FakeBinaryHttp(
        {
            PROFILE_URL: _bytes("logo.png"),
            PHOTO_A: photo,
            PHOTO_A_DUP: photo,
            PHOTO_B: _bytes("photo_b.jpg"),
        }
    )
    dossier = _dossier(
        posts=[
            _post("a", PHOTO_A, [{"url": PHOTO_A, "type": "image"}]),
            _post("a2", PHOTO_A_DUP, [{"url": PHOTO_A_DUP, "type": "image"}]),
            _post("b", PHOTO_B, [{"url": PHOTO_B, "type": "image"}]),
        ]
    )
    media = select_assets(STUDIO_ID, dossier, assets_dir=_assets_dir(tmp_path), http=http)

    selected_urls = [item["sourceUrl"] for item in media["selected"]]
    assert PHOTO_A in selected_urls
    assert PHOTO_B in selected_urls
    assert PHOTO_A_DUP not in selected_urls
    shas = [item["sha256"] for item in media["selected"]]
    assert len(shas) == len(set(shas))
    _assert_valid_media(media)


def test_caps_selected_photos_at_ten(tmp_path: Path) -> None:
    routes: dict[str, bytes] = {PROFILE_URL: _bytes("logo.png")}
    posts: list[dict[str, Any]] = []
    for index in range(11):
        url = f"{CDN}/posts/cap-{index:02d}.jpg"
        routes[url] = _unique_jpeg(index)
        posts.append(_post(f"cap{index}", url, [{"url": url, "type": "image"}]))
    http = FakeBinaryHttp(routes)
    media = select_assets(
        STUDIO_ID,
        _dossier(posts=posts),
        assets_dir=_assets_dir(tmp_path),
        http=http,
    )
    assert len(media["selected"]) == 10
    assert len(media["candidates"]) == 11
    _assert_valid_media(media)


def test_perceptual_near_duplicate_is_not_selected_twice(tmp_path: Path) -> None:
    near_a = f"{CDN}/posts/near-a.jpg"
    near_b = f"{CDN}/posts/near-b.jpg"
    distinct = f"{CDN}/posts/near-c.jpg"
    http = FakeBinaryHttp(
        {
            PROFILE_URL: _bytes("logo.png"),
            near_a: _near_jpeg(20),
            near_b: _near_jpeg(200),
            distinct: _unique_jpeg(7),
        }
    )
    dossier = _dossier(
        posts=[
            _post("na", near_a, [{"url": near_a, "type": "image"}]),
            _post("nb", near_b, [{"url": near_b, "type": "image"}]),
            _post("nc", distinct, [{"url": distinct, "type": "image"}]),
        ]
    )
    media = select_assets(STUDIO_ID, dossier, assets_dir=_assets_dir(tmp_path), http=http)
    selected_urls = [item["sourceUrl"] for item in media["selected"]]
    assert near_a in selected_urls
    assert distinct in selected_urls
    assert near_b not in selected_urls
    flagged = next(item for item in media["candidates"] if item["sourceUrl"] == near_b)
    assert "near_duplicate" in flagged["flags"]
    _assert_valid_media(media)


def test_unselected_candidates_are_written_under_tmpdir(tmp_path: Path) -> None:
    http = FakeBinaryHttp(
        {
            PROFILE_URL: _bytes("logo.png"),
            PHOTO_A: _bytes("photo_a.jpg"),
            PHOTO_B: _bytes("photo_b.jpg"),
            PHOTO_C: _bytes("photo_c.jpg"),
        }
    )
    dossier = _dossier(
        posts=[
            _post("a", PHOTO_A, [{"url": PHOTO_A, "type": "image"}]),
            _post("b", PHOTO_B, [{"url": PHOTO_B, "type": "image"}]),
            _post("c", PHOTO_C, [{"url": PHOTO_C, "type": "image"}]),
        ]
    )
    assets_dir = _assets_dir(tmp_path)
    media = select_assets(
        STUDIO_ID,
        dossier,
        assets_dir=assets_dir,
        http=http,
        max_selected=1,
    )
    assert len(media["selected"]) == 1
    studio_dir = assets_dir / STUDIO_ID
    for item in media["candidates"]:
        relative = item["localPath"].split(f"{STUDIO_ID}/", 1)[-1]
        path = studio_dir / relative
        assert path.is_file(), item["localPath"]
        assert path.resolve().is_relative_to(tmp_path.resolve())
    assert not (repo_root() / "public" / "studios" / STUDIO_ID).exists()
    _assert_valid_media(media)


def test_three_valid_images_selects_three(tmp_path: Path) -> None:
    http = FakeBinaryHttp(
        {
            PROFILE_URL: _bytes("logo.png"),
            PHOTO_A: _bytes("photo_a.jpg"),
            PHOTO_B: _bytes("photo_b.jpg"),
            PHOTO_C: _bytes("photo_c.jpg"),
        }
    )
    dossier = _dossier(
        posts=[
            _post("a", PHOTO_A, [{"url": PHOTO_A, "type": "image"}]),
            _post("b", PHOTO_B, [{"url": PHOTO_B, "type": "image"}]),
            _post("c", PHOTO_C, [{"url": PHOTO_C, "type": "image"}]),
        ]
    )
    media = select_assets(STUDIO_ID, dossier, assets_dir=_assets_dir(tmp_path), http=http)

    assert len(media["selected"]) == 3
    for item in media["selected"]:
        assert "score" not in item
        assert "flags" not in item
        assert "qualityScore" not in item
        assert "usableAsHero" not in item
    for item in media["candidates"]:
        assert "score" in item
    _assert_valid_media(media)


def test_manifest_lists_files_and_hashes(tmp_path: Path) -> None:
    http = FakeBinaryHttp(
        {
            PROFILE_URL: _bytes("logo.png"),
            PHOTO_A: _bytes("photo_a.jpg"),
            PHOTO_B: _bytes("photo_b.jpg"),
        }
    )
    dossier = _dossier(
        posts=[
            _post("a", PHOTO_A, [{"url": PHOTO_A, "type": "image"}]),
            _post("b", PHOTO_B, [{"url": PHOTO_B, "type": "image"}]),
        ]
    )
    assets_dir = _assets_dir(tmp_path)
    media = select_assets(STUDIO_ID, dossier, assets_dir=assets_dir, http=http)

    manifest_path = assets_dir / STUDIO_ID / "manifest.json"
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    paths = [item["path"] for item in payload["files"]]
    assert "logo.png" in paths
    assert "images/01.jpg" in paths
    assert "images/02.jpg" in paths
    by_path = {item["path"]: item for item in payload["files"]}
    logo_bytes = (assets_dir / STUDIO_ID / "logo.png").read_bytes()
    assert by_path["logo.png"]["sha256"] == _sha256(logo_bytes)
    assert by_path["logo.png"]["sha256"] == media["logo"]["sha256"]
    one = (assets_dir / STUDIO_ID / "images" / "01.jpg").read_bytes()
    assert by_path["images/01.jpg"]["sha256"] == _sha256(one)
    assert not any(item["path"].endswith(".tmp") for item in payload["files"])


def test_leftover_tmp_is_not_a_final_asset(tmp_path: Path) -> None:
    assets_dir = _assets_dir(tmp_path)
    studio_dir = assets_dir / STUDIO_ID
    (studio_dir / "images").mkdir(parents=True)
    leftover_logo = studio_dir / "logo.png.tmp"
    leftover_logo.write_bytes(b"not-an-image")
    leftover_image = studio_dir / "images" / "01.jpg.tmp"
    leftover_image.write_bytes(b"also-not-an-image")
    keep = studio_dir / "notes.txt"
    keep.write_text("do not delete", encoding="utf-8")

    http = FakeBinaryHttp(
        {
            PROFILE_URL: _bytes("logo.png"),
            PHOTO_A: _bytes("photo_a.jpg"),
        }
    )
    dossier = _dossier(posts=[_post("a", PHOTO_A, [{"url": PHOTO_A, "type": "image"}])])
    media = select_assets(STUDIO_ID, dossier, assets_dir=assets_dir, http=http)

    assert not leftover_logo.exists()
    assert not leftover_image.exists()
    assert keep.is_file()
    assert keep.read_text(encoding="utf-8") == "do not delete"
    manifest = json.loads((studio_dir / "manifest.json").read_text(encoding="utf-8"))
    assert all(not item["path"].endswith(".tmp") for item in manifest["files"])
    assert media["logo"]["localPath"].endswith("logo.png")
    assert not media["logo"]["localPath"].endswith(".tmp")
    _assert_valid_media(media)


def test_reel_without_still_is_skipped(tmp_path: Path) -> None:
    http = FakeBinaryHttp(
        {
            PROFILE_URL: _bytes("logo.png"),
            PHOTO_A: _bytes("photo_a.jpg"),
            THUMB_URL: _bytes("photo_b.jpg"),
        }
    )
    dossier = _dossier(
        posts=[
            _post("reel1", VIDEO_URL, [{"url": VIDEO_URL, "type": "video"}]),
            _post(
                "reel2",
                VIDEO_URL,
                [
                    {
                        "url": VIDEO_URL,
                        "type": "video",
                        "selectable_photo": False,
                        "flags": ["reel_without_still"],
                    },
                    {"url": THUMB_URL, "type": "image", "selectable_photo": True},
                ],
            ),
            _post("still", PHOTO_A, [{"url": PHOTO_A, "type": "image"}]),
        ]
    )
    media = select_assets(STUDIO_ID, dossier, assets_dir=_assets_dir(tmp_path), http=http)

    assert VIDEO_URL not in http.calls
    selected_urls = [item["sourceUrl"] for item in media["selected"]]
    assert VIDEO_URL not in selected_urls
    assert THUMB_URL in selected_urls
    assert PHOTO_A in selected_urls
    _assert_valid_media(media)


def test_mime_mismatch_and_corrupt_rejected(tmp_path: Path) -> None:
    jpeg = _bytes("photo_a.jpg")
    http = FakeBinaryHttp(
        {
            PROFILE_URL: _bytes("logo.png"),
            MISMATCH_URL: (
                200,
                {"Content-Type": "image/png"},
                jpeg,
                MISMATCH_URL,
            ),
            CORRUPT_URL: (
                200,
                {"Content-Type": "image/jpeg"},
                b"\xff\xd8\xff\xe0" + b"not-a-jpeg-payload",
                CORRUPT_URL,
            ),
            PHOTO_B: _bytes("photo_b.jpg"),
        }
    )
    dossier = _dossier(
        posts=[
            _post("bad1", MISMATCH_URL, [{"url": MISMATCH_URL, "type": "image"}]),
            _post("bad2", CORRUPT_URL, [{"url": CORRUPT_URL, "type": "image"}]),
            _post("ok", PHOTO_B, [{"url": PHOTO_B, "type": "image"}]),
        ]
    )
    media = select_assets(STUDIO_ID, dossier, assets_dir=_assets_dir(tmp_path), http=http)

    selected_urls = [item["sourceUrl"] for item in media["selected"]]
    assert selected_urls == [PHOTO_B]
    assert all(item["code"] == DOWNLOAD_INVALID for item in dossier["warnings"] if item["code"] != "HTTP_NOT_FOUND")
    codes = [item["code"] for item in dossier["warnings"]]
    assert codes.count(DOWNLOAD_INVALID) >= 2
    _assert_valid_media(media)
