"""Boot-time agent seeding from a JSON spec.

Set ``WISDOM_STUDIO_SEED_PATH`` to point at a JSON file matching :class:`SeedSpec`
and the API's lifespan hook will create the agent (if missing) and prefill its
memories. Idempotent: re-running against an existing ``agent_id`` logs a
warning and skips.

Use cases:
* Conference / kiosk deployments that ship with a guided-tour persona.
* Vertical-product forks that want a starter agent already populated.
* The hosted demo (v0.6) which seeds a fresh visitor agent at boot.
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field, ValidationError, field_validator

from studio_api.schemas import AgentDetail, Archetype, ConversationStarter, LLMProvider, StorageKind
from studio_api.settings import settings
from studio_api.store import get_agent

logger = logging.getLogger(__name__)


class SeedMemory(BaseModel):
    """A single memory entry to capture against the seeded agent."""

    kind: Literal["conversation", "fact", "directive", "session_record"]
    content: dict[str, Any]
    created_at: datetime | None = None

    @field_validator("created_at")
    @classmethod
    def _require_tz_aware(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        # The SDK rejects naive datetimes downstream; rejecting them here gives
        # the operator a much clearer error pointing at the offending entry.
        if value.tzinfo is None or value.tzinfo.utcoffset(value) is None:
            raise ValueError("created_at must be timezone-aware (e.g. ISO 8601 with Z or +00:00)")
        return value


class SeedSpec(BaseModel):
    """Top-level shape of a seed file."""

    agent_id: str
    name: str
    role: str = ""
    archetype: Archetype
    persona: str = ""
    directives: list[str] = Field(default_factory=list)
    memories: list[SeedMemory] = Field(default_factory=list)
    # Optional clickable chips rendered on the agent's empty chat. Same shape
    # as AgentCreate.conversation_starters so the manifest round-trips cleanly.
    conversation_starters: list[ConversationStarter] = Field(default_factory=list, max_length=5)

    llm_provider: LLMProvider = "anthropic"
    llm_model: str | None = None
    storage_kind: StorageKind = "sqlite"


def load_seed(path: Path, *, configured: Path | None = None) -> SeedSpec | None:
    """Read and validate a seed file. Return None and log on any error.

    ``path`` is the absolute, resolved path that will actually be opened.
    ``configured`` is the operator-supplied value (relative or absolute) used
    only for clearer log output — when the operator wrote
    ``WISDOM_STUDIO_SEED_PATH=examples/seeds/researcher.json`` we want to
    surface both that value and the absolute path we tried, so the fix is
    obvious.
    """
    shown = str(configured) if configured is not None else str(path)
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        # Loud (error, not warning) because a missing seed combined with
        # ``WISDOM_STUDIO_EPHEMERAL=true`` produces a dead-end UI ("No agents
        # available") with no in-app way to recover. The log is the only
        # actionable surface.
        logger.error(
            "studio.seed.not_found",
            extra={"seed_path": shown, "resolved_path": str(path)},
        )
        return None
    except json.JSONDecodeError as exc:
        logger.warning(
            "studio.seed.invalid_json",
            extra={"seed_path": shown, "resolved_path": str(path), "error": str(exc)},
        )
        return None
    try:
        return SeedSpec.model_validate(raw)
    except ValidationError as exc:
        logger.warning(
            "studio.seed.schema_invalid",
            extra={"seed_path": shown, "resolved_path": str(path), "errors": exc.errors()},
        )
        return None


def _persist_seed_manifest(spec: SeedSpec) -> AgentDetail:
    """Write the agent manifest, honoring the seed's explicit ``agent_id``."""
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    settings.agents_dir.mkdir(parents=True, exist_ok=True)
    agent_dir = settings.agents_dir / spec.agent_id
    agent_dir.mkdir(parents=True, exist_ok=True)

    detail = AgentDetail(
        agent_id=spec.agent_id,
        name=spec.name,
        role=spec.role,
        archetype=spec.archetype,
        persona=spec.persona,
        directives=list(spec.directives),
        llm_provider=spec.llm_provider,
        llm_model=spec.llm_model,
        storage_kind=spec.storage_kind,
        storage_url=None,
        conversation_starters=list(spec.conversation_starters),
        created_at=datetime.now(UTC),
        last_active_at=None,
    )
    (agent_dir / "agent.json").write_text(
        detail.model_dump_json(indent=2),
        encoding="utf-8",
    )
    return detail


async def apply_seed(spec: SeedSpec) -> None:
    """Create the seeded agent (if missing) and capture its memories.

    Idempotent: returns immediately when ``spec.agent_id`` already exists.
    Memory capture failures are logged but do not abort startup — operators
    can repair the config and reseed manually.
    """
    if get_agent(spec.agent_id) is not None:
        logger.info(
            "studio.seed.skipped_existing",
            extra={"agent_id": spec.agent_id},
        )
        return

    detail = _persist_seed_manifest(spec)
    logger.info(
        "studio.seed.agent_created",
        extra={"agent_id": detail.agent_id, "archetype": spec.archetype},
    )

    if not spec.memories:
        return

    # Booting a session requires a provider key. If we can't get one (no env,
    # no studio.json), capture is skipped — the agent record still exists.
    from studio_api.sessions import session_manager

    try:
        session = await session_manager.get_or_create(spec.agent_id)
    except Exception as exc:  # noqa: BLE001 — startup must not crash on seed errors
        logger.warning(
            "studio.seed.session_boot_failed",
            extra={"agent_id": spec.agent_id, "error": str(exc)},
        )
        return

    captured = 0
    async with session.lock:
        for mem in spec.memories:
            try:
                kwargs: dict[str, Any] = {}
                if mem.created_at is not None:
                    kwargs["created_at"] = mem.created_at
                await session.agent.memory.capture(mem.kind, mem.content, **kwargs)
                captured += 1
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "studio.seed.memory_capture_failed",
                    extra={
                        "agent_id": spec.agent_id,
                        "memory_kind": mem.kind,
                        "error": str(exc),
                    },
                )

    logger.info(
        "studio.seed.memories_captured",
        extra={
            "agent_id": spec.agent_id,
            "captured": captured,
            "total": len(spec.memories),
        },
    )


__all__ = ["SeedMemory", "SeedSpec", "apply_seed", "load_seed"]
