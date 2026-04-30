"""Persistence for Studio metadata.

Two artifacts on disk:
- ``data_dir/studio.json`` — process-level config (license key, provider keys)
- ``data_dir/agents/<agent_id>/agent.json`` — per-agent manifest

Per-agent SQLite databases are owned by the SDK and live alongside the manifest.
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from pathlib import Path

from studio_api.schemas import (
    AgentCreate,
    AgentDetail,
    AgentSummary,
    StudioConfig,
)
from studio_api.settings import settings

logger = logging.getLogger(__name__)


def _ensure_dirs() -> None:
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    settings.agents_dir.mkdir(parents=True, exist_ok=True)


# Fields that are persisted to studio.json. The remaining StudioConfig fields
# (banner_html, session_ttl_minutes, etc.) are runtime-only — they come from
# environment variables on every boot and never touch disk.
_PERSISTED_FIELDS: tuple[str, ...] = ("license_key", "provider_keys", "initialized")


def _runtime_overlay() -> dict[str, object]:
    """Read-only fields injected from current env settings on every load."""
    return {
        "banner_html": settings.banner_html,
        "session_ttl_minutes": settings.session_ttl_minutes,
        "docs_url": settings.docs_url,
        "signup_url": settings.signup_url,
        "locked_llm": settings.locked_llm,
        "hide_settings": settings.hide_settings,
        "hide_agent_crud": settings.hide_agent_crud,
    }


def load_studio_config() -> StudioConfig:
    _ensure_dirs()
    path = settings.config_path
    persisted: dict[str, object] = {}
    if path.exists():
        raw = json.loads(path.read_text(encoding="utf-8"))
        persisted = {k: raw.get(k) for k in _PERSISTED_FIELDS if k in raw}
    return StudioConfig.model_validate({**persisted, **_runtime_overlay()})


def save_studio_config(config: StudioConfig) -> None:
    """Persist only the user-saved fields. Runtime/env fields are not written."""
    _ensure_dirs()
    payload = config.model_dump(include=set(_PERSISTED_FIELDS))
    settings.config_path.write_text(
        json.dumps(payload, indent=2, default=str),
        encoding="utf-8",
    )


def _agent_dir(agent_id: str) -> Path:
    return settings.agents_dir / agent_id


def _manifest_path(agent_id: str) -> Path:
    return _agent_dir(agent_id) / "agent.json"


def storage_path_for(agent_id: str) -> Path:
    return _agent_dir(agent_id) / "agent.db"


def list_agents() -> list[AgentSummary]:
    _ensure_dirs()
    summaries: list[AgentSummary] = []
    for agent_dir in sorted(settings.agents_dir.iterdir()):
        if not agent_dir.is_dir():
            continue
        manifest = agent_dir / "agent.json"
        if not manifest.exists():
            continue
        raw = json.loads(manifest.read_text(encoding="utf-8"))
        summaries.append(AgentSummary.model_validate(raw))
    return summaries


def get_agent(agent_id: str) -> AgentDetail | None:
    path = _manifest_path(agent_id)
    if not path.exists():
        return None
    raw = json.loads(path.read_text(encoding="utf-8"))
    return AgentDetail.model_validate(raw)


def slugify(name: str) -> str:
    cleaned = "".join(ch.lower() if ch.isalnum() else "-" for ch in name).strip("-")
    return cleaned or "agent"


def create_agent(spec: AgentCreate) -> AgentDetail:
    _ensure_dirs()
    base_id = slugify(spec.name)
    agent_id = base_id
    counter = 1
    while _agent_dir(agent_id).exists():
        counter += 1
        agent_id = f"{base_id}-{counter}"

    _agent_dir(agent_id).mkdir(parents=True, exist_ok=True)
    detail = AgentDetail(
        agent_id=agent_id,
        name=spec.name,
        role=spec.role,
        archetype=spec.archetype,
        persona=spec.persona,
        directives=list(spec.directives),
        llm_provider=spec.llm_provider,
        llm_model=spec.llm_model,
        llm_tier=spec.llm_tier,  # type: ignore[arg-type]
        storage_kind=spec.storage_kind,
        storage_url=spec.storage_url,
        conversation_starters=list(spec.conversation_starters),
        created_at=datetime.now(UTC),
        last_active_at=None,
    )
    _manifest_path(agent_id).write_text(
        detail.model_dump_json(indent=2),
        encoding="utf-8",
    )
    logger.info(
        "studio.agent.created",
        extra={"agent_id": agent_id, "archetype": spec.archetype},
    )
    return detail


def touch_agent(agent_id: str) -> None:
    detail = get_agent(agent_id)
    if detail is None:
        return
    updated = detail.model_copy(update={"last_active_at": datetime.now(UTC)})
    _manifest_path(agent_id).write_text(
        updated.model_dump_json(indent=2),
        encoding="utf-8",
    )


def delete_agent(agent_id: str) -> bool:
    agent_dir = _agent_dir(agent_id)
    if not agent_dir.exists():
        return False
    for child in sorted(agent_dir.glob("**/*"), reverse=True):
        if child.is_file():
            child.unlink()
        elif child.is_dir():
            child.rmdir()
    agent_dir.rmdir()
    return True


__all__ = [
    "create_agent",
    "delete_agent",
    "get_agent",
    "list_agents",
    "load_studio_config",
    "save_studio_config",
    "slugify",
    "storage_path_for",
    "touch_agent",
]
