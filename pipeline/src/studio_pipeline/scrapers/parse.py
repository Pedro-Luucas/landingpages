"""Parse invented public HTML/JSON fixtures — not proprietary app internals."""

from __future__ import annotations

import json
import re
from html.parser import HTMLParser
from typing import Any
from urllib.parse import urljoin

from studio_pipeline.clock import format_iso, parse_iso
from studio_pipeline.scrapers.models import PostMedia
from studio_pipeline.scrapers.urls import canonicalize_url, is_reel_url

LOGIN_WALL_RE = re.compile(
    r"log in to continue|login to continue|please log in|entre para continuar|"
    r"checkpoint_required|unusual traffic|solve this captcha|confirm you.?re human|"
    r"security check required",
    re.IGNORECASE,
)

_BIO_LD_TYPES = {
    "person",
    "organization",
    "localbusiness",
    "profilepage",
    "musicgroup",
    "place",
}


class ParsedPost:
    __slots__ = ("external_id", "url", "published_at", "caption", "kind", "media")

    def __init__(self) -> None:
        self.external_id = ""
        self.url = ""
        self.published_at: str | None = None
        self.caption: str | None = None
        self.kind = ""
        self.media: list[PostMedia] = []


class ParsedProfile:
    __slots__ = ("bio", "profile_image_url", "highlights", "posts", "login_wall")

    def __init__(self) -> None:
        self.bio: str | None = None
        self.profile_image_url: str | None = None
        self.highlights: list[tuple[str, str | None]] = []
        self.posts: list[ParsedPost] = []
        self.login_wall = False


def parse_public_document(text: str, *, content_type: str = "", base_url: str = "") -> ParsedProfile:
    stripped = (text or "").lstrip()
    if _looks_like_json(stripped, content_type):
        profile = parse_public_json(stripped, base_url=base_url)
    else:
        profile = parse_public_html(text or "", base_url=base_url)
    _detect_login_wall(profile, text or "")
    return profile


def parse_public_json(text: str, *, base_url: str = "") -> ParsedProfile:
    profile = ParsedProfile()
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return profile
    if _looks_like_private_graph(payload):
        return profile
    root = _unwrap_json_root(payload)
    if not isinstance(root, dict):
        return profile
    profile.bio = _clean_text(root.get("bio") or root.get("description"))
    image = root.get("profileImage") or root.get("profileImageUrl") or root.get("image")
    profile.profile_image_url = _abs_url(image, base_url)
    for raw in root.get("highlights") or []:
        if not isinstance(raw, dict):
            continue
        title = _clean_text(raw.get("title"))
        if not title:
            continue
        profile.highlights.append((title, _clean_text(raw.get("text"))))
    for raw in root.get("posts") or []:
        post = _post_from_json(raw, base_url)
        if post is not None:
            profile.posts.append(post)
    return profile


def parse_public_html(text: str, *, base_url: str = "") -> ParsedProfile:
    parser = _PublicHTMLParser(base_url=base_url)
    parser.feed(text)
    parser.close()
    profile = ParsedProfile()
    profile.bio = parser.bio or _clean_text(parser.meta.get("og:description") or parser.meta.get("description"))
    profile.profile_image_url = parser.profile_image or _abs_url(
        parser.meta.get("og:image") or parser.meta.get("og:image:url") or parser.meta.get("og:image:secure_url"),
        base_url,
    )
    profile.highlights = list(parser.highlights)
    profile.posts = list(parser.posts)
    _apply_json_ld(profile, parser.json_ld, base_url)
    return profile


def annotate_selectable_media(posts: list[ParsedPost]) -> None:
    for post in posts:
        reel = post.kind == "reel" or is_reel_url(post.url)
        has_still = any(item.type in {"image", "carousel"} for item in post.media)
        for item in post.media:
            if item.type == "video":
                item.selectable_photo = False
                flags = list(item.flags)
                if "not_selectable_photo" not in flags:
                    flags.append("not_selectable_photo")
                if reel and not has_still and "reel_without_still" not in flags:
                    flags.append("reel_without_still")
                item.flags = tuple(flags)
            else:
                item.selectable_photo = True


