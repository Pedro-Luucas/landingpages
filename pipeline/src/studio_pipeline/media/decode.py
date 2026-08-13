"""Sniff, validate, and reencode raster bytes. Never treat SVG/HTML as images."""

from __future__ import annotations

import hashlib
import io
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Literal

from PIL import Image, ImageOps, UnidentifiedImageError

from studio_pipeline.errors import ASSET_TOO_LARGE, DOWNLOAD_INVALID

Role = Literal["logo", "photo"]

MIN_PHOTO_SHORT_SIDE = 200
MIN_PHOTO_BYTES = 8 * 1024
MIN_LOGO_SHORT_SIDE = 32
AHASH_SIZE = 8

_JPEG_MAGIC = b"\xff\xd8\xff"
_PNG_MAGIC = b"\x89PNG\r\n\x1a\n"
_GIF87 = b"GIF87a"
_GIF89 = b"GIF89a"

_RASTER_DECLARED = {
    "image/jpeg": "image/jpeg",
    "image/jpg": "image/jpeg",
    "image/pjpeg": "image/jpeg",
    "image/png": "image/png",
    "image/gif": "image/gif",
    "image/webp": "image/webp",
}

_GENERIC_DECLARED = frozenset(
    {
        "",
        "application/octet-stream",
        "binary/octet-stream",
        "application/binary",
    }
)


@dataclass(frozen=True)
class DecodedRaster:
    image: Image.Image
    sniffed_mime: str
    width: int
    height: int


@dataclass(frozen=True)
class StoredRaster:
    body: bytes
    mime: str
    ext: str
    width: int
    height: int
    sha256: str
    ahash: int


def header_content_type(headers: Mapping[str, str] | None) -> str:
    if not headers:
        return ""
    for key, value in headers.items():
        if str(key).lower() == "content-type":
            return str(value).split(";", 1)[0].strip().lower()
    return ""


def sniff_raster_mime(body: bytes) -> str | None:
    if body.startswith(_PNG_MAGIC):
        return "image/png"
    if body.startswith(_JPEG_MAGIC):
        return "image/jpeg"
    if body.startswith(_GIF87) or body.startswith(_GIF89):
        return "image/gif"
    if len(body) >= 12 and body[:4] == b"RIFF" and body[8:12] == b"WEBP":
        return "image/webp"
    return None


def looks_like_svg(body: bytes, content_type: str) -> bool:
    if "svg" in content_type:
        return True
    head = body.lstrip()[:512].lower()
    if head.startswith(b"<svg"):
        return True
    return head.startswith(b"<?xml") and b"<svg" in head


def looks_like_html(body: bytes, content_type: str) -> bool:
    if "text/html" in content_type or "application/xhtml" in content_type:
        return True
    head = body.lstrip()[:64].lower()
    return head.startswith(b"<!doctype html") or head.startswith(b"<html")


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def average_hash(image: Image.Image, hash_size: int = AHASH_SIZE) -> int:
    gray = image.convert("L").resize((hash_size, hash_size), Image.Resampling.LANCZOS)
    pixels = list(gray.tobytes())
    avg = sum(pixels) / len(pixels)
    bits = 0
    for index, value in enumerate(pixels):
        if value >= avg:
            bits |= 1 << index
    return bits


def hamming_distance(left: int, right: int) -> int:
    return (left ^ right).bit_count()


def reject_non_raster(body: bytes, content_type: str) -> str | None:
    """Return DOWNLOAD_INVALID message if SVG/HTML, else None."""
    if looks_like_svg(body, content_type):
        return "SVG is not a raster image"
    if looks_like_html(body, content_type):
        return "HTML is not a raster image"
    return None


