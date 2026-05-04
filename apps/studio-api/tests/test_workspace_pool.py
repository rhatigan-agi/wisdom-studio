"""Tests for the shared-memory pool, team insights, and provenance walk routes.

Same harness as ``test_workspace_status.py`` — we monkey-patch
``studio_api.workspace._build_workspace`` to return a stub that exposes the
pool, directory, and team-dream surfaces with deterministic in-memory state.
"""

from __future__ import annotations

import importlib
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient


class _FakeAgentRecord:
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

    async def list(self, **_: Any) -> list[_FakeAgentRecord]:
        return list(self._store.values())

    async def get(self, agent_id: str) -> _FakeAgentRecord | None:
        return self._store.get(agent_id)


class _FakeSharedMemory:
    def __init__(
        self,
        *,
        id: str,
        contributor_id: str,
        source_memory_id: str,
        content: str,
        reason: str = "",
        visibility: str = "TEAM",
    ) -> None:
        self.id = id
        self.workspace_id = "studio-default"
        self.contributor_id = contributor_id
        self.source_memory_id = source_memory_id
        self.visibility = visibility
        self.content = content
        self.reason = reason
        self.endorsement_count = 0
        self.contention_count = 0
        self.base_score = 0.0
        self.shared_at = datetime.now(UTC)
        self.archived_at: datetime | None = None

    @property
    def team_score(self) -> float:
        return self.base_score + 0.1 * self.endorsement_count - 0.2 * self.contention_count


class _FakeTeamInsight:
    def __init__(self, *, id: str, content: str, contributor_count: int) -> None:
        self.id = id
        self.workspace_id = "studio-default"
        self.content = content
        self.synthesis_prompt_hash = "hash-abc"
        self.contributor_count = contributor_count
        self.dream_cycle_id: str | None = None
        self.created_at = datetime.now(UTC)
        self.archived_at: datetime | None = None


class _FakeContribution:
    def __init__(
        self,
        *,
        shared_memory_id: str,
        contributor_agent_id: str,
        source_memory_id: str,
        shared_content: str,
    ) -> None:
        self.shared_memory_id = shared_memory_id
        self.contributor_agent_id = contributor_agent_id
        self.source_memory_id = source_memory_id
        self.shared_content = shared_content
        self.contribution_weight = 1.0


class _FakeProvenance:
    def __init__(self, insight: _FakeTeamInsight, contributions: list[_FakeContribution]) -> None:
        self.team_insight = insight
        self.contributions = contributions


class _FakePool:
    def __init__(self) -> None:
        self.shared: dict[str, _FakeSharedMemory] = {}
        self.insights: dict[str, _FakeTeamInsight] = {}
        self.contributions_by_insight: dict[str, list[_FakeContribution]] = {}

    async def list(
        self,
        *,
        contributor_id: str | None = None,
        min_base_score: float | None = None,
        limit: int = 100,
        **_: Any,
    ) -> list[_FakeSharedMemory]:
        rows = list(self.shared.values())
        if contributor_id is not None:
            rows = [r for r in rows if r.contributor_id == contributor_id]
        if min_base_score is not None:
            rows = [r for r in rows if r.base_score >= min_base_score]
        return rows[:limit]

    async def list_team_insights(
        self,
        *,
        include_archived: bool = False,  # noqa: ARG002 — match SDK signature
        limit: int = 100,
    ) -> list[_FakeTeamInsight]:
        return list(self.insights.values())[:limit]

    async def endorse(self, shared_id: str, *, endorsing_agent_id: str) -> bool:
        row = self.shared.get(shared_id)
        if row is None:
            raise LookupError(shared_id)
        # Track unique endorsers to keep the test contract realistic
        seen = getattr(row, "_endorsers", set())
        if endorsing_agent_id in seen:
            return False
        seen.add(endorsing_agent_id)
        row._endorsers = seen  # type: ignore[attr-defined]
        row.endorsement_count = len(seen)
        return True

    async def contest(
        self, shared_id: str, *, contesting_agent_id: str, reason: str
    ) -> bool:
        row = self.shared.get(shared_id)
        if row is None:
            raise LookupError(shared_id)
        seen = getattr(row, "_contesters", set())
        if contesting_agent_id in seen:
            return False
        seen.add(contesting_agent_id)
        row._contesters = seen  # type: ignore[attr-defined]
        row.contention_count = len(seen)
        row._contest_reason = reason  # type: ignore[attr-defined]
        return True

    async def walk_provenance(self, insight_id: str) -> _FakeProvenance:
        insight = self.insights.get(insight_id)
        if insight is None:
            raise LookupError(insight_id)
        return _FakeProvenance(insight, self.contributions_by_insight.get(insight_id, []))


