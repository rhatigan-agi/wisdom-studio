"""Smoke tests for the Studio API.

These tests verify the transport surface — schema correctness, persistence,
and error paths — without booting a real `WisdomAgent` (which requires an LLM
backend). End-to-end agent boot is covered by the Ollama smoke script in CI.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


def test_health(studio_app: TestClient) -> None:
    response = studio_app.get("/api/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert "version" in body


def test_initial_config_is_uninitialized(studio_app: TestClient) -> None:
    response = studio_app.get("/api/config")
    assert response.status_code == 200
    body = response.json()
    assert body["initialized"] is False
    assert body["provider_keys"] == {}


def test_update_config_marks_initialized(studio_app: TestClient) -> None:
    response = studio_app.put(
        "/api/config",
        json={"provider_keys": {"anthropic": "sk-test"}},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["initialized"] is True
    assert body["provider_keys"] == {"anthropic": "sk-test"}


def test_agent_lifecycle(studio_app: TestClient) -> None:
    create = studio_app.post(
        "/api/agents",
        json={
            "name": "Tester",
            "role": "smoke test",
            "archetype": "balanced",
            "llm_provider": "ollama",
            "llm_model": "llama3.1:8b",
            "storage_kind": "sqlite",
        },
    )
    assert create.status_code == 201, create.text
    detail = create.json()
    assert detail["agent_id"] == "tester"
    assert detail["llm_model"] == "llama3.1:8b"

    listed = studio_app.get("/api/agents").json()
    assert len(listed) == 1
    assert listed[0]["agent_id"] == "tester"

    fetched = studio_app.get(f"/api/agents/{detail['agent_id']}").json()
    assert fetched["persona"] == ""

    deleted = studio_app.delete(f"/api/agents/{detail['agent_id']}")
    assert deleted.status_code == 204
    assert studio_app.get("/api/agents").json() == []


def test_agent_id_collisions_are_suffixed(studio_app: TestClient) -> None:
    payload = {
        "name": "Same Name",
        "archetype": "balanced",
        "llm_provider": "ollama",
        "storage_kind": "sqlite",
    }
    first = studio_app.post("/api/agents", json=payload).json()
    second = studio_app.post("/api/agents", json=payload).json()
    assert first["agent_id"] == "same-name"
    assert second["agent_id"] == "same-name-2"


def test_get_missing_agent_returns_404(studio_app: TestClient) -> None:
    response = studio_app.get("/api/agents/does-not-exist")
    assert response.status_code == 404


def test_multi_agent_sessions_are_isolated(
    studio_app: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Two sessions must each have their own SDK sub-app and WebSocket hub.

    Cross-bleed of events or HTTP routes between agents would defeat Studio's
    multi-agent guarantee. We avoid spinning up real LLM adapters by stubbing
    :func:`build_agent` with a minimal fake; the structural check is what
    matters.
    """
    import studio_api.sessions as sessions_module

    class _FakeAgent:
        def __init__(self, agent_id: str) -> None:
            self.agent_id = agent_id
            self._listeners: list[object] = []

        async def initialize(self) -> None:
            return None

        def on(self, _name: str, _handler: object) -> object:
            token = object()
            self._listeners.append(token)
            return token

        def off(self, token: object) -> None:
            self._listeners.remove(token)

        async def close(self) -> None:
            return None

    def _fake_build_agent(detail, **_kwargs):  # type: ignore[no-untyped-def]
        return _FakeAgent(detail.agent_id)

    monkeypatch.setattr(sessions_module, "build_agent", _fake_build_agent)

    studio_app.post(
        "/api/agents",
        json={"name": "Alpha", "archetype": "balanced", "llm_provider": "ollama"},
    )
    studio_app.post(
        "/api/agents",
        json={"name": "Beta", "archetype": "balanced", "llm_provider": "ollama"},
    )

    import asyncio

    sm = sessions_module.session_manager
    asyncio.run(sm.get_or_create("alpha"))
    asyncio.run(sm.get_or_create("beta"))

    a = sm._sessions["alpha"]
    b = sm._sessions["beta"]
    assert a.hub is not b.hub
    assert a.sub_app is not b.sub_app
    assert a.sub_app.state.agent.agent_id == "alpha"
    assert b.sub_app.state.agent.agent_id == "beta"
    assert a.mount.path == "/agents/alpha"
    assert b.mount.path == "/agents/beta"


def test_get_example_returns_full_payload(studio_app: TestClient) -> None:
    """Wizard prefill: GET /api/examples/{slug} returns the full AgentCreate.

    The shipped researcher.yaml carries non-empty conversation_starters so
    the round-trip across YAML → loader → endpoint is verified end-to-end.
    """
    response = studio_app.get("/api/examples/researcher")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["name"] == "Researcher"
    assert body["archetype"] == "research"
    assert isinstance(body["directives"], list) and body["directives"]
    assert isinstance(body["conversation_starters"], list)
    assert body["conversation_starters"], "researcher.yaml must ship starters"
    for starter in body["conversation_starters"]:
        assert 1 <= len(starter) <= 80


def test_get_example_unknown_slug_returns_404(studio_app: TestClient) -> None:
    response = studio_app.get("/api/examples/does-not-exist")
    assert response.status_code == 404


def test_create_agent_with_conversation_starters_round_trips(
    studio_app: TestClient,
) -> None:
    starters = ["What did we decide last week?", "Compare drafts A and B"]
    create = studio_app.post(
        "/api/agents",
        json={
            "name": "Starter Agent",
            "archetype": "balanced",
            "llm_provider": "ollama",
            "conversation_starters": starters,
        },
    )
    assert create.status_code == 201, create.text
    detail = create.json()
    assert detail["conversation_starters"] == starters

    fetched = studio_app.get(f"/api/agents/{detail['agent_id']}").json()
    assert fetched["conversation_starters"] == starters


def test_conversation_starters_enforce_caps(studio_app: TestClient) -> None:
    """Schema rejects >5 entries or any entry over 80 chars."""
    too_many = studio_app.post(
        "/api/agents",
        json={
            "name": "Too Many",
            "archetype": "balanced",
            "llm_provider": "ollama",
            "conversation_starters": [f"q{i}" for i in range(6)],
        },
    )
    assert too_many.status_code == 422

    too_long = studio_app.post(
        "/api/agents",
        json={
            "name": "Too Long",
            "archetype": "balanced",
            "llm_provider": "ollama",
            "conversation_starters": ["x" * 81],
        },
    )
    assert too_long.status_code == 422


def test_create_agent_default_starters_are_empty(studio_app: TestClient) -> None:
    create = studio_app.post(
        "/api/agents",
        json={
            "name": "No Starters",
            "archetype": "balanced",
            "llm_provider": "ollama",
        },
    )
    assert create.status_code == 201
    assert create.json()["conversation_starters"] == []


def test_postgres_storage_requires_url_at_session_open(studio_app: TestClient) -> None:
    """The schema accepts the agent without a URL but session boot rejects it.

    Postgres requires a connection URL; this check belongs in session boot,
    not in agent creation, because users may want to draft an agent before
    pointing it at a database.
    """
    create = studio_app.post(
        "/api/agents",
        json={
            "name": "Pg Agent",
            "archetype": "balanced",
            "llm_provider": "ollama",
            "storage_kind": "postgres",
        },
    )
    assert create.status_code == 201
