"""AIProvider protocol (plan §8 stage F)."""

from __future__ import annotations

from typing import Any, Protocol, TypedDict


class BrandAnalysis(TypedDict, total=False):
    colors: dict[str, str]
    fontHeading: str
    fontBody: str
    radius: str
    mood: list[str]
    imageTreatment: str
    warnings: list[str]


class MediaSelection(TypedDict, total=False):
    selected: list[Any]
    rejected: list[Any]
    warnings: list[str]


class GeneratedSite(TypedDict, total=False):
    schemaVersion: int
    studioId: str
    generationId: str
    inputHash: str
    provider: str
    model: str
    promptVersion: str
    templateId: str
    branding: dict[str, Any]
    copy: dict[str, Any]
    sections: list[dict[str, Any]]
    assetPaths: list[str]
    factualClaims: list[dict[str, Any]]
    warnings: list[str]
    createdAt: str


class AIProvider(Protocol):
    def analyze_brand(
        self,
        dossier: dict[str, Any],
        asset_paths: list[str],
    ) -> BrandAnalysis: ...

    def select_media(
        self,
        dossier: dict[str, Any],
        candidates: list[Any],
    ) -> MediaSelection: ...

    def generate_site(
        self,
        dossier: dict[str, Any],
        brand: BrandAnalysis,
        selected_media: MediaSelection,
    ) -> GeneratedSite: ...
