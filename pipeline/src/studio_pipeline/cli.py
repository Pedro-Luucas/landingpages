"""Command-line interface for studio-pipeline (argparse, stdlib)."""

from __future__ import annotations

import argparse
import json
import os
import sys
import traceback
from collections.abc import Sequence
from pathlib import Path

from jsonschema.exceptions import ValidationError

from studio_pipeline.config import load_config, schemas_dir, schemas_dir_candidates
from studio_pipeline.errors import INPUT_INVALID, SCHEMA_INVALID, PipelineError
from studio_pipeline.http import StdlibBinaryHttp, StdlibHttpClient
from studio_pipeline.importers.source import import_source
from studio_pipeline.orchestrator import Orchestrator
from studio_pipeline.search import create_search_provider
from studio_pipeline.persistence import read_json
from studio_pipeline.repositories.state import StateRepository
from studio_pipeline.repositories.studio import StudioRepository
from studio_pipeline.validation.schema_store import load_schema
from studio_pipeline.validation.schemas import (
    EXPECTED_SCHEMA_FILES,
    SchemaValidationError,
    validate_fixture_tree,
    validate_instance,
)

_SECRET_ENV_KEYS = (
    "AI_API_KEY",
    "SEARCH_API_KEY",
    "VERCEL_TOKEN",
    "DASHBOARD_SECRET",
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="studio-pipeline",
        description="Music-studio landing-page generator pipeline.",
        epilog=(
            "DATA_DIR defaults to ./data (repo root when CWD is pipeline/). "
            "Existing environment variables win over repo-root .env."
        ),
    )
    sub = parser.add_subparsers(dest="command")

    import_p = sub.add_parser(
        "import",
        help="Import and normalize the source studios JSON.",
    )
    import_p.add_argument(
        "--input",
        required=True,
        help="Path to the source JSON (object with musica[] or a bare array).",
    )

    queue_p = sub.add_parser(
        "queue",
        help="Enqueue a studio (imported or rejected -> queued).",
    )
    queue_p.add_argument("--studio-id", required=True, help="Stable studio id.")

    run_p = sub.add_parser(
        "run",
        help="Run pipeline stages for one studio (M2–M3: discovery, scrape, enrich, media).",
    )
    run_p.add_argument("--studio-id", required=True, help="Stable studio id.")

    retry_p = sub.add_parser(
        "retry",
        help="Retry a failed studio (failed -> queued).",
    )
    retry_p.add_argument("--studio-id", required=True, help="Stable studio id.")

    validate_p = sub.add_parser(
        "validate",
        help="Validate schema fixtures, or one studio with --studio-id.",
    )
    validate_p.add_argument(
        "--studio-id",
        required=False,
        default=None,
        help="If set, validate that studio's JSON documents.",
    )

    sub.add_parser(
        "doctor",
        help="Check schemas, data dir, locks, and pipeline/studio consistency.",
    )

    return parser


def _redact_cli_text(text: str) -> str:
    out = text
    for key in _SECRET_ENV_KEYS:
        secret = os.environ.get(key, "")
        if secret and len(secret) >= 4:
            out = out.replace(secret, "***")
    return out


def _print_error(exc: BaseException) -> None:
    if isinstance(exc, PipelineError):
        print(
            _redact_cli_text(f"error: {exc.code}: {exc.message}"),
            file=sys.stderr,
        )
        return
    print(_redact_cli_text(f"error: {INPUT_INVALID}: {exc}"), file=sys.stderr)


def _debug_traces() -> bool:
    return os.environ.get("LOG_LEVEL", "").strip().lower() == "debug"


def _cmd_import(input_path: str) -> int:
    config = load_config()
    report = import_source(input_path, data_dir=config.data_dir, actor="cli")
    print(report.format())
    print(f"data dir: {config.data_dir}")
    return 0


