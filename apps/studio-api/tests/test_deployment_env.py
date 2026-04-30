"""Tests for the v0.5 deployment env vars.

The seven ``WISDOM_STUDIO_*`` settings (banner, session TTL, seed path, lock
provider, hide settings, hide agent CRUD, docs URL) are first-class Studio
features that forkers tune to tailor a deployment without changing code.
These tests cover the backend surface; component-level frontend tests live
in ``apps/studio-web/`` (vitest).
"""

from __future__ import annotations

import importlib
import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

# --- helpers -----------------------------------------------------------------


def _boot_studio(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, **env: str) -> TestClient:
    """Boot the Studio app with an isolated data dir and arbitrary env overrides."""
    monkeypatch.setenv("WISDOM_STUDIO_DATA_DIR", str(tmp_path))
    for key, value in env.items():
        monkeypatch.setenv(key, value)

    import studio_api.settings as settings_module

    importlib.reload(settings_module)
    import studio_api.store as store_module

    importlib.reload(store_module)
    import studio_api.seeds as seeds_module

    importlib.reload(seeds_module)
    import studio_api.sdk_mount as sdk_mount_module

    importlib.reload(sdk_mount_module)
    import studio_api.sessions as sessions_module

    importlib.reload(sessions_module)
    import studio_api.main as main_module

    importlib.reload(main_module)

    return TestClient(main_module.app)


# --- 2.1 Banner --------------------------------------------------------------


