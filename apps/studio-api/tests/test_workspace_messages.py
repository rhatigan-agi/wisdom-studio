"""Tests for the agent-to-agent MessageBus routes.

Same harness as ``test_workspace_pool.py`` — we monkey-patch
``studio_api.workspace._build_workspace`` to return a stub that exposes the
directory and message-bus surfaces with deterministic in-memory state.
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


class _FakeMessage:
    def __init__(
        self,
        *,
        id: str,
        sender_id: str,
        recipient_id: str | None,
        content: str,
        broadcast_capability: str | None = None,
        thread_id: str | None = None,
        in_reply_to: str | None = None,
        purpose: str = "question",
        expects_reply: bool = True,
    ) -> None:
        self.id = id
        self.workspace_id = "studio-default"
        self.sender_id = sender_id
        self.recipient_id = recipient_id
        self.broadcast_capability = broadcast_capability
        self.content = content
        self.purpose = purpose
        self.thread_id = thread_id or id
        self.in_reply_to = in_reply_to
        self.expects_reply = expects_reply
        self.status = "pending"
        self.read_at: datetime | None = None
        self.replied_at: datetime | None = None
        self.created_at = datetime.now(UTC)

    @property
    def is_broadcast(self) -> bool:
        return self.broadcast_capability is not None


class _FakeMessageBus:
    def __init__(self) -> None:
        self.messages: dict[str, _FakeMessage] = {}
        self._counter = 0

    def _next_id(self, prefix: str = "msg") -> str:
        self._counter += 1
        return f"{prefix}-{self._counter}"

    async def send(
        self,
        *,
        sender_id: str,
        recipient_id: str,
        content: str,
        purpose: Any = "question",
        expects_reply: bool = True,
        **_: Any,
    ) -> str:
        msg_id = self._next_id()
        self.messages[msg_id] = _FakeMessage(
            id=msg_id,
            sender_id=sender_id,
            recipient_id=recipient_id,
            content=content,
            purpose=str(getattr(purpose, "value", purpose)),
            expects_reply=expects_reply,
        )
        return msg_id

    async def broadcast(
        self,
        *,
        sender_id: str,
        broadcast_capability: str,
        content: str,
        purpose: Any = "information",
        **_: Any,
    ) -> str:
        msg_id = self._next_id("bcast")
        self.messages[msg_id] = _FakeMessage(
            id=msg_id,
            sender_id=sender_id,
            recipient_id=None,
            content=content,
            broadcast_capability=broadcast_capability,
            purpose=str(getattr(purpose, "value", purpose)),
            expects_reply=False,
        )
        return msg_id

    async def reply(
        self,
        *,
        sender_id: str,
        in_reply_to: str,
        content: str,
        purpose: Any = "information",
        **_: Any,
    ) -> str:
        original = self.messages.get(in_reply_to)
        if original is None:
            raise LookupError(in_reply_to)
        msg_id = self._next_id("reply")
        self.messages[msg_id] = _FakeMessage(
            id=msg_id,
            sender_id=sender_id,
            recipient_id=original.sender_id,
            content=content,
            thread_id=original.thread_id,
            in_reply_to=in_reply_to,
            purpose=str(getattr(purpose, "value", purpose)),
            expects_reply=False,
        )
        return msg_id

    async def list_inbox(
        self,
        *,
        recipient_id: str,
        recipient_capabilities: list[str],
        unread_only: bool = True,
        include_broadcasts: bool = True,
        limit: int = 100,
    ) -> list[_FakeMessage]:
        rows: list[_FakeMessage] = []
        for m in self.messages.values():
            if m.recipient_id == recipient_id:
                rows.append(m)
            elif (
                include_broadcasts
                and m.broadcast_capability is not None
                and m.broadcast_capability in recipient_capabilities
            ):
                rows.append(m)
        if unread_only:
            rows = [m for m in rows if m.read_at is None]
        return rows[:limit]

    async def list_thread(self, thread_id: str, *, limit: int = 200) -> list[_FakeMessage]:
        return [m for m in self.messages.values() if m.thread_id == thread_id][:limit]

    async def mark_read(self, *, message_id: str, reader_agent_id: str) -> bool:
        msg = self.messages.get(message_id)
        if msg is None or msg.read_at is not None:
            return False
        msg.read_at = datetime.now(UTC)
        return True


class _FakeWorkspace:
    def __init__(self) -> None:
        self._agents: dict[str, _FakeAgentRecord] = {}
        self.directory = _FakeDirectory(self._agents)
        self.messages = _FakeMessageBus()

    async def initialize(self) -> None: ...
    async def close(self) -> None: ...

    async def register_agent(
        self, agent: Any, *, capabilities: list[str] | None = None
    ) -> None:
        self._agents[agent.agent_id] = _FakeAgentRecord(
            agent_id=agent.agent_id,
            capabilities=capabilities or [],
        )


@pytest.fixture
def workspace_app(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Iterator[tuple[TestClient, _FakeWorkspace]]:
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
    # Pre-register two agents so directory lookups succeed for inbox tests.
    fake._agents["agent-a"] = _FakeAgentRecord("agent-a", ["general", "research"])
    fake._agents["agent-b"] = _FakeAgentRecord("agent-b", ["general", "synthesis"])
    import studio_api.sessions as sessions_module

    importlib.reload(sessions_module)
    import studio_api.main as main_module

    importlib.reload(main_module)

    with TestClient(main_module.app) as client:
        yield client, fake


def test_send_requires_all_fields(workspace_app: tuple[TestClient, _FakeWorkspace]) -> None:
    client, _ = workspace_app
    response = client.post(
        "/api/workspace/messages",
        json={"sender_id": "agent-a", "recipient_id": "agent-b", "content": "  "},
    )
    assert response.status_code == 422


def test_send_returns_message_id(workspace_app: tuple[TestClient, _FakeWorkspace]) -> None:
    client, fake = workspace_app
    response = client.post(
        "/api/workspace/messages",
        json={
            "sender_id": "agent-a",
            "recipient_id": "agent-b",
            "content": "What did you find?",
            "purpose": "question",
        },
    )
    assert response.status_code == 200
    msg_id = response.json()["message_id"]
    assert msg_id in fake.messages.messages
    assert fake.messages.messages[msg_id].purpose == "question"


def test_send_returns_403_when_workspace_unavailable(studio_app: TestClient) -> None:
    response = studio_app.post(
        "/api/workspace/messages",
        json={"sender_id": "agent-a", "recipient_id": "agent-b", "content": "hi"},
    )
    assert response.status_code == 403
    assert response.json()["detail"]["error"] == "workspace_unavailable"


def test_broadcast_requires_capability(
    workspace_app: tuple[TestClient, _FakeWorkspace],
) -> None:
    client, _ = workspace_app
    response = client.post(
        "/api/workspace/messages/broadcast",
        json={"sender_id": "agent-a", "broadcast_capability": "", "content": "hi all"},
    )
    assert response.status_code == 422


def test_broadcast_records_message(workspace_app: tuple[TestClient, _FakeWorkspace]) -> None:
    client, fake = workspace_app
    response = client.post(
        "/api/workspace/messages/broadcast",
        json={
            "sender_id": "agent-a",
            "broadcast_capability": "general",
            "content": "Heads up team",
        },
    )
    assert response.status_code == 200
    msg_id = response.json()["message_id"]
    msg = fake.messages.messages[msg_id]
    assert msg.broadcast_capability == "general"
    assert msg.recipient_id is None


def test_inbox_includes_directed_and_broadcasts(
    workspace_app: tuple[TestClient, _FakeWorkspace],
) -> None:
    client, fake = workspace_app
    # agent-a sends a directed message to agent-b
    client.post(
        "/api/workspace/messages",
        json={
            "sender_id": "agent-a",
            "recipient_id": "agent-b",
            "content": "Direct ping",
        },
    )
    # agent-a broadcasts to general (agent-b is in 'general' capability set)
    client.post(
        "/api/workspace/messages/broadcast",
        json={
            "sender_id": "agent-a",
            "broadcast_capability": "general",
            "content": "Team broadcast",
        },
    )
    response = client.get("/api/workspace/agents/agent-b/inbox")
    assert response.status_code == 200
    body = response.json()
    assert len(body) == 2
    # The broadcast carries broadcast_capability and is_broadcast=True
    bcast_rows = [r for r in body if r["is_broadcast"]]
    direct_rows = [r for r in body if not r["is_broadcast"]]
    assert len(bcast_rows) == 1
    assert len(direct_rows) == 1
    _ = fake  # silence unused


def test_thread_returns_send_and_reply(
    workspace_app: tuple[TestClient, _FakeWorkspace],
) -> None:
    client, _ = workspace_app
    send_resp = client.post(
        "/api/workspace/messages",
        json={
            "sender_id": "agent-a",
            "recipient_id": "agent-b",
            "content": "Question?",
        },
    )
    msg_id = send_resp.json()["message_id"]
    reply_resp = client.post(
        f"/api/workspace/messages/{msg_id}/reply",
        json={"sender_id": "agent-b", "content": "Answer."},
    )
    assert reply_resp.status_code == 200
    # The thread id equals the original message id in our fake
    thread_resp = client.get(f"/api/workspace/threads/{msg_id}")
    assert thread_resp.status_code == 200
    thread = thread_resp.json()
    assert len(thread) == 2
    assert thread[1]["in_reply_to"] == msg_id


def test_reply_to_unknown_message_returns_404(
    workspace_app: tuple[TestClient, _FakeWorkspace],
) -> None:
    client, _ = workspace_app
    response = client.post(
        "/api/workspace/messages/no-such-msg/reply",
        json={"sender_id": "agent-b", "content": "hi"},
    )
    assert response.status_code == 404


def test_mark_read_records_once(workspace_app: tuple[TestClient, _FakeWorkspace]) -> None:
    client, _ = workspace_app
    send_resp = client.post(
        "/api/workspace/messages",
        json={
            "sender_id": "agent-a",
            "recipient_id": "agent-b",
            "content": "ping",
        },
    )
    msg_id = send_resp.json()["message_id"]
    first = client.post(
        f"/api/workspace/messages/{msg_id}/read", json={"agent_id": "agent-b"}
    )
    second = client.post(
        f"/api/workspace/messages/{msg_id}/read", json={"agent_id": "agent-b"}
    )
    assert first.status_code == 200 and first.json()["recorded"] is True
    assert second.status_code == 200 and second.json()["recorded"] is False