def _cmd_queue(studio_id: str) -> int:
    config = load_config()
    studios = StudioRepository(config.data_dir)
    state = StateRepository(config.data_dir, studio_repo=studios)
    item = state.get_item(studio_id)
    if item is None:
        raise PipelineError(INPUT_INVALID, f"no pipeline item for studio {studio_id}")
    status = str(item.get("status") or "")
    if status == "queued":
        print(f"queue: {studio_id} already queued")
        return 0
    if status not in {"imported", "rejected"}:
        raise PipelineError(
            INPUT_INVALID,
            f"studio {studio_id} is {status}; queue requires imported or rejected "
            "(use retry if failed)",
        )
    state.transition(studio_id, "queued", actor="cli", reason="Enqueued via CLI.")
    print(f"queue: {studio_id} {status} -> queued")
    return 0


def _cmd_run(studio_id: str) -> int:
    config = load_config()
    http_client = StdlibHttpClient(
        timeout=config.discovery_http_timeout_seconds,
        max_redirects=config.discovery_max_redirects,
    )
    binary_http = StdlibBinaryHttp(
        timeout=config.discovery_http_timeout_seconds,
        max_redirects=config.discovery_max_redirects,
    )
    message = Orchestrator(config).run(
        studio_id,
        actor=f"pipeline:{os.getpid()}",
        http_client=http_client,
        search_provider=create_search_provider(config),
        binary_http=binary_http,
    )
    print(message)
    return 0


def _cmd_retry(studio_id: str) -> int:
    config = load_config()
    studios = StudioRepository(config.data_dir)
    state = StateRepository(config.data_dir, studio_repo=studios)
    item = state.get_item(studio_id)
    if item is None:
        raise PipelineError(INPUT_INVALID, f"no pipeline item for studio {studio_id}")
    status = str(item.get("status") or "")
    if status != "failed":
        raise PipelineError(
            INPUT_INVALID,
            f"studio {studio_id} is {status}; retry requires failed",
        )
    state.transition(studio_id, "queued", actor="cli", reason="Retry via CLI.")
    print(f"retry: {studio_id} failed -> queued")
    return 0


def _validate_document(kind: str, path: Path) -> None:
    try:
        instance = read_json(path)
    except OSError as exc:
        raise PipelineError(INPUT_INVALID, f"cannot read {path}: {exc}") from exc
    except Exception as exc:
        raise PipelineError(SCHEMA_INVALID, f"{path.name}: invalid JSON ({exc})") from exc
    try:
        validate_instance(load_schema(kind), instance)
    except ValidationError as exc:
        raise PipelineError(SCHEMA_INVALID, f"{path.name}: {exc.message}") from exc


def _cmd_validate(studio_id: str | None) -> int:
    if not studio_id:
        return _cmd_validate_fixtures()

    config = load_config()
    studios = StudioRepository(config.data_dir)
    studio_dir = studios.studio_dir(studio_id)
    studio_path = studio_dir / "studio.json"
    if not studio_path.is_file():
        raise PipelineError(
            INPUT_INVALID,
            f"studio.json not found for {studio_id!r} under {studio_dir}",
        )

    _validate_document("studio", studio_path)
    print(f"{studio_path.name}: OK")
    optional = (
        ("dossier", "dossier.json"),
        ("generated", "generated.json"),
        ("deployment", "deployment.json"),
    )
    for kind, name in optional:
        path = studio_dir / name
        if path.is_file():
            _validate_document(kind, path)
            print(f"{name}: OK")
        else:
            print(f"{name}: absent")
    approved = studio_dir / "approved.json"
    if approved.is_file():
        print("approved.json: present (no approved.schema.json in M1; skipped)")
    print(f"validate: studio {studio_id} OK")
    return 0


def _cmd_validate_fixtures() -> int:
    root_schemas = schemas_dir()
    fixtures = root_schemas / "fixtures"
    try:
        results = validate_fixture_tree(root_schemas, fixtures)
    except FileNotFoundError as exc:
        raise PipelineError(INPUT_INVALID, str(exc)) from exc
    except SchemaValidationError as exc:
        raise PipelineError(SCHEMA_INVALID, str(exc)) from exc

    failed = 0
    for item in results:
        print(item.message)
        if not item.ok:
            failed += 1

    if failed:
        print(f"validate: {failed} fixture(s) failed", file=sys.stderr)
        return 1
    print("validate: all schema fixtures passed")
    return 0


