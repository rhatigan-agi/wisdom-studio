"""Factories that translate Studio's API schemas into Wisdom Layer SDK objects.

This module is the only place Studio touches SDK construction. Every public
surface of the SDK referenced here is part of `wisdom_layer.__all__` — Studio
never imports private symbols.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from wisdom_layer import AdminDefaults, AgentConfig, WisdomAgent
from wisdom_layer.config import PersonalityConfig

from studio_api.schemas import AgentDetail, Archetype, LLMProvider, StorageKind
from studio_api.store import storage_path_for

if TYPE_CHECKING:
    from wisdom_layer.llm.base import BaseLLMAdapter
    from wisdom_layer.storage.base import BaseBackend

logger = logging.getLogger(__name__)


def _admin_defaults_for(archetype: Archetype) -> AdminDefaults:
    match archetype:
        case "balanced":
            return AdminDefaults.balanced()
        case "research":
            return AdminDefaults.for_research()
        case "coding_assistant":
            return AdminDefaults.for_coding_assistant()
        case "consumer_support":
            return AdminDefaults.for_consumer_support()
        case "strategic_advisors":
            return AdminDefaults.for_strategic_advisors()
        case "lightweight_local":
            return AdminDefaults.for_lightweight_local()


def build_llm_adapter(
    provider: LLMProvider,
    api_key: str,
    *,
    model: str | None = None,
) -> BaseLLMAdapter:
    """Construct an SDK LLM adapter for the given provider."""
    match provider:
        case "anthropic":
            from wisdom_layer.llm.anthropic import AnthropicAdapter

            return (
                AnthropicAdapter(api_key=api_key, model=model)
                if model
                else AnthropicAdapter(api_key=api_key)
            )
        case "openai":
            from wisdom_layer.llm.openai import OpenAIAdapter

            return (
                OpenAIAdapter(api_key=api_key, model=model)
                if model
                else OpenAIAdapter(api_key=api_key)
            )
        case "gemini":
            from wisdom_layer.llm.gemini import GeminiAdapter

            return (
                GeminiAdapter(api_key=api_key, model=model)
                if model
                else GeminiAdapter(api_key=api_key)
            )
        case "ollama":
            from wisdom_layer.llm.ollama import OllamaAdapter

            return OllamaAdapter(model=model) if model else OllamaAdapter()
        case "litellm":
            from wisdom_layer.llm.litellm import LiteLLMAdapter

            return (
                LiteLLMAdapter(api_key=api_key, model=model)
                if model
                else LiteLLMAdapter(api_key=api_key)
            )


def build_storage_backend(kind: StorageKind, agent_id: str, url: str | None) -> BaseBackend:
    match kind:
        case "sqlite":
            from wisdom_layer.storage.sqlite import SQLiteBackend

            return SQLiteBackend(str(storage_path_for(agent_id)))
        case "postgres":
            if not url:
                raise ValueError("Postgres storage requires a connection URL")
            from wisdom_layer.storage.postgres import PostgresBackend

            return PostgresBackend(url)


def build_agent(
    detail: AgentDetail,
    *,
    provider_api_key: str,
    license_key: str | None,
) -> WisdomAgent:
    """Construct a `WisdomAgent` from a Studio agent detail."""
    config = AgentConfig.for_dev(
        name=detail.name,
        role=detail.role,
        directives=list(detail.directives),
        api_key=license_key or "",
        admin_defaults=_admin_defaults_for(detail.archetype),
        personality=PersonalityConfig(),
    )
    llm = build_llm_adapter(detail.llm_provider, provider_api_key, model=detail.llm_model)
    backend = build_storage_backend(detail.storage_kind, detail.agent_id, detail.storage_url)
    return WisdomAgent(
        agent_id=detail.agent_id,
        config=config,
        llm=llm,
        backend=backend,
    )


__all__ = ["build_agent", "build_llm_adapter", "build_storage_backend"]