def normalize_published_at(value: object) -> str | None:
    text = _clean_text(value)
    if not text:
        return None
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", text):
        text = f"{text}T00:00:00Z"
    try:
        return format_iso(parse_iso(text))
    except (ValueError, TypeError):
        return None


def _detect_login_wall(profile: ParsedProfile, text: str) -> None:
    if profile.bio or profile.posts or profile.profile_image_url or profile.highlights:
        profile.login_wall = False
        return
    profile.login_wall = bool(LOGIN_WALL_RE.search(text))


def _looks_like_json(text: str, content_type: str) -> bool:
    if "json" in (content_type or "").lower():
        return True
    return text.startswith("{") or text.startswith("[")


def _looks_like_private_graph(payload: object) -> bool:
    if not isinstance(payload, dict):
        return False
    keys = {str(key).lower() for key in payload}
    return "access_token" in keys or "oauth" in keys


def _unwrap_json_root(payload: object) -> object:
    if isinstance(payload, dict):
        for key in ("publicProfile", "profile", "page"):
            nested = payload.get(key)
            if isinstance(nested, dict):
                merged = dict(nested)
                if "posts" not in merged and isinstance(payload.get("posts"), list):
                    merged["posts"] = payload["posts"]
                if "highlights" not in merged and isinstance(payload.get("highlights"), list):
                    merged["highlights"] = payload["highlights"]
                return merged
    return payload


def _post_from_json(raw: object, base_url: str) -> ParsedPost | None:
    if not isinstance(raw, dict):
        return None
    post = ParsedPost()
    post.url = _abs_url(raw.get("url") or raw.get("canonicalUrl"), base_url) or ""
    post.external_id = str(raw.get("id") or raw.get("externalId") or _id_from_url(post.url) or "")
    post.published_at = normalize_published_at(raw.get("publishedAt") or raw.get("date"))
    post.caption = _clean_text(raw.get("caption") or raw.get("text"))
    post.kind = str(raw.get("kind") or "").lower()
    media_type = str(raw.get("mediaType") or "").lower()
    for item in raw.get("media") or []:
        post.media.extend(_media_from_json(item, base_url, default_type=media_type))
    thumb = _abs_url(raw.get("thumbnailUrl") or raw.get("thumbnail"), base_url)
    if thumb:
        post.media.append(PostMedia(url=thumb, type="image", selectable_photo=True, flags=("thumbnail",)))
    if not post.url and not post.caption and not post.media:
        return None
    if not post.url:
        post.url = base_url
    if not post.external_id:
        post.external_id = _id_from_url(post.url) or "post"
    annotate_selectable_media([post])
    return post


def _media_from_json(raw: object, base_url: str, *, default_type: str) -> list[PostMedia]:
    if isinstance(raw, str):
        url = _abs_url(raw, base_url)
        if not url:
            return []
        media_type = _infer_media_type(url, default_type)
        return [PostMedia(url=url, type=media_type, selectable_photo=media_type != "video")]
    if not isinstance(raw, dict):
        return []
    url = _abs_url(raw.get("url") or raw.get("src"), base_url)
    items: list[PostMedia] = []
    declared = str(raw.get("type") or default_type or "").lower()
    thumb = _abs_url(raw.get("thumbnailUrl") or raw.get("thumbnail"), base_url)
    if thumb:
        items.append(PostMedia(url=thumb, type="image", selectable_photo=True, flags=("thumbnail",)))
    if url:
        media_type = declared if declared in {"image", "video", "carousel"} else _infer_media_type(url, declared)
        items.append(PostMedia(url=url, type=media_type, selectable_photo=media_type != "video"))
    return items