def _cmd_doctor() -> int:
    issues: list[str] = []
    candidates = schemas_dir_candidates()
    existing = [path for path in candidates if path.is_dir()]
    if existing:
        schemas = existing[0]
        print(f"schemas directory: {schemas}  OK")
    else:
        schemas = candidates[0]
        print(f"schemas directory: {schemas}  MISSING")
        issues.append(f"schemas directory missing: {schemas}")

    for name in EXPECTED_SCHEMA_FILES:
        path = schemas / name
        present = path.is_file()
        status = "OK" if present else "MISSING"
        print(f"  {name:28} {status}")
        if not present:
            issues.append(f"missing schema {name}")

    config = load_config()
    data_dir = config.data_dir
    if data_dir.is_dir():
        print(f"data directory: {data_dir}  OK")
    else:
        print(f"data directory: {data_dir}  MISSING")
        issues.append(f"data directory missing: {data_dir}")

    studios = StudioRepository(data_dir)
    state = StateRepository(data_dir, studio_repo=studios)
    pipeline_path = state.pipeline_path
    if pipeline_path.is_file():
        try:
            pipeline = state.get_pipeline()
            validate_instance(load_schema("pipeline"), pipeline)
            print(f"pipeline.json: {len(pipeline.get('items') or [])} item(s)  OK")
        except (PipelineError, ValidationError, OSError, json.JSONDecodeError, UnicodeError) as exc:
            print(f"pipeline.json: INVALID ({exc})")
            code = SCHEMA_INVALID
            if isinstance(exc, PipelineError):
                code = exc.code
            elif isinstance(exc, OSError) and not isinstance(exc, json.JSONDecodeError):
                code = INPUT_INVALID
            issues.append(f"{code}: pipeline.json invalid: {exc}")
            pipeline = {"items": []}
        for item in pipeline.get("items") or []:
            if not isinstance(item, dict):
                issues.append("pipeline item is not an object")
                continue
            studio_id = str(item.get("studioId") or "")
            if not studio_id:
                issues.append("pipeline item missing studioId")
                continue
            studio_file = studios.studio_dir(studio_id) / "studio.json"
            if not studio_file.is_file():
                msg = f"missing studio.json for pipeline item {studio_id}"
                print(f"  {msg}")
                issues.append(msg)
    else:
        print("pipeline.json: absent (empty queue)  OK")

    locks = state.list_locks()
    if not locks:
        print("locks: none  OK")
    else:
        print(f"locks: {len(locks)}")
        for lock in locks:
            studio_id = lock.get("studioId")
            if lock.get("invalid"):
                msg = f"invalid lock file for {studio_id}"
                print(f"  {msg}")
                issues.append(msg)
            elif lock.get("expired"):
                msg = f"expired lock for {studio_id}"
                print(f"  {msg}")
                issues.append(msg)
            else:
                print(f"  {studio_id}: held by {lock.get('owner')}")

    if issues:
        print(f"doctor: {len(issues)} issue(s)")
        return 1
    print("doctor: OK")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)

    if not args.command:
        parser.print_help()
        return 0

    try:
        if args.command == "doctor":
            return _cmd_doctor()
        if args.command == "validate":
            return _cmd_validate(args.studio_id)
        if args.command == "import":
            return _cmd_import(args.input)
        if args.command == "queue":
            return _cmd_queue(args.studio_id)
        if args.command == "run":
            return _cmd_run(args.studio_id)
        if args.command == "retry":
            return _cmd_retry(args.studio_id)
    except PipelineError as exc:
        _print_error(exc)
        return 1
    except SchemaValidationError as exc:
        _print_error(PipelineError(SCHEMA_INVALID, str(exc)))
        return 1
    except json.JSONDecodeError as exc:
        _print_error(PipelineError(SCHEMA_INVALID, f"invalid JSON: {exc}"))
        return 1
    except OSError as exc:
        _print_error(PipelineError(INPUT_INVALID, str(exc)))
        return 1
    except Exception as exc:
        _print_error(PipelineError(INPUT_INVALID, str(exc)))
        if _debug_traces():
            traceback.print_exc()
        return 1

    parser.print_help()
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
