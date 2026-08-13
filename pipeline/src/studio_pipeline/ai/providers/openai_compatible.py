"""OpenAI-compatible Chat Completions adapter (M4). Stdlib urllib only."""

from __future__ import annotations

import json
import os
import time
import urllib.request
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError

from studio_pipeline.ai.base import BrandAnalysis, GeneratedSite, MediaSelection
from studio_pipeline.config import Config
from studio_pipeline.errors import (
    AI_OUTPUT_INVALID,
    AI_PROVIDER_ERROR,
    AI_RATE_LIMITED,
    PipelineError,
)

PROMPT_VERSION = "m4.v1"
DEFAULT_MODEL = "gpt-4o-mini"
DEFAULT_TIMEOUT_SECONDS = 60.0
DEFAULT_BASE_URL = "https://api.openai.com/v1"
MAX_CAPTIONS = 30
MAX_RETRIES = 2
BACKOFF_SECONDS = 0.5
MAX_BODY_BYTES = 2_000_000

_PROMPT_PATH = Path(__file__).resolve().parents[1] / "prompts" / "m4.v1.md"

_EMBEDDED_SYSTEM_PROMPT = """You are M4 (promptVersion m4.v1) for music-studio landing pages.
Return a single JSON object only (no markdown).

GeneratedSite fields: schemaVersion, studioId, generationId, inputHash, provider,
model, promptVersion, templateId (editorial|immersive|minimal|bold), branding,
copy, sections, assetPaths, factualClaims, warnings, createdAt.

Rules:
- Use only facts supported by the provided evidence. Do not invent prices, hours,
  equipment, reviews, addresses, or phone numbers.
- Omit copy sections that lack evidence. Every factual claim needs evidenceRefs
  pointing at sourceUrl values from the input.
- You may freely choose colors, fonts, mood, template, and visual direction.
- Input order is bio, highlights, captions (at most 30), then facts. Text-only;
  do not expect or request images.
"""

_BRAND_SYSTEM = (
    _EMBEDDED_SYSTEM_PROMPT
    + "\nTask: return BrandAnalysis JSON with colors, fontHeading, fontBody, "
    "radius, mood, imageTreatment, warnings."
)
_MEDIA_SYSTEM = (
    _EMBEDDED_SYSTEM_PROMPT
    + "\nTask: return MediaSelection JSON with selected (max 10 localPath values), "
    "rejected, warnings. Do not invent files."
)

_SITE_SHAPE_KEYS = frozenset({"templateId", "copy", "branding"})


def _load_system_prompt() -> str:
    try:
        text = _PROMPT_PATH.read_text(encoding="utf-8").strip()
    except OSError:
        text = ""
    return text or _EMBEDDED_SYSTEM_PROMPT


def _completions_url(environ: Mapping[str, str]) -> str:
    base = (environ.get("OPENAI_BASE_URL") or DEFAULT_BASE_URL).strip().rstrip("/")
    if base.endswith("/chat/completions"):
        return base
    return f"{base}/chat/completions"


def _strip_fences(text: str) -> str:
    stripped = text.strip()
    if not stripped.startswith("```"):
        return stripped
    lines = stripped.split("\n")
    if lines and lines[0].startswith("```"):
        lines = lines[1:]
    if lines and lines[-1].strip() == "```":
        lines = lines[:-1]
    return "\n".join(lines).strip()


def _evidence_value(item: object) -> Any:
    if isinstance(item, dict) and "value" in item:
        return item.get("value")
    return item


def _compact_evidence(item: object) -> dict[str, Any] | None:
    if not isinstance(item, dict):
        return None
    payload: dict[str, Any] = {}
    for key in ("value", "sourceUrl", "sourceType", "confidence", "excerpt"):
        if key in item:
            payload[key] = item[key]
    return payload or None


def _highlights(social: Mapping[str, Any]) -> list[Any]:
    out: list[Any] = []
    for item in social.get("highlights") or []:
        compact = _compact_evidence(item)
        if compact is not None:
            out.append(compact)
    return out


def _captions(social: Mapping[str, Any], *, limit: int = MAX_CAPTIONS) -> list[str]:
    out: list[str] = []
    for post in social.get("posts") or []:
        if len(out) >= limit:
            break
        if not isinstance(post, dict):
            continue
        caption = post.get("caption")
        if isinstance(caption, str) and caption.strip():
            out.append(caption.strip())
    return out