def _apply_json_ld(profile: ParsedProfile, blobs: list[str], base_url: str) -> None:
    for blob in blobs:
        try:
            payload = json.loads(blob)
        except json.JSONDecodeError:
            continue
        for node in _walk_json(payload):
            if not isinstance(node, dict):
                continue
            types = _ld_types(node)
            if types & _BIO_LD_TYPES:
                if not profile.bio:
                    profile.bio = _clean_text(node.get("description") or node.get("bio"))
                if not profile.profile_image_url:
                    profile.profile_image_url = _ld_image(node, base_url)
            if "itemlist" in types:
                for element in node.get("itemListElement") or []:
                    raw = element.get("item", element) if isinstance(element, dict) else element
                    post = _post_from_json(_ld_post_node(raw), base_url)
                    if post is not None:
                        profile.posts.append(post)


def _ld_post_node(raw: object) -> dict[str, Any]:
    if not isinstance(raw, dict):
        return {}
    return {
        "id": raw.get("@id") or raw.get("identifier"),
        "url": raw.get("url"),
        "caption": raw.get("caption") or raw.get("text") or raw.get("description"),
        "publishedAt": raw.get("datePublished") or raw.get("uploadDate"),
        "media": [{"url": _first_url(raw.get("image") or raw.get("thumbnailUrl")), "type": "image"}]
        if raw.get("image") or raw.get("thumbnailUrl")
        else [],
    }


def _ld_types(node: dict[str, Any]) -> set[str]:
    raw = node.get("@type") or node.get("type") or ""
    if isinstance(raw, list):
        return {str(item).lower() for item in raw}
    return {str(raw).lower()} if raw else set()


def _ld_image(node: dict[str, Any], base_url: str) -> str | None:
    return _abs_url(_first_url(node.get("image") or node.get("logo")), base_url)


def _first_url(value: object) -> str | None:
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        url = value.get("url") or value.get("contentUrl")
        return str(url) if url else None
    if isinstance(value, list) and value:
        return _first_url(value[0])
    return None


def _walk_json(value: object) -> list[object]:
    found: list[object] = []
    stack: list[object] = [value]
    while stack:
        current = stack.pop()
        found.append(current)
        if isinstance(current, dict):
            stack.extend(current.values())
        elif isinstance(current, list):
            stack.extend(current)
    return found


def _clean_text(value: object) -> str | None:
    if value is None:
        return None
    text = " ".join(str(value).split())
    return text or None


def _abs_url(value: object, base_url: str) -> str | None:
    text = _clean_text(value)
    if not text:
        return None
    joined = urljoin(base_url, text) if base_url else text
    try:
        return canonicalize_url(joined)
    except Exception:
        return joined


def _id_from_url(url: str) -> str:
    if not url:
        return ""
    parts = [part for part in canonicalize_url(url).rstrip("/").split("/") if part]
    return parts[-1] if parts else ""


def _infer_media_type(url: str, declared: str) -> str:
    if declared in {"image", "video", "carousel"}:
        return declared
    path = url.lower()
    if any(path.endswith(ext) for ext in (".mp4", ".mov", ".webm", ".m4v")):
        return "video"
    return "image"