def validate_download(
    body: bytes,
    headers: Mapping[str, str] | None,
    *,
    role: Role,
    max_bytes: int,
) -> tuple[DecodedRaster | None, str | None, str]:
    """Return (decoded, error_code, message). error_code is set on failure."""
    content_type = header_content_type(headers)
    if not body:
        return None, DOWNLOAD_INVALID, "empty body"
    if len(body) > max_bytes:
        return None, ASSET_TOO_LARGE, f"body is {len(body)} bytes (cap {max_bytes})"

    non_raster = reject_non_raster(body, content_type)
    if non_raster:
        return None, DOWNLOAD_INVALID, non_raster

    sniffed = sniff_raster_mime(body)
    declared = _RASTER_DECLARED.get(content_type)
    if content_type and content_type not in _GENERIC_DECLARED and declared is None:
        if content_type.startswith("image/"):
            return None, DOWNLOAD_INVALID, f"unexpected MIME {content_type}"
        if content_type.startswith("text/") or content_type.startswith("application/"):
            return None, DOWNLOAD_INVALID, f"unexpected MIME {content_type}"

    if declared and sniffed and declared != sniffed:
        return None, DOWNLOAD_INVALID, f"MIME {content_type} does not match file signature {sniffed}"
    if declared and sniffed is None:
        return None, DOWNLOAD_INVALID, f"MIME {content_type} does not match file signature"

    if sniffed is None:
        return None, DOWNLOAD_INVALID, "unrecognized image signature"

    try:
        with Image.open(io.BytesIO(body)) as probe:
            probe.verify()
        with Image.open(io.BytesIO(body)) as img:
            img.load()
            transposed = ImageOps.exif_transpose(img)
            image = (transposed or img).copy()
            if image.mode == "P":
                image = image.convert("RGBA" if "transparency" in img.info else "RGB")
            elif image.mode == "CMYK":
                image = image.convert("RGB")
            width, height = image.size
    except (UnidentifiedImageError, OSError, ValueError, SyntaxError):
        return None, DOWNLOAD_INVALID, "corrupted or unreadable image bytes"

    if width < 1 or height < 1:
        return None, DOWNLOAD_INVALID, "image has no dimensions"

    short = min(width, height)
    if role == "logo":
        if short < MIN_LOGO_SHORT_SIDE:
            return None, DOWNLOAD_INVALID, f"logo short side {short}px is below {MIN_LOGO_SHORT_SIDE}px"
    else:
        if short < MIN_PHOTO_SHORT_SIDE:
            return None, DOWNLOAD_INVALID, f"short side {short}px is below {MIN_PHOTO_SHORT_SIDE}px"
        if len(body) < MIN_PHOTO_BYTES:
            return None, DOWNLOAD_INVALID, f"photo is {len(body)} bytes (minimum {MIN_PHOTO_BYTES})"

    decoded = DecodedRaster(
        image=image,
        sniffed_mime=sniffed,
        width=width,
        height=height,
    )
    return decoded, None, ""


def _has_alpha(image: Image.Image) -> bool:
    if image.mode in {"RGBA", "LA"}:
        extrema = image.getchannel("A").getextrema()
        return extrema is not None and extrema[0] < 255
    return False


def reencode(decoded: DecodedRaster) -> StoredRaster:
    image = decoded.image
    use_png = decoded.sniffed_mime == "image/png" or _has_alpha(image)
    buffer = io.BytesIO()
    if use_png:
        out = image.convert("RGBA") if _has_alpha(image) or image.mode == "RGBA" else image.convert("RGB")
        out.save(buffer, format="PNG", optimize=True)
        mime = "image/png"
        ext = "png"
        stored = out
    else:
        out = image.convert("RGB")
        out.save(buffer, format="JPEG", quality=90, optimize=True)
        mime = "image/jpeg"
        ext = "jpg"
        stored = out
    body = buffer.getvalue()
    width, height = stored.size
    return StoredRaster(
        body=body,
        mime=mime,
        ext=ext,
        width=width,
        height=height,
        sha256=sha256_hex(body),
        ahash=average_hash(stored),
    )
