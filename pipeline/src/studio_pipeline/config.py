"""Environment configuration. Secrets are never printed."""

from __future__ import annotations

import os
import re
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

_SECRET_FIELDS = frozenset(
    {
        "ai_api_key",
        "search_api_key",
        "vercel_token",
        "dashboard_secret",
    }
)

DEFAULT_DISCOVERY_CONFIDENCE_THRESHOLD = 0.85
DEFAULT_DISCOVERY_HTTP_TIMEOUT_SECONDS = 10.0
DEFAULT_DISCOVERY_MAX_REDIRECTS = 5
DEFAULT_DISCOVERY_AMBIGUITY_MARGIN = 0.08

_ENV_KEY = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def repo_root() -> Path:
    """Return the git/repo root: parent of the `pipeline/` package directory."""
    # this file: <repo>/pipeline/src/studio_pipeline/config.py
    return Path(__file__).resolve().parents[3]


def pipeline_root() -> Path:
    """Return the `pipeline/` directory that contains pyproject.toml."""
    return Path(__file__).resolve().parents[2]


def schemas_dir_candidates() -> list[Path]:
    """Schema locations: repo-root `schemas/` and `../schemas` from pipeline/."""
    root = repo_root()
    pipeline = pipeline_root()
    seen: set[Path] = set()
    ordered: list[Path] = []
    for candidate in (root / "schemas", (pipeline / ".." / "schemas").resolve()):
        resolved = candidate.resolve()
        if resolved not in seen:
            seen.add(resolved)
            ordered.append(resolved)
    return ordered


def schemas_dir() -> Path:
    """Preferred schemas directory (repo-root `schemas/`)."""
    return schemas_dir_candidates()[0]


_DOUBLE_ESCAPES = {
    "n": "\n",
    "r": "\r",
    "t": "\t",
    '"': '"',
    "'": "'",
    "\\": "\\",
}


def _parse_dotenv_value(raw: str) -> str:
    """Unquote values and drop inline comments (`#` outside quotes)."""
    i = 0
    n = len(raw)
    while i < n and raw[i] in " \t":
        i += 1
    if i >= n:
        return ""
    quote = raw[i]
    if quote in {'"', "'"}:
        i += 1
        chars: list[str] = []
        while i < n:
            ch = raw[i]
            if quote == '"' and ch == "\\" and i + 1 < n:
                nxt = raw[i + 1]
                chars.append(_DOUBLE_ESCAPES.get(nxt, nxt))
                i += 2
                continue
            if quote == "'" and ch == "\\" and i + 1 < n and raw[i + 1] == "'":
                chars.append("'")
                i += 2
                continue
            if ch == quote:
                return "".join(chars)
            chars.append(ch)
            i += 1
        return raw.strip()
    hash_at = raw.find("#", i)
    if hash_at != -1:
        return raw[i:hash_at].rstrip()
    return raw[i:].rstrip()


def parse_dotenv(path: Path) -> dict[str, str]:
    """Parse a dotenv file with the stdlib only (no python-dotenv)."""
    values: dict[str, str] = {}
    try:
        text = Path(path).read_text(encoding="utf-8-sig")
    except OSError:
        return values
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].strip()
        if "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        if not key or _ENV_KEY.fullmatch(key) is None:
            continue
        values[key] = _parse_dotenv_value(value)
    return values


def _cwd_prefers_repo_root() -> bool:
    cwd = Path.cwd().resolve()
    pipeline = pipeline_root().resolve()
    return cwd == pipeline or pipeline in cwd.parents


def resolve_relative_path(raw: str | Path) -> Path:
    """Resolve DATA_DIR/ASSETS_DIR.

    Relative paths use CWD, except when CWD is `pipeline/` (or inside it):
    then they are resolved from the repo root so `./data` is the shared tree.
    """
    path = Path(raw).expanduser()
    if path.is_absolute():
        return path.resolve()
    base = repo_root() if _cwd_prefers_repo_root() else Path.cwd()
    return (base / path).resolve()


def _lookup(
    name: str,
    default: str,
    environ: Mapping[str, str],
    file_vals: Mapping[str, str],
) -> str:
    if name in environ:
        return environ[name]
    if name in file_vals:
        return file_vals[name]
    return default