class _FakeWorkspace:
    def __init__(self) -> None:
        self._agents: dict[str, _FakeAgentRecord] = {}
        self.directory = _FakeDirectory(self._agents)
        self.pool = _FakePool()
        self.team_synthesize_calls: list[dict[str, Any]] = []
        self._synth_response: _FakeTeamInsight | None = None

    async def initialize(self) -> None: ...
    async def close(self) -> None: ...

    async def register_agent(
        self, agent: Any, *, capabilities: list[str] | None = None
    ) -> None:
        self._agents[agent.agent_id] = _FakeAgentRecord(
            agent_id=agent.agent_id,
            capabilities=capabilities or [],
        )

    async def team_synthesize(
        self,
        synthesizer: Any,
        *,
        min_contributors: int = 2,
        **_: Any,
    ) -> _FakeTeamInsight | None:
        self.team_synthesize_calls.append(
            {"synthesizer_id": synthesizer.agent_id, "min_contributors": min_contributors}
        )
        return self._synth_response


@pytest.fixture
def workspace_app(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[tuple[TestClient, _FakeWorkspace]]:
    """Boot Studio with a license + a successfully-initializing fake workspace."""
    monkeypatch.setenv("WISDOM_STUDIO_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("WISDOM_LAYER_LICENSE", "valid-enterprise-token")

    import studio_api.settings as settings_module

    importlib.reload(settings_module)
    import studio_api.store as store_module

    importlib.reload(store_module)
    import studio_api.workspace as workspace_module

    importlib.reload(workspace_module)
    fake = _FakeWorkspace()
    workspace_module._build_workspace = lambda _key: fake  # type: ignore[assignment]
    import studio_api.sessions as sessions_module

    importlib.reload(sessions_module)
    import studio_api.main as main_module

    importlib.reload(main_module)

    with TestClient(main_module.app) as client:
        yield client, fake


def test_share_returns_403_when_workspace_unavailable(studio_app: TestClient) -> None:
    """No license → share endpoint surfaces the structured workspace_unavailable body."""
    response = studio_app.post(
        "/api/agents/whatever/memory/mem-1/share",
        json={"visibility": "TEAM", "reason": "test"},
    )
    assert response.status_code == 403
    body = response.json()
    detail = body["detail"]
    assert detail["error"] == "workspace_unavailable"
    assert detail["reason"] == "license_missing"


def test_share_rejects_private_visibility(workspace_app: tuple[TestClient, _FakeWorkspace]) -> None:
    """Sharing with PRIVATE visibility is a contract violation → 422 before any side effects."""
    client, _ = workspace_app
    # Even though the agent doesn't exist, validation runs before lookup, so
    # we get 422 from the visibility guard, not 404.
    response = client.post(
        "/api/agents/agent-x/memory/mem-1/share",
        json={"visibility": "PRIVATE"},
    )
    assert response.status_code == 422
    assert "PRIVATE" in response.json()["detail"]


def test_list_shared_memory_returns_empty_when_unavailable(studio_app: TestClient) -> None:
    """No license → 403 (matches share-route behavior; UI uses /api/workspace/status to gate)."""
    response = studio_app.get("/api/workspace/shared-memory")
    assert response.status_code == 403


def test_list_shared_memory_returns_rows(workspace_app: tuple[TestClient, _FakeWorkspace]) -> None:
    client, fake = workspace_app
    fake.pool.shared["sh-1"] = _FakeSharedMemory(
        id="sh-1", contributor_id="agent-a", source_memory_id="mem-1", content="hello world"
    )
    fake.pool.shared["sh-2"] = _FakeSharedMemory(
        id="sh-2", contributor_id="agent-b", source_memory_id="mem-2", content="another"
    )

    response = client.get("/api/workspace/shared-memory")
    assert response.status_code == 200
    body = response.json()
    assert len(body) == 2
    ids = {row["id"] for row in body}
    assert ids == {"sh-1", "sh-2"}
    # All projection fields present
    first = body[0]
    for key in (
        "id",
        "workspace_id",
        "contributor_id",
        "source_memory_id",
        "visibility",
        "content",
        "reason",
        "endorsement_count",
        "contention_count",
        "base_score",
        "team_score",
        "shared_at",
    ):
        assert key in first


def test_endorse_requires_agent_id(workspace_app: tuple[TestClient, _FakeWorkspace]) -> None:
    client, fake = workspace_app
    fake.pool.shared["sh-1"] = _FakeSharedMemory(
        id="sh-1", contributor_id="agent-a", source_memory_id="mem-1", content="x"
    )
    response = client.post("/api/workspace/shared-memory/sh-1/endorse", json={})
    assert response.status_code == 422
    assert "agent_id" in response.json()["detail"]


def test_endorse_records_and_is_idempotent(
    workspace_app: tuple[TestClient, _FakeWorkspace],
) -> None:
    client, fake = workspace_app
    fake.pool.shared["sh-1"] = _FakeSharedMemory(
        id="sh-1", contributor_id="agent-a", source_memory_id="mem-1", content="x"
    )
    first = client.post(
        "/api/workspace/shared-memory/sh-1/endorse", json={"agent_id": "agent-b"}
    )
    second = client.post(
        "/api/workspace/shared-memory/sh-1/endorse", json={"agent_id": "agent-b"}
    )
    assert first.status_code == 200 and first.json()["recorded"] is True
    assert second.status_code == 200 and second.json()["recorded"] is False
    assert fake.pool.shared["sh-1"].endorsement_count == 1


def test_contest_requires_reason(workspace_app: tuple[TestClient, _FakeWorkspace]) -> None:
    client, fake = workspace_app
    fake.pool.shared["sh-1"] = _FakeSharedMemory(
        id="sh-1", contributor_id="agent-a", source_memory_id="mem-1", content="x"
    )
    response = client.post(
        "/api/workspace/shared-memory/sh-1/contest", json={"agent_id": "agent-c"}
    )
    assert response.status_code == 422
    assert "reason" in response.json()["detail"]


def test_team_dream_requires_synthesizer_id(
    workspace_app: tuple[TestClient, _FakeWorkspace],
) -> None:
    client, _ = workspace_app
    response = client.post("/api/workspace/team-dream", json={})
    assert response.status_code == 422


def test_walk_provenance_returns_chain_without_private_content(
    workspace_app: tuple[TestClient, _FakeWorkspace],
) -> None:
    """Provenance contributions must carry source_memory_id but never private content.

    The patent-defensible isolation invariant is that walk_provenance returns
    the *workspace-visible* shared content plus opaque back-pointers — Studio
    never receives (and therefore can never surface) the contributor's
    underlying private memory.
    """
    client, fake = workspace_app
    insight = _FakeTeamInsight(
        id="insight-1", content="Combined finding", contributor_count=2
    )
    fake.pool.insights["insight-1"] = insight
    fake.pool.contributions_by_insight["insight-1"] = [
        _FakeContribution(
            shared_memory_id="sh-1",
            contributor_agent_id="agent-a",
            source_memory_id="opaque-private-id-a",
            shared_content="public version of a's contribution",
        ),
        _FakeContribution(
            shared_memory_id="sh-2",
            contributor_agent_id="agent-b",
            source_memory_id="opaque-private-id-b",
            shared_content="public version of b's contribution",
        ),
    ]

    response = client.get("/api/workspace/team-insights/insight-1/provenance")
    assert response.status_code == 200
    body = response.json()
    assert body["team_insight"]["id"] == "insight-1"
    assert len(body["contributions"]) == 2
    for contribution in body["contributions"]:
        assert "source_memory_id" in contribution  # boundary back-pointer present
        assert "shared_content" in contribution  # workspace-visible content present
        # The contract: NO private-memory content field. If a future SDK ever
        # adds one, this assertion fails loudly so we can decide whether the
        # boundary moved.
        assert "private_content" not in contribution
        assert "raw_memory" not in contribution


def test_walk_provenance_404_when_insight_missing(
    workspace_app: tuple[TestClient, _FakeWorkspace],
) -> None:
    client, _ = workspace_app
    response = client.get("/api/workspace/team-insights/does-not-exist/provenance")
    assert response.status_code == 404
