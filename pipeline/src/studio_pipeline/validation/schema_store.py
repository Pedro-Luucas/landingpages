"""Load JSON Schema documents from repo-root `schemas/`."""

from __future__ import annotations

from functools import lru_cache
from typing import Any

from studio_pipeline.config import schemas_dir
from studio_pipeline.errors import SCHEMA_INVALID, PipelineError
from studio_pipeline.validation.schemas import load_json

_KIND_FILES = {
    "studio": "studio.schema.json",
    "dossier": "dossier.schema.json",
    "generated": "generated.schema.json",
    "pipeline": "pipeline.schema.json",
    "deployment": "deployment.schema.json",
}


@lru_cache(maxsize=16)
def load_schema(kind: str) -> dict[str, Any]:
    filename = _KIND_FILES.get(kind)
    if filename is None:
        raise PipelineError(SCHEMA_INVALID, f"unknown schema kind {kind!r}")
    path = schemas_dir() / filename
    if not path.is_file():
        raise PipelineError(SCHEMA_INVALID, f"schema not found: {path}")
    return load_json(path)