class _PublicHTMLParser(HTMLParser):
    def __init__(self, *, base_url: str) -> None:
        super().__init__(convert_charrefs=True)
        self.base_url = base_url
        self.meta: dict[str, str] = {}
        self.json_ld: list[str] = []
        self.bio: str | None = None
        self.profile_image: str | None = None
        self.highlights: list[tuple[str, str | None]] = []
        self.posts: list[ParsedPost] = []
        self._capture: list[str] | None = None
        self._in_ld = False
        self._post: ParsedPost | None = None
        self._highlight: dict[str, str] | None = None
        self._caption = False
        self._bio = False
        self._hl_title = False
        self._hl_text = False
        self._post_default_type = ""

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.handle_starttag(tag, attrs)

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        data = {key.lower(): (value or "") for key, value in attrs}
        if tag == "meta":
            prop = (data.get("property") or data.get("name") or "").lower()
            if prop and data.get("content"):
                self.meta[prop] = data["content"]
            return
        if tag == "link" and data.get("rel", "").lower() == "canonical" and data.get("href"):
            self.meta["canonical"] = data["href"]
            return
        if tag == "script" and "application/ld+json" in data.get("type", "").lower():
            self._in_ld = True
            self._capture = []
            return
        if "data-bio" in data and tag in {"p", "div", "span", "section"}:
            self._bio = True
            self._capture = []
        if tag == "img" and "data-profile-image" in data:
            self.profile_image = _abs_url(data.get("src") or data.get("content"), self.base_url)
        if "data-highlight" in data:
            self._highlight = {
                "title": data.get("data-title") or "",
                "text": data.get("data-text") or "",
            }
        if self._highlight is not None and tag in {"h1", "h2", "h3", "h4"}:
            self._hl_title = True
            self._capture = []
        if self._highlight is not None and tag == "p" and "data-caption" not in data:
            self._hl_text = True
            self._capture = []
        if "data-post" in data:
            post = ParsedPost()
            post.external_id = data.get("data-id") or ""
            post.url = _abs_url(data.get("data-url") or data.get("href"), self.base_url) or ""
            post.published_at = normalize_published_at(data.get("data-published") or data.get("datetime"))
            post.kind = (data.get("data-kind") or "").lower()
            default_type = (data.get("data-media-type") or "").lower()
            post.media = []
            self._post = post
            self._post_default_type = default_type
        if self._post is not None and "data-caption" in data:
            self._caption = True
            self._capture = []
        if self._post is not None and tag in {"img", "video", "source"}:
            self._add_media(data, tag)

    def handle_endtag(self, tag: str) -> None:
        if tag == "script" and self._in_ld:
            blob = "".join(self._capture or []).strip()
            if blob:
                self.json_ld.append(blob)
            self._in_ld = False
            self._capture = None
            return
        text = _clean_text("".join(self._capture)) if self._capture is not None else None
        if self._bio and tag in {"p", "div", "span", "section"}:
            if text and not self.bio:
                self.bio = text
            self._bio = False
            self._capture = None
        if self._caption and self._post is not None:
            if text:
                self._post.caption = text
            self._caption = False
            self._capture = None
        if self._hl_title and self._highlight is not None:
            if text:
                self._highlight["title"] = text
            self._hl_title = False
            self._capture = None
        if self._hl_text and self._highlight is not None:
            if text and not self._highlight.get("text"):
                self._highlight["text"] = text
            self._hl_text = False
            self._capture = None
        if tag == "article" and self._highlight is not None and self._post is None:
            title = _clean_text(self._highlight.get("title"))
            if title:
                self.highlights.append((title, _clean_text(self._highlight.get("text"))))
            self._highlight = None
        if tag == "article" and self._post is not None:
            post = self._post
            if not post.external_id:
                post.external_id = _id_from_url(post.url) or "post"
            if not post.url:
                post.url = self.base_url
            annotate_selectable_media([post])
            self.posts.append(post)
            self._post = None
            self._post_default_type = ""

    def handle_data(self, data: str) -> None:
        if self._capture is not None:
            self._capture.append(data)

    def _add_media(self, data: dict[str, str], tag: str) -> None:
        post = self._post
        if post is None:
            return
        src = data.get("src") or data.get("content") or data.get("data-src")
        url = _abs_url(src, self.base_url)
        if not url:
            return
        default_type = self._post_default_type
        if "data-thumbnail" in data:
            post.media.append(PostMedia(url=url, type="image", selectable_photo=True, flags=("thumbnail",)))
            return
        if tag == "video" or (tag == "source" and "video" in data.get("type", "")):
            media_type = "video"
        elif default_type in {"image", "video", "carousel"}:
            media_type = default_type
        else:
            media_type = _infer_media_type(url, "")
        if media_type not in {"image", "video", "carousel"}:
            media_type = "image"
        if "data-media" in data or tag in {"img", "video", "source"}:
            post.media.append(
                PostMedia(url=url, type=media_type, selectable_photo=media_type != "video")
            )