def _facts_payload(facts: object) -> dict[str, Any]:
    if not isinstance(facts, dict):
        return {}
    out: dict[str, Any] = {}
    for key, rows in facts.items():
        if not isinstance(rows, list):
            continue
        compact_rows = [row for row in (_compact_evidence(item) for item in rows) if row]
        out[str(key)] = compact_rows
    return out


def _ordered_input(
    dossier: Mapping[str, Any],
    extra: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    social = dossier.get("social") if isinstance(dossier.get("social"), dict) else {}
    payload: dict[str, Any] = {
        "studioId": dossier.get("studioId"),
        "bio": _evidence_value(social.get("bio")),
        "highlights": _highlights(social),
        "captions": _captions(social),
        "facts": _facts_payload(dossier.get("facts")),
    }
    if extra:
        payload.update(extra)
    return payload


def _media_refs(selected_media: Mapping[str, Any] | None) -> list[str]:
    if not selected_media:
        return []
    refs: list[str] = []
    for item in selected_media.get("selected") or []:
        if isinstance(item, str) and item.strip():
            refs.append(item.strip())
        elif isinstance(item, dict):
            path = item.get("localPath") or item.get("path")
            if isinstance(path, str) and path.strip():
                refs.append(path.strip())
    return refs


def _candidate_refs(candidates: list[Any]) -> list[dict[str, Any]]:
    keys = (
        "localPath",
        "sourceUrl",
        "mime",
        "width",
        "height",
        "score",
        "qualityScore",
        "relevanceScore",
        "flags",
        "usableAsHero",
        "usableAsGallery",
    )
    out: list[dict[str, Any]] = []
    for item in candidates:
        if not isinstance(item, dict):
            continue
        row = {key: item[key] for key in keys if key in item}
        if row:
            out.append(row)
    return out


def _content_from_message(message: object) -> str:
    if isinstance(message, str):
        return message
    if not isinstance(message, dict):
        return ""
    content = message.get("content")
    if isinstance(content, str):
        return content
    if isinstance(content, dict):
        return json.dumps(content, ensure_ascii=False)
    if isinstance(content, list):
        parts: list[str] = []
        for part in content:
            if isinstance(part, str):
                parts.append(part)
            elif isinstance(part, dict):
                if part.get("type") == "text" or "text" in part:
                    parts.append(str(part.get("text") or ""))
        return "".join(parts)
    return ""


def _parse_json_object(raw: str, *, what: str) -> dict[str, Any]:
    text = _strip_fences(raw)
    if not text:
        raise PipelineError(AI_OUTPUT_INVALID, f"AI {what} was empty")
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as exc:
        raise PipelineError(
            AI_OUTPUT_INVALID, f"AI {what} was not valid JSON"
        ) from None
    if not isinstance(parsed, dict):
        raise PipelineError(AI_OUTPUT_INVALID, f"AI {what} is not a JSON object")
    return parsed


def _status_error(status: int) -> PipelineError:
    if status == 429:
        return PipelineError(AI_RATE_LIMITED, "AI provider rate limited the request")
    if status in {401, 403}:
        return PipelineError(
            AI_PROVIDER_ERROR, "AI provider rejected the request (unauthorized)"
        )
    return PipelineError(AI_PROVIDER_ERROR, f"AI provider HTTP {status}")


def _should_retry(status: int) -> bool:
    return status == 429 or 500 <= status <= 599


class OpenAICompatibleProvider:
    """Chat Completions client. Vendor HTTP stays in this module."""

    def __init__(
        self,
        config: Config,
        *,
        urlopen: Callable[..., Any] | None = None,
        sleep: Callable[[float], None] | None = None,
        environ: Mapping[str, str] | None = None,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
    ) -> None:
        self._config = config
        self._urlopen = urlopen
        self._sleep = sleep or time.sleep
        self._environ = environ if environ is not None else os.environ
        self._timeout = timeout

    def analyze_brand(
        self,
        dossier: dict[str, Any],
        asset_paths: list[str],
    ) -> BrandAnalysis:
        paths = [str(path) for path in asset_paths if str(path).strip()]
        payload = _ordered_input(dossier, {"assetPaths": paths})
        result = self._chat_json(_BRAND_SYSTEM, payload)
        return result  # type: ignore[return-value]

    def select_media(
        self,
        dossier: dict[str, Any],
        candidates: list[Any],
    ) -> MediaSelection:
        payload = _ordered_input(dossier, {"candidates": _candidate_refs(candidates)})
        result = self._chat_json(_MEDIA_SYSTEM, payload)
        return result  # type: ignore[return-value]

    def generate_site(
        self,
        dossier: dict[str, Any],
        brand: BrandAnalysis,
        selected_media: MediaSelection,
    ) -> GeneratedSite:
        extra = {
            "brand": dict(brand) if brand else {},
            "selectedMedia": _media_refs(selected_media),
        }
        payload = _ordered_input(dossier, extra)
        parsed = self._chat_json(_load_system_prompt(), payload)
        if not any(key in parsed for key in _SITE_SHAPE_KEYS):
            raise PipelineError(
                AI_OUTPUT_INVALID, "AI output is not GeneratedSite-shaped JSON"
            )
        model = (self._config.ai_model or "").strip() or DEFAULT_MODEL
        parsed["schemaVersion"] = 1
        parsed["studioId"] = str(dossier.get("studioId") or parsed.get("studioId") or "")
        parsed["provider"] = (self._config.ai_provider or "openai_compatible").strip() or (
            "openai_compatible"
        )
        parsed["model"] = model
        parsed["promptVersion"] = PROMPT_VERSION
        parsed.setdefault("warnings", [])
        parsed.setdefault("sections", [])
        parsed.setdefault("assetPaths", [])
        parsed.setdefault("factualClaims", [])
        return parsed  # type: ignore[return-value]

    def _chat_json(self, system_prompt: str, user_payload: dict[str, Any]) -> dict[str, Any]:
        model = (self._config.ai_model or "").strip() or DEFAULT_MODEL
        body = {
            "model": model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {
                    "role": "user",
                    "content": json.dumps(user_payload, ensure_ascii=False),
                },
            ],
            "response_format": {"type": "json_object"},
        }
        raw = self._post(body)
        return self._parse_completion(raw)

    def _api_key(self) -> str:
        return (self._config.ai_api_key or "").strip()

    def _post(self, payload: dict[str, Any]) -> bytes:
        api_key = self._api_key()
        if not api_key:
            raise PipelineError(
                AI_PROVIDER_ERROR,
                "AI_API_KEY is missing; cannot call the OpenAI-compatible provider",
            )
        url = _completions_url(self._environ)
        request = urllib.request.Request(
            url,
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            method="POST",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
                "Accept": "application/json",
                "User-Agent": "studio-pipeline/0.1",
            },
        )
        opener = self._urlopen or urllib.request.urlopen
        last_status = 0
        for attempt in range(MAX_RETRIES + 1):
            try:
                with opener(request, timeout=self._timeout) as response:
                    status = int(getattr(response, "status", 200) or 200)
                    body = response.read(MAX_BODY_BYTES)
            except HTTPError as exc:
                status = int(exc.code or 0)
                body = b""
                try:
                    body = exc.read(MAX_BODY_BYTES)
                except Exception:
                    body = b""
                if _should_retry(status) and attempt < MAX_RETRIES:
                    last_status = status
                    self._sleep(BACKOFF_SECONDS * (2**attempt))
                    continue
                raise _status_error(status) from None
            except (TimeoutError, URLError, OSError):
                raise PipelineError(
                    AI_PROVIDER_ERROR, "AI provider request failed or timed out"
                ) from None
            if _should_retry(status):
                last_status = status
                if attempt < MAX_RETRIES:
                    self._sleep(BACKOFF_SECONDS * (2**attempt))
                    continue
                raise _status_error(status)
            if status < 200 or status >= 300:
                raise _status_error(status)
            return body
        raise _status_error(last_status or 503)

    def _parse_completion(self, raw: bytes) -> dict[str, Any]:
        try:
            envelope = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            raise PipelineError(
                AI_OUTPUT_INVALID, "AI provider returned malformed JSON"
            ) from None
        if not isinstance(envelope, dict):
            raise PipelineError(
                AI_OUTPUT_INVALID, "AI provider returned malformed JSON"
            )
        if envelope.get("error") and not envelope.get("choices"):
            raise PipelineError(
                AI_PROVIDER_ERROR, "AI provider returned an error payload"
            )
        choices = envelope.get("choices")
        if not isinstance(choices, list) or not choices:
            raise PipelineError(AI_OUTPUT_INVALID, "AI provider returned no choices")
        first = choices[0] if isinstance(choices[0], dict) else {}
        content = _content_from_message(first.get("message") if isinstance(first, dict) else {})
        return _parse_json_object(content, what="output")
