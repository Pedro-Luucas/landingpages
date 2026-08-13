"""Select an AIProvider from config. ``fake`` is always available."""

from __future__ import annotations

import importlib

from studio_pipeline.ai.base import AIProvider
from studio_pipeline.ai.providers.fake import FakeProvider
from studio_pipeline.config import Config, load_config
from studio_pipeline.errors import AI_PROVIDER_ERROR, PipelineError

_OPENAI_NAMES = frozenset({"openai", "openai_compatible"})


def create_provider(config: Config | None = None) -> AIProvider:
    settings = config if config is not None else load_config()
    name = (settings.ai_provider or "fake").strip().lower() or "fake"
    if name == "fake":
        return FakeProvider()
    if name in _OPENAI_NAMES:
        return _load_openai_compatible(settings)
    raise PipelineError(
        AI_PROVIDER_ERROR,
        f"Unknown AI provider {name!r}; expected 'fake', 'openai', or 'openai_compatible'",
    )


def _load_openai_compatible(settings: Config) -> AIProvider:
    try:
        module = importlib.import_module(
            "studio_pipeline.ai.providers.openai_compatible"
        )
    except ImportError as exc:
        raise PipelineError(
            AI_PROVIDER_ERROR,
            "AI provider is not available: module "
            "studio_pipeline.ai.providers.openai_compatible was not found. "
            "Set AI_PROVIDER=fake or add that adapter.",
        ) from exc
    factory = getattr(module, "create_provider", None)
    if callable(factory):
        return factory(settings)
    cls = getattr(module, "OpenAICompatibleProvider", None) or getattr(
        module, "OpenAIProvider", None
    )
    if cls is None:
        raise PipelineError(
            AI_PROVIDER_ERROR,
            "openai_compatible adapter has no create_provider or OpenAICompatibleProvider",
        )
    try:
        return cls(settings)
    except TypeError:
        try:
            return cls(config=settings)
        except TypeError as exc:
            raise PipelineError(
                AI_PROVIDER_ERROR,
                "could not construct OpenAI-compatible provider from config",
            ) from exc
