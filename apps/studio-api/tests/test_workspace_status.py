"""Tests for the multi-agent workspace foundation (license gate + status route).

The real ``Workspace.initialize()`` validates an Ed25519-signed Enterprise
license, which we can't fake at the SDK level. Instead these tests
monkey-patch ``studio_api.workspace._build_workspace`` to return a stub that
either raises :class:`TierRestrictionError` or behaves as a successful
initialization. This keeps tests fast (no SQLite open, no license verification)
while still exercising the real ``WorkspaceManager`` lifecycle.
"""

from __future__ import annotations

import importlib
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from wisdom_layer.errors import TierRestrictionError


class _FakeAgentRecord:
    """Minimal stand-in for wisdom_layer.workspace.AgentRecord."""

    def __init__(self, agent_id: str, capabilities: list[str]) -> None:
        self.agent_id = agent_id
        self.capabilities = capabilities
        self.registered_at = datetime.now(UTC)
        self.last_seen_at: datetime | None = None
        self.past_success_rate = 0.0
        self.archived_at: datetime | None = None


class _FakeDirectory:
    def __init__(self, store: dict[str, _FakeAgentRecord]) -> None:
        self._store = store

    async def list(
        self,
        *,
        capability: str | None = None,
        active_within: Any = None,
        include_archived: bool = False,
    ) -> list[_FakeAgentRecord]:
        return [
            r
            for r in self._store.values()
            if capability is None or capability in r.capabilities
        ]

    async def get(self, agent_id: str) -> _FakeAgentRecord | None:
        return self._store.get(agent_id)


class _FakeWorkspace:
    """Successful-init Workspace stand-in."""

    def __init__(self) -> None:
        self._agents: dict[str, _FakeAgentRecord] = {}
        self.directory = _FakeDirectory(self._agents)
        self.initialize_calls = 0
        self.close_calls = 0

    async def initialize(self) -> None:
        self.initialize_calls += 1

    async def close(self) -> None:
        self.close_calls += 1

    async def register_agent(
        self,
        agent: Any,
        *,
        capabilities: list[str] | None = None,
    ) -> None:
        self._agents[agent.agent_id] = _FakeAgentRecord(
            agent_id=agent.agent_id,
            capabilities=capabilities or [],
        )


class _GatedWorkspace:
    """Workspace stand-in whose initialize raises TierRestrictionError."""

    async def initialize(self) -> None:
        raise TierRestrictionError(
            feature="multi_agent_workspace",
            required_tier="Enterprise",
            upgrade_url="https://wisdomlayer.ai/pricing",
        )

    async def close(self) -> None:
        return None


def _patch_workspace_factory(builder: Any) -> Any:
    """Reload workspace module then monkey-patch its factory.

    Returns the reloaded module so tests can inspect its singleton state.
    """
    import studio_api.workspace as workspace_module

    importlib.reload(workspace_module)
    workspace_module._build_workspace = builder  # type: ignore[assignment]
    return workspace_module


