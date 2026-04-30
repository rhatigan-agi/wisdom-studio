"""Pydantic schemas for the Studio control-plane API.

Mirrored on the frontend as TypeScript types in
``apps/studio-web/src/types/api.ts``. Keep both sides in lockstep.

Per-agent operations (memory, dreams, directives, status, …) are served by
the SDK dashboard's own routers mounted under ``/agents/{agent_id}``, so
their request/response shapes are owned by the SDK — Studio does not redefine
them here.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, Field, StringConstraints

ConversationStarter = Annotated[
    str, StringConstraints(min_length=1, max_length=80, strip_whitespace=True)
]

LLMProvider = Literal["anthropic", "openai", "gemini", "ollama", "litellm"]
StorageKind = Literal["sqlite", "postgres"]
Archetype = Literal[
    "balanced",
    "research",
    "coding_assistant",
    "consumer_support",
    "strategic_advisors",
    "lightweight_local",
]


# --- Studio config (first-run setup) -----------------------------------------


class LockedLLM(BaseModel):
    """A pinned provider/model combination.

    Set via ``WISDOM_STUDIO_LOCK_PROVIDER`` to force every agent in this
    deployment to use a specific provider (and optionally a specific model).
    Used by vertical-product forks (e.g. Claude-only kiosk agents).
    """

    provider: LLMProvider
    model: str | None = None


class StudioConfig(BaseModel):
    """The shape returned from ``GET /api/config``.

    Fields fall into two groups:

    * **Persisted** (saved to ``studio.json`` via the wizard / Settings page):
      ``license_key``, ``provider_keys``, ``initialized``.
    * **Runtime** (read-only, sourced from environment variables at boot):
      banner, session timer, docs URL, lock-provider, hide-settings,
      hide-agent-crud. Forkers set these to tailor a deployment without
      changing code.
    """

    license_key: str | None = None
    provider_keys: dict[LLMProvider, str] = Field(default_factory=dict)
    initialized: bool = False

    # Runtime-only (read-only, set via WISDOM_STUDIO_* env vars).
    banner_html: str | None = None
    session_ttl_minutes: int | None = None
    docs_url: str | None = None
    signup_url: str | None = None
    locked_llm: LockedLLM | None = None
    hide_settings: bool = False
    hide_agent_crud: bool = False


class StudioConfigUpdate(BaseModel):
    license_key: str | None = None
    provider_keys: dict[LLMProvider, str] | None = None


# --- Agent management --------------------------------------------------------


class AgentCreate(BaseModel):
    name: str
    role: str = ""
    archetype: Archetype = "balanced"
    persona: str = ""
    directives: list[str] = Field(default_factory=list)

    llm_provider: LLMProvider
    llm_model: str | None = None
    llm_tier: Literal["sota", "high", "mid", "low"] | None = None

    storage_kind: StorageKind = "sqlite"
    storage_url: str | None = None  # Postgres URL when storage_kind == postgres

    # Optional clickable chips rendered on an empty chat. Solves blank-page
    # paralysis in conference, internal-team, and marketing-embed contexts.
    conversation_starters: list[ConversationStarter] = Field(
        default_factory=list, max_length=5
    )


# --- Examples ----------------------------------------------------------------


class ExampleSummary(BaseModel):
    """Lightweight view of a YAML reference config for the wizard picker."""

    slug: str
    name: str
    role: str
    archetype: Archetype
    persona_preview: str
    directive_count: int


class AgentSummary(BaseModel):
    agent_id: str
    name: str
    role: str
    archetype: Archetype
    llm_provider: LLMProvider
    storage_kind: StorageKind
    created_at: datetime
    last_active_at: datetime | None = None


class AgentDetail(AgentSummary):
    persona: str
    directives: list[str]
    llm_model: str | None
    storage_url: str | None
    conversation_starters: list[ConversationStarter] = Field(default_factory=list)


# --- Chat (Studio-owned wrapper around respond_loop) -------------------------


class ChatRequest(BaseModel):
    message: str
    capture: bool = True


class ChatResponse(BaseModel):
    """Mirror of :class:`wisdom_layer.integration.respond.RespondResult`.

    Studio strips the SDK helper's ``metadata`` field (Studio surfaces the
    SDK's own status/provenance routes for that detail).
    """

    response: str
    memories_used: int = 0
    composed_chars: int = 0
    truncated_layers: list[str] = Field(default_factory=list)
    snapshot_id: str = ""