def test_banner_html_round_trips_through_config(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    with _boot_studio(
        tmp_path,
        monkeypatch,
        WISDOM_STUDIO_BANNER_HTML="<strong>Demo</strong> mode",
    ) as client:
        body = client.get("/api/config").json()
        assert body["banner_html"] == "<strong>Demo</strong> mode"


def test_banner_html_strips_script_tag(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    with _boot_studio(
        tmp_path,
        monkeypatch,
        WISDOM_STUDIO_BANNER_HTML="hi <script>alert('x')</script> there",
    ) as client:
        body = client.get("/api/config").json()
        # bleach strips the executable tag — inner text is preserved as
        # harmless plain text. The security guarantee is that no script or
        # event handler reaches the DOM, not that the literal word "alert"
        # never appears in the banner.
        cleaned = body["banner_html"] or ""
        assert "<script" not in cleaned
        assert "</script" not in cleaned


def test_banner_html_strips_onerror_attr(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    with _boot_studio(
        tmp_path,
        monkeypatch,
        WISDOM_STUDIO_BANNER_HTML='<a href="x" onerror="boom()">click</a>',
    ) as client:
        body = client.get("/api/config").json()
        assert "onerror" not in (body["banner_html"] or "")


def test_banner_html_unset_returns_null(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    with _boot_studio(tmp_path, monkeypatch) as client:
        body = client.get("/api/config").json()
        assert body["banner_html"] is None


# --- 2.2 Session TTL ---------------------------------------------------------


def test_session_ttl_minutes_round_trips(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    with _boot_studio(
        tmp_path,
        monkeypatch,
        WISDOM_STUDIO_SESSION_TTL_MINUTES="30",
    ) as client:
        body = client.get("/api/config").json()
        assert body["session_ttl_minutes"] == 30


# --- 2.3 Seed ----------------------------------------------------------------


def test_seed_naive_datetime_raises() -> None:
    """Pydantic must reject seed memories with naive timestamps."""
    from studio_api.seeds import SeedMemory

    with pytest.raises(ValidationError):
        SeedMemory(
            kind="fact",
            content={"text": "naive"},
            created_at=datetime(2025, 1, 1),  # noqa: DTZ001 — intentional
        )


def test_seed_invalid_json_logs_and_continues(tmp_path: Path) -> None:
    from studio_api.seeds import load_seed

    bad = tmp_path / "bad.json"
    bad.write_text("{ not valid json")
    assert load_seed(bad) is None


def test_seed_missing_file_returns_none(tmp_path: Path) -> None:
    from studio_api.seeds import load_seed

    assert load_seed(tmp_path / "nope.json") is None


def test_seed_creates_agent_and_memories(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seed = {
        "agent_id": "guide",
        "name": "Guide",
        "archetype": "balanced",
        "persona": "patient and concise",
        "directives": ["cite sources", "ask before assuming"],
        "memories": [
            {
                "kind": "fact",
                "content": {"text": "Studio is the canonical SDK reference UI."},
                "created_at": datetime(2026, 4, 1, tzinfo=UTC).isoformat(),
            },
            {
                "kind": "fact",
                "content": {"text": "Built on wisdom-layer 1.1.0+."},
            },
        ],
        "llm_provider": "ollama",
    }
    seed_path = tmp_path / "guide.json"
    seed_path.write_text(json.dumps(seed))

    # Stub session boot so we don't need a live LLM. We still want to verify
    # the manifest is written and the seed apply loop reaches memory.capture.
    captured: list[tuple[str, dict]] = []

    class _FakeMemory:
        async def capture(self, kind: str, content: dict, **_kwargs: object) -> None:
            captured.append((kind, content))

    class _FakeAgent:
        def __init__(self, agent_id: str) -> None:
            self.agent_id = agent_id
            self.memory = _FakeMemory()

        async def initialize(self) -> None:
            return None

        def on(self, _name: str, _handler: object) -> object:
            return object()

        def off(self, _token: object) -> None:
            return None

        async def close(self) -> None:
            return None

    def _fake_build_agent(detail, **_kwargs):  # type: ignore[no-untyped-def]
        return _FakeAgent(detail.agent_id)

    monkeypatch.setenv("WISDOM_STUDIO_SEED_PATH", str(seed_path))
    monkeypatch.setenv("WISDOM_STUDIO_DATA_DIR", str(tmp_path / "data"))

    import studio_api.settings as settings_module

    importlib.reload(settings_module)
    import studio_api.store as store_module

    importlib.reload(store_module)
    import studio_api.seeds as seeds_module

    importlib.reload(seeds_module)
    import studio_api.sdk_mount as sdk_mount_module

    importlib.reload(sdk_mount_module)
    import studio_api.sessions as sessions_module

    importlib.reload(sessions_module)
    monkeypatch.setattr(sessions_module, "build_agent", _fake_build_agent)

    import studio_api.main as main_module

    importlib.reload(main_module)

    with TestClient(main_module.app):
        # Lifespan startup applies the seed.
        agents = store_module.list_agents()
        assert any(a.agent_id == "guide" for a in agents)
        assert len(captured) == 2
        assert captured[0][0] == "fact"


def test_seed_idempotent_when_agent_exists(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Re-running the seed against an existing agent_id must not error or duplicate."""
    seed = {
        "agent_id": "twin",
        "name": "Twin",
        "archetype": "balanced",
        "memories": [],
        "llm_provider": "ollama",
    }
    seed_path = tmp_path / "twin.json"
    seed_path.write_text(json.dumps(seed))

    monkeypatch.setenv("WISDOM_STUDIO_SEED_PATH", str(seed_path))
    monkeypatch.setenv("WISDOM_STUDIO_DATA_DIR", str(tmp_path / "data"))

    for module_name in (
        "studio_api.settings",
        "studio_api.store",
        "studio_api.seeds",
        "studio_api.sdk_mount",
        "studio_api.sessions",
        "studio_api.main",
    ):
        importlib.reload(importlib.import_module(module_name))

    import studio_api.main as main_module
    import studio_api.store as store_module

    # First boot creates the agent.
    with TestClient(main_module.app):
        first = [a.agent_id for a in store_module.list_agents()]
        assert "twin" in first

    # Second boot must observe the existing agent and skip without raising.
    importlib.reload(main_module)
    with TestClient(main_module.app):
        second = [a.agent_id for a in store_module.list_agents()]
        assert second == first


# --- 2.4 Lock provider -------------------------------------------------------


def test_locked_provider_parses_provider_and_model(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    with _boot_studio(
        tmp_path,
        monkeypatch,
        WISDOM_STUDIO_LOCK_PROVIDER="anthropic:claude-haiku-4-5",
    ) as client:
        body = client.get("/api/config").json()
        assert body["locked_llm"] == {"provider": "anthropic", "model": "claude-haiku-4-5"}


def test_locked_provider_only(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Bare provider (no model) is valid — model selection stays open."""
    with _boot_studio(
        tmp_path,
        monkeypatch,
        WISDOM_STUDIO_LOCK_PROVIDER="anthropic",
    ) as client:
        body = client.get("/api/config").json()
        assert body["locked_llm"] == {"provider": "anthropic", "model": None}


def test_locked_provider_invalid_silently_dropped(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Typoed provider names must not crash the boot — log and treat as unlocked."""
    with _boot_studio(
        tmp_path,
        monkeypatch,
        WISDOM_STUDIO_LOCK_PROVIDER="not-a-real-provider:foo",
    ) as client:
        body = client.get("/api/config").json()
        assert body["locked_llm"] is None


def test_locked_provider_overrides_request_body(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    with _boot_studio(
        tmp_path,
        monkeypatch,
        WISDOM_STUDIO_LOCK_PROVIDER="anthropic:claude-haiku-4-5",
    ) as client:
        response = client.post(
            "/api/agents",
            json={
                "name": "Sneaky",
                "archetype": "balanced",
                "llm_provider": "ollama",
                "llm_model": "llama3.1:8b",
            },
        )
        assert response.status_code == 201
        detail = response.json()
        assert detail["llm_provider"] == "anthropic"
        assert detail["llm_model"] == "claude-haiku-4-5"


def test_unlocked_default_unchanged(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    with _boot_studio(tmp_path, monkeypatch) as client:
        response = client.post(
            "/api/agents",
            json={
                "name": "Free",
                "archetype": "balanced",
                "llm_provider": "ollama",
                "llm_model": "llama3.1:8b",
            },
        )
        detail = response.json()
        assert detail["llm_provider"] == "ollama"
        assert detail["llm_model"] == "llama3.1:8b"


# --- 2.5 Hide settings -------------------------------------------------------


def test_hide_settings_returns_403_on_config_put(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    with _boot_studio(
        tmp_path,
        monkeypatch,
        WISDOM_STUDIO_HIDE_SETTINGS="true",
    ) as client:
        response = client.put(
            "/api/config",
            json={"provider_keys": {"anthropic": "sk-test"}},
        )
        assert response.status_code == 403
        body = client.get("/api/config").json()
        assert body["hide_settings"] is True


# --- 2.6 Hide agent CRUD -----------------------------------------------------


def test_hide_crud_disables_post_agents(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    with _boot_studio(
        tmp_path,
        monkeypatch,
        WISDOM_STUDIO_HIDE_AGENT_CRUD="true",
    ) as client:
        response = client.post(
            "/api/agents",
            json={"name": "Blocked", "archetype": "balanced", "llm_provider": "ollama"},
        )
        assert response.status_code == 403


def test_hide_crud_disables_delete_agent(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # Create an agent BEFORE enabling the hide-crud gate so we have something to delete.
    with _boot_studio(tmp_path, monkeypatch) as client:
        client.post(
            "/api/agents",
            json={"name": "Doomed", "archetype": "balanced", "llm_provider": "ollama"},
        )

    # Reboot with the gate enabled and verify deletion is blocked.
    with _boot_studio(
        tmp_path,
        monkeypatch,
        WISDOM_STUDIO_HIDE_AGENT_CRUD="true",
    ) as client:
        response = client.delete("/api/agents/doomed")
        assert response.status_code == 403


def test_hide_crud_disables_from_example(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    with _boot_studio(
        tmp_path,
        monkeypatch,
        WISDOM_STUDIO_HIDE_AGENT_CRUD="true",
    ) as client:
        response = client.post("/api/agents/from-example/researcher")
        assert response.status_code == 403


# --- 2.7 Docs URL ------------------------------------------------------------


def test_docs_url_exposed_in_config(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    with _boot_studio(
        tmp_path,
        monkeypatch,
        WISDOM_STUDIO_DOCS_URL="https://example.com/docs",
    ) as client:
        body = client.get("/api/config").json()
        assert body["docs_url"] == "https://example.com/docs"


def test_docs_url_unset_returns_null(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    with _boot_studio(tmp_path, monkeypatch) as client:
        body = client.get("/api/config").json()
        assert body["docs_url"] is None