@pytest.fixture
def studio_app_with_license(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    """Studio app booted with an env-supplied license key.

    The license value is an opaque sentinel — the real license validation is
    bypassed by replacing ``_build_workspace`` (the test patches that
    separately to choose a successful or gated stand-in).
    """
    monkeypatch.setenv("WISDOM_STUDIO_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("WISDOM_LAYER_LICENSE", "test-license-token")

    import studio_api.settings as settings_module

    importlib.reload(settings_module)
    import studio_api.store as store_module

    importlib.reload(store_module)
    import studio_api.workspace as workspace_module

    importlib.reload(workspace_module)
    import studio_api.sessions as sessions_module

    importlib.reload(sessions_module)
    import studio_api.main as main_module

    importlib.reload(main_module)

    with TestClient(main_module.app) as client:
        yield client


def test_status_unavailable_when_license_missing(studio_app: TestClient) -> None:
    """No license → workspace short-circuits without touching the SDK."""
    response = studio_app.get("/api/workspace/status")
    assert response.status_code == 200
    body = response.json()
    assert body["available"] is False
    assert body["reason"] == "license_missing"
    assert body["required_tier"] == "Enterprise"


def test_agents_returns_empty_when_unavailable(studio_app: TestClient) -> None:
    """No license → /api/workspace/agents returns [], not an error."""
    response = studio_app.get("/api/workspace/agents")
    assert response.status_code == 200
    assert response.json() == []


def test_status_unavailable_when_tier_restricted(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """License present but tier insufficient → enterprise_required gate cached."""
    monkeypatch.setenv("WISDOM_STUDIO_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("WISDOM_LAYER_LICENSE", "free-tier-token")

    import studio_api.settings as settings_module

    importlib.reload(settings_module)
    import studio_api.store as store_module

    importlib.reload(store_module)
    workspace_module = _patch_workspace_factory(lambda _key: _GatedWorkspace())
    import studio_api.sessions as sessions_module

    importlib.reload(sessions_module)
    import studio_api.main as main_module

    importlib.reload(main_module)

    with TestClient(main_module.app) as client:
        response = client.get("/api/workspace/status")

    assert response.status_code == 200
    body = response.json()
    assert body["available"] is False
    assert body["reason"] == "enterprise_required"
    assert body["feature"] == "multi_agent_workspace"
    assert body["required_tier"] == "Enterprise"
    assert body["upgrade_url"] == "https://wisdomlayer.ai/pricing"

    # Cached: a second status call must not raise / re-attempt.
    assert workspace_module.workspace_manager.unavailable_reason is not None
    assert workspace_module.workspace_manager.unavailable_reason.reason == "enterprise_required"


def test_status_available_when_initialize_succeeds(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Successful initialize → status returns available=true with workspace metadata."""
    monkeypatch.setenv("WISDOM_STUDIO_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("WISDOM_LAYER_LICENSE", "valid-enterprise-token")

    import studio_api.settings as settings_module

    importlib.reload(settings_module)
    import studio_api.store as store_module

    importlib.reload(store_module)
    fake = _FakeWorkspace()
    _patch_workspace_factory(lambda _key: fake)
    import studio_api.sessions as sessions_module

    importlib.reload(sessions_module)
    import studio_api.main as main_module

    importlib.reload(main_module)

    with TestClient(main_module.app) as client:
        response = client.get("/api/workspace/status")

    assert response.status_code == 200
    body = response.json()
    assert body["available"] is True
    assert body["workspace_id"] == "studio-default"
    assert body["agent_count"] == 0
    assert fake.initialize_calls == 1


def test_initialize_is_idempotent_across_repeated_calls(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Multiple status / agents requests must not repeatedly re-initialize."""
    monkeypatch.setenv("WISDOM_STUDIO_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("WISDOM_LAYER_LICENSE", "valid-enterprise-token")

    import studio_api.settings as settings_module

    importlib.reload(settings_module)
    import studio_api.store as store_module

    importlib.reload(store_module)
    fake = _FakeWorkspace()
    _patch_workspace_factory(lambda _key: fake)
    import studio_api.sessions as sessions_module

    importlib.reload(sessions_module)
    import studio_api.main as main_module

    importlib.reload(main_module)

    with TestClient(main_module.app) as client:
        client.get("/api/workspace/status")
        client.get("/api/workspace/status")
        client.get("/api/workspace/agents")

    assert fake.initialize_calls == 1


def test_agents_lists_registered_agents(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """When agents are bound (simulated via direct register), directory list reflects them."""
    monkeypatch.setenv("WISDOM_STUDIO_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("WISDOM_LAYER_LICENSE", "valid-enterprise-token")

    import studio_api.settings as settings_module

    importlib.reload(settings_module)
    import studio_api.store as store_module

    importlib.reload(store_module)
    fake = _FakeWorkspace()
    workspace_module = _patch_workspace_factory(lambda _key: fake)
    import studio_api.sessions as sessions_module

    importlib.reload(sessions_module)
    import studio_api.main as main_module

    importlib.reload(main_module)

    # Simulate a session bind by calling register on the fake directly through
    # the manager's bind_agent path. Build a minimal stand-in agent + detail.
    class _StubAgent:
        agent_id = "agent-alpha"

    from studio_api.schemas import AgentDetail

    detail = AgentDetail(
        agent_id="agent-alpha",
        name="Alpha",
        role="research",
        archetype="research",
        llm_provider="anthropic",
        storage_kind="sqlite",
        created_at=datetime.now(UTC),
        last_active_at=None,
        persona="",
        directives=[],
        llm_model=None,
        storage_url=None,
        conversation_starters=[],
    )

    import asyncio

    async def _bind_and_list() -> dict[str, Any]:
        await workspace_module.workspace_manager.bind_agent(_StubAgent(), detail)
        return await workspace_module.workspace_manager.list_agents()

    records = asyncio.run(_bind_and_list())
    assert len(records) == 1
    assert records[0]["agent_id"] == "agent-alpha"
    assert "general" in records[0]["capabilities"]
    assert "research" in records[0]["capabilities"]

    # And the HTTP route surfaces the same shape:
    with TestClient(main_module.app) as client:
        response = client.get("/api/workspace/agents")

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["agent_id"] == "agent-alpha"