def _parse_bounded_float(
    raw: str,
    default: float,
    *,
    minimum: float,
    maximum: float,
) -> float:
    text = (raw or "").strip()
    if not text:
        return default
    try:
        value = float(text)
    except ValueError:
        return default
    if value < minimum or value > maximum:
        return default
    return value


def _parse_bounded_int(
    raw: str,
    default: int,
    *,
    minimum: int,
    maximum: int,
) -> int:
    text = (raw or "").strip()
    if not text:
        return default
    try:
        value = int(text, 10)
    except ValueError:
        return default
    if value < minimum or value > maximum:
        return default
    return value


@dataclass(frozen=True)
class Config:
    studio_id: str
    data_dir: Path
    assets_dir: Path
    app_base_url: str
    dashboard_secret: str
    ai_provider: str
    ai_model: str
    ai_api_key: str
    search_provider: str
    search_api_key: str
    vercel_token: str
    vercel_team_id: str
    log_level: str
    discovery_confidence_threshold: float
    discovery_http_timeout_seconds: float
    discovery_max_redirects: int
    discovery_ambiguity_margin: float

    def redacted(self) -> dict[str, str]:
        """Public view of settings; secret values are masked."""
        out: dict[str, str] = {}
        for key, value in self.__dict__.items():
            text = str(value)
            if key in _SECRET_FIELDS:
                out[key] = "***" if text else ""
            else:
                out[key] = text
        return out

    def __repr__(self) -> str:
        parts = [f"{key}={value!r}" for key, value in self.redacted().items()]
        return f"Config({', '.join(parts)})"


def load_config(
    *,
    environ: Mapping[str, str] | None = None,
    dotenv_path: Path | None = None,
) -> Config:
    """Load config from process env, overlaying repo-root `.env`.

    Existing environment variables win over `.env`. Secrets are never printed.
    """
    env: Mapping[str, str] = os.environ if environ is None else environ
    path = repo_root() / ".env" if dotenv_path is None else Path(dotenv_path)
    file_vals = parse_dotenv(path) if path.is_file() else {}

    def get(name: str, default: str = "") -> str:
        return _lookup(name, default, env, file_vals)

    log_level = get("LOG_LEVEL", "info").strip().lower() or "info"
    return Config(
        studio_id=get("STUDIO_ID").strip(),
        data_dir=resolve_relative_path(get("DATA_DIR", "./data") or "./data"),
        assets_dir=resolve_relative_path(
            get("ASSETS_DIR", "./public/studios") or "./public/studios"
        ),
        app_base_url=get("APP_BASE_URL", "http://localhost:3000"),
        dashboard_secret=get("DASHBOARD_SECRET"),
        ai_provider=get("AI_PROVIDER").strip(),
        ai_model=get("AI_MODEL").strip(),
        ai_api_key=get("AI_API_KEY"),
        search_provider=get("SEARCH_PROVIDER").strip(),
        search_api_key=get("SEARCH_API_KEY"),
        vercel_token=get("VERCEL_TOKEN"),
        vercel_team_id=get("VERCEL_TEAM_ID").strip(),
        log_level=log_level,
        discovery_confidence_threshold=_parse_bounded_float(
            get("DISCOVERY_CONFIDENCE_THRESHOLD"),
            DEFAULT_DISCOVERY_CONFIDENCE_THRESHOLD,
            minimum=0.0,
            maximum=1.0,
        ),
        discovery_http_timeout_seconds=_parse_bounded_float(
            get("DISCOVERY_HTTP_TIMEOUT_SECONDS"),
            DEFAULT_DISCOVERY_HTTP_TIMEOUT_SECONDS,
            minimum=0.5,
            maximum=60.0,
        ),
        discovery_max_redirects=_parse_bounded_int(
            get("DISCOVERY_MAX_REDIRECTS"),
            DEFAULT_DISCOVERY_MAX_REDIRECTS,
            minimum=1,
            maximum=20,
        ),
        discovery_ambiguity_margin=_parse_bounded_float(
            get("DISCOVERY_AMBIGUITY_MARGIN"),
            DEFAULT_DISCOVERY_AMBIGUITY_MARGIN,
            minimum=0.0,
            maximum=1.0,
        ),
    )
