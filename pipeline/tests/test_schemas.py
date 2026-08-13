"""Validate repo-root JSON schemas against fixtures."""

from __future__ import annotations

from pathlib import Path

import pytest
from jsonschema.exceptions import ValidationError

from studio_pipeline.config import repo_root, schemas_dir
from studio_pipeline.validation.schemas import (
    fixture_kind,
    load_json,
    make_validator,
    match_schema,
    schema_stem,
    validate_instance,
)


def _schemas_dir() -> Path:
    return schemas_dir()


def _require_schema_files() -> tuple[Path, list[Path]]:
    directory = _schemas_dir()
    assert directory.is_dir(), f"JSON schemas missing at {directory}"
    files = sorted(directory.glob("*.schema.json"))
    assert files, f"No *.schema.json files in {directory}"
    return directory, files


def test_repo_root_is_parent_of_pipeline() -> None:
    root = repo_root()
    assert (root / "pipeline" / "pyproject.toml").is_file()


def test_schemas_load_and_fixtures_validate() -> None:
    directory, schema_files = _require_schema_files()
    validators = {}
    for schema_path in schema_files:
        document = load_json(schema_path)
        validators[schema_path] = make_validator(document)
        assert schema_stem(schema_path)

    fixtures_dir = directory / "fixtures"
    assert fixtures_dir.is_dir(), f"Schema fixtures missing at {fixtures_dir}"

    valid = sorted(fixtures_dir.glob("*.valid.json"))
    invalid = sorted(fixtures_dir.glob("*.invalid.json"))
    assert valid or invalid, f"No *.valid.json / *.invalid.json in {fixtures_dir}"

    for fixture in valid:
        kind = fixture_kind(fixture)
        assert kind is not None
        stem, _ = kind
        schema_path = match_schema(stem, schema_files)
        assert schema_path is not None, f"no schema for {fixture.name}"
        instance = load_json(fixture)
        validate_instance(load_json(schema_path), instance)

    for fixture in invalid:
        kind = fixture_kind(fixture)
        assert kind is not None
        stem, _ = kind
        schema_path = match_schema(stem, schema_files)
        assert schema_path is not None, f"no schema for {fixture.name}"
        instance = load_json(fixture)
        with pytest.raises(ValidationError):
            validate_instance(load_json(schema_path), instance)


def test_format_assertions_match_ajv() -> None:
    directory, _schema_files = _require_schema_files()
    schema = load_json(directory / "studio.schema.json")
    instance = load_json(directory / "fixtures" / "studio.valid.json")

    bad_date = dict(instance)
    bad_date["updatedAt"] = "not-a-date"
    with pytest.raises(ValidationError, match="date-time"):
        validate_instance(schema, bad_date)

    bad_uri = dict(instance)
    contacts = dict(instance["contacts"])
    contacts["website"] = "not a uri"
    bad_uri["contacts"] = contacts
    with pytest.raises(ValidationError, match="uri"):
        validate_instance(schema, bad_uri)
