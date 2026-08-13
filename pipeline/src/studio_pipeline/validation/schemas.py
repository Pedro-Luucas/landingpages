"""JSON Schema validation against repo-root `schemas/` (M0)."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from jsonschema.exceptions import SchemaError, ValidationError
from jsonschema.validators import validator_for

EXPECTED_SCHEMA_FILES = (
    "studio.schema.json",
    "dossier.schema.json",
    "generated.schema.json",
    "pipeline.schema.json",
    "deployment.schema.json",
)


class SchemaValidationError(Exception):
    """Invalid schema document or unmatched fixture."""


@dataclass(frozen=True)
class FixtureResult:
    ok: bool
    path: Path
    message: str


def load_json(path: Path) -> Any:
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def make_validator(schema: dict[str, Any]) -> Any:
    validator_cls = validator_for(schema)
    validator_cls.check_schema(schema)
    # Match Ajv `addFormats`: treat `format` (date-time, uri, …) as assertions.
    return validator_cls(schema, format_checker=validator_cls.FORMAT_CHECKER)


def schema_stem(path: Path) -> str:
    name = path.name
    suffix = ".schema.json"
    if name.endswith(suffix):
        return name[: -len(suffix)]
    return path.stem


def fixture_kind(path: Path) -> tuple[str, str] | None:
    name = path.name
    for kind, suffix in (("valid", ".valid.json"), ("invalid", ".invalid.json")):
        if name.endswith(suffix):
            return name[: -len(suffix)], kind
    return None


def match_schema(fixture_stem: str, schema_files: list[Path]) -> Path | None:
    """Match a fixture stem to the longest schema stem that is a prefix."""
    best: Path | None = None
    best_len = -1
    for schema_path in schema_files:
        stem = schema_stem(schema_path)
        if fixture_stem == stem or fixture_stem.startswith(stem + "."):
            if len(stem) > best_len:
                best = schema_path
                best_len = len(stem)
    return best


def validate_instance(schema: dict[str, Any], instance: Any) -> None:
    make_validator(schema).validate(instance)


def validate_fixture_tree(schemas_dir: Path, fixtures_dir: Path) -> list[FixtureResult]:
    if not schemas_dir.is_dir():
        raise FileNotFoundError(f"schemas directory not found: {schemas_dir}")

    schema_files = sorted(schemas_dir.glob("*.schema.json"))
    if not schema_files:
        raise FileNotFoundError(f"no *.schema.json files in {schemas_dir}")

    schemas_by_path: dict[Path, dict[str, Any]] = {}
    for schema_path in schema_files:
        try:
            document = load_json(schema_path)
            make_validator(document)
        except (json.JSONDecodeError, SchemaError) as exc:
            raise SchemaValidationError(f"invalid schema {schema_path}: {exc}") from exc
        schemas_by_path[schema_path] = document

    results: list[FixtureResult] = []
    if not fixtures_dir.is_dir():
        results.append(
            FixtureResult(
                ok=True,
                path=fixtures_dir,
                message=f"note: fixtures directory not found ({fixtures_dir}); schemas loaded OK",
            )
        )
        return results

    fixtures = sorted(
        p
        for p in fixtures_dir.glob("*.json")
        if fixture_kind(p) is not None
    )
    if not fixtures:
        results.append(
            FixtureResult(
                ok=True,
                path=fixtures_dir,
                message=f"note: no *.valid.json / *.invalid.json fixtures in {fixtures_dir}; schemas loaded OK",
            )
        )
        return results

    for fixture in fixtures:
        kind_info = fixture_kind(fixture)
        assert kind_info is not None
        stem, kind = kind_info
        schema_path = match_schema(stem, schema_files)
        if schema_path is None:
            raise SchemaValidationError(
                f"no matching *.schema.json for fixture {fixture.name}"
            )
        schema = schemas_by_path[schema_path]
        instance = load_json(fixture)
        try:
            validate_instance(schema, instance)
            passed = True
            error_text = ""
        except ValidationError as exc:
            passed = False
            error_text = exc.message

        if kind == "valid":
            ok = passed
            detail = "OK" if ok else f"FAIL (expected valid): {error_text}"
        else:
            ok = not passed
            detail = "OK (rejected)" if ok else "FAIL (expected invalid, but schema accepted it)"

        results.append(
            FixtureResult(
                ok=ok,
                path=fixture,
                message=f"{fixture.name} vs {schema_path.name}: {detail}",
            )
        )
    return results
