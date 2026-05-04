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


def test_seed_path_relative_resolves_from_repo_root(monkeypatch: pytest.MonkeyPatch) -> None:
    """A relative ``seed_path`` resolves against the repo root (= Docker WORKDIR /app).

    This is the contract that lets a forker write
    ``WISDOM_STUDIO_SEED_PATH=examples/seeds/researcher.json`` once and have
    it work both in ``make dev`` (cwd = apps/studio-api) and in the published
    container (WORKDIR /app). The previous behavior — pass straight through
    to pydantic ``Path`` — required either an absolute path (Docker-only) or
    knowing the dev-server cwd, both forker-hostile.
    """
    monkeypatch.setenv("WISDOM_STUDIO_SEED_PATH", "examples/seeds/researcher.json")

    import studio_api.settings as settings_module

    importlib.reload(settings_module)

    resolved = settings_module.settings.seed_path_resolved
    assert resolved is not None
    assert resolved.is_absolute()
    # Anchor is whatever directory contains an ``examples/`` sibling — the same
    # walk the production code does. Locks in: relative paths land under repo
    # root in source AND under /app in the Docker image.
    assert resolved == settings_module._REPO_ROOT / "examples" / "seeds" / "researcher.json"


def test_repo_root_anchor_works_when_package_is_flattened(tmp_path: Path) -> None:
    """The repo-root anchor must work in the Docker image where the package
    is flattened to ``/app/studio_api/`` (only two levels deep), not just on
    host where it lives at ``apps/studio-api/studio_api/`` (four levels deep).

    Regression test for v0.7.2 boot failure: ``parents[3]`` raised IndexError
    in the production container, breaking ``ghcr.io/...:0.7.2`` at import
    time. The anchor now walks up looking for an ``examples/`` directory
    instead of hardcoding a depth.
    """
    import studio_api.settings as settings_module

    # Simulate the Docker layout: a settings.py whose only repo marker is
    # an ``examples/`` directory two levels up (matching /app/studio_api/
    # + /app/examples/).
    fake_pkg = tmp_path / "studio_api"
    fake_pkg.mkdir()
    (tmp_path / "examples").mkdir()
    fake_settings = fake_pkg / "settings.py"
    fake_settings.write_text("# placeholder\n")

    # Re-run the anchor logic with __file__ pointed at the fake layout.
    monkeypatched_file = fake_settings.resolve()
    here = monkeypatched_file
    anchor: Path | None = None
    for candidate in here.parents:
        if (candidate / "examples").is_dir():
            anchor = candidate
            break

    assert anchor == tmp_path, "anchor must find the examples/ sibling, not blow up on parents[3]"
    # And the production code's anchor finder must agree on the real layout.
    assert (settings_module._REPO_ROOT / "examples").is_dir()


def test_seed_path_absolute_passes_through(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """An absolute ``seed_path`` is returned untouched — the operator's call wins."""
    explicit = tmp_path / "ops" / "custom-seed.json"
    monkeypatch.setenv("WISDOM_STUDIO_SEED_PATH", str(explicit))

    import studio_api.settings as settings_module

    importlib.reload(settings_module)

    assert settings_module.settings.seed_path_resolved == explicit


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


# --- 2.7a Provider credentials via env ---------------------------------------


def test_anthropic_env_key_marks_initialized(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`ANTHROPIC_API_KEY` set without a wizard run flips ``initialized=true``.

    This is what `docker-compose.yml` and the Dockerfile have always promised
    forkers: pass the bare provider key as an env var, skip the GUI setup.
    Before this, the env var was advertised but silently ignored — only the
    FirstRun wizard could initialize the deployment.
    """
    with _boot_studio(
        tmp_path,
        monkeypatch,
        ANTHROPIC_API_KEY="sk-ant-test",
    ) as client:
        body = client.get("/api/config").json()
        assert body["initialized"] is True


def test_env_keys_do_not_leak_into_config_response(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Env-supplied secrets must not appear in ``GET /api/config``.

    The response is consumed by the SPA and may be cached in browser memory.
    Persisted keys (entered through the wizard) live there by necessity, but
    env keys belong to the operator's deployment surface and have no business
    flowing to the client.
    """
    with _boot_studio(
        tmp_path,
        monkeypatch,
        ANTHROPIC_API_KEY="sk-ant-secret",
        OPENAI_API_KEY="sk-openai-secret",
        WISDOM_LAYER_LICENSE="wl_pro_secret",
    ) as client:
        body = client.get("/api/config").json()
        assert body["provider_keys"] == {}
        assert body["license_key"] is None


def test_env_keys_not_persisted_to_disk(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Booting with env keys must NOT write studio.json.

    The persistence file is reserved for user-set values from the wizard. An
    env-only deployment should leave it absent so future env rotations take
    effect without a stale persisted override.
    """
    with _boot_studio(
        tmp_path,
        monkeypatch,
        ANTHROPIC_API_KEY="sk-ant-test",
    ):
        config_path = tmp_path / "studio.json"
        assert not config_path.exists()


def test_persisted_provider_key_overrides_env(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A wizard-saved key wins over the env var for the same provider.

    Self-hosters can still override an env default through the GUI. The env
    serves as a deployment-level fallback, not an authoritative override.
    """
    # Pre-seed studio.json as if the wizard ran with a different anthropic key.
    config_path = tmp_path / "studio.json"
    config_path.write_text(
        json.dumps(
            {
                "license_key": None,
                "provider_keys": {"anthropic": "sk-from-wizard"},
                "initialized": True,
            }
        )
    )

    with _boot_studio(
        tmp_path,
        monkeypatch,
        ANTHROPIC_API_KEY="sk-from-env",
    ) as _client:
        # Resolve the provider key the way SessionManager does.
        import studio_api.sessions as sessions_module

        resolved = sessions_module.SessionManager._resolve_provider_key(
            {"anthropic": "sk-from-wizard"}, "anthropic"
        )
        assert resolved == "sk-from-wizard"


def test_env_provider_key_is_used_when_persisted_absent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """With no wizard run, ``_resolve_provider_key`` falls back to env."""
    with _boot_studio(
        tmp_path,
        monkeypatch,
        ANTHROPIC_API_KEY="sk-from-env",
    ):
        import studio_api.sessions as sessions_module

        resolved = sessions_module.SessionManager._resolve_provider_key({}, "anthropic")
        assert resolved == "sk-from-env"


def test_no_env_keys_keeps_uninitialized(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Sanity: absence of env keys leaves ``initialized=false`` (FirstRun shows)."""
    with _boot_studio(tmp_path, monkeypatch) as client:
        body = client.get("/api/config").json()
        assert body["initialized"] is False


def test_blank_env_key_treated_as_unset(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """``ANTHROPIC_API_KEY=`` (empty) must not flip ``initialized`` to true.

    Forkers commonly pass through the env var unconditionally
    (``-e ANTHROPIC_API_KEY=$ANTHROPIC_API_KEY``); when the host shell has it
    unset, Docker forwards an empty string. Treat that as absent so the
    wizard still appears.
    """
    with _boot_studio(
        tmp_path,
        monkeypatch,
        ANTHROPIC_API_KEY="",
    ) as client:
        body = client.get("/api/config").json()
        assert body["initialized"] is False


def test_wisdom_layer_license_env_passes_to_agent_build(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``WISDOM_LAYER_LICENSE`` env propagates to ``build_agent`` when no
    persisted license exists.

    Stubs ``build_agent`` to capture the license_key argument; we don't need a
    real LLM to verify the wiring. Persisted license (if any) wins, but here
    studio.json is absent so the env value is what the SDK should see.
    """
    monkeypatch.setenv("WISDOM_LAYER_LICENSE", "wl_pro_envtest")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")

    with _boot_studio(tmp_path, monkeypatch) as client:
        # Create an agent so a session can be opened against it.
        create = client.post(
            "/api/agents",
            json={
                "name": "Licensed",
                "archetype": "balanced",
                "llm_provider": "anthropic",
            },
        )
        assert create.status_code == 201, create.text
        agent_id = create.json()["agent_id"]

    captured: dict[str, object] = {}

    class _FakeAgent:
        def __init__(self, agent_id: str) -> None:
            self.agent_id = agent_id

        async def initialize(self) -> None:
            return None

        def on(self, _name: str, _handler: object) -> object:
            return object()

        def off(self, _token: object) -> None:
            return None

        async def close(self) -> None:
            return None

    def _fake_build_agent(detail, *, provider_api_key, license_key):  # type: ignore[no-untyped-def]
        captured["provider_api_key"] = provider_api_key
        captured["license_key"] = license_key
        return _FakeAgent(detail.agent_id)

    import studio_api.sessions as sessions_module

    monkeypatch.setattr(sessions_module, "build_agent", _fake_build_agent)

    import asyncio

    async def _open_session() -> None:
        await sessions_module.session_manager.get_or_create(agent_id)

    # The session_manager singleton needs the parent app attached. Reuse the
    # most recent main module import from `_boot_studio`.
    import studio_api.main as main_module

    sessions_module.session_manager.attach(main_module.app)
    asyncio.run(_open_session())

    assert captured["provider_api_key"] == "sk-ant-test"
    assert captured["license_key"] == "wl_pro_envtest"


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


# --- 2.8 Ephemeral mode (v0.7) -----------------------------------------------


def test_ephemeral_mode_exposed_in_config(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    with _boot_studio(
        tmp_path,
        monkeypatch,
        WISDOM_STUDIO_EPHEMERAL="true",
    ) as client:
        body = client.get("/api/config").json()
        assert body["ephemeral"] is True


def test_ephemeral_mode_implies_hide_settings_and_crud(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Ephemeral deployments suppress Settings + Agent CRUD even without the explicit flags.

    A try-it-now demo box can't accept persistent visitor config (Settings)
    and visitors should never delete the seeded agent (CRUD). The forced
    overlay covers the case where an operator only sets ``EPHEMERAL=true``.
    """
    with _boot_studio(
        tmp_path,
        monkeypatch,
        WISDOM_STUDIO_EPHEMERAL="true",
    ) as client:
        body = client.get("/api/config").json()
        assert body["hide_settings"] is True
        assert body["hide_agent_crud"] is True


def test_ephemeral_mode_blocks_studio_json_writes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``save_studio_config`` must no-op under ephemeral mode.

    Defense-in-depth: PUT /api/config already returns 403 when ``hide_settings``
    is true (which ephemeral implies), but if any internal call path tries to
    persist config the file should still not appear on disk.
    """
    with _boot_studio(
        tmp_path,
        monkeypatch,
        WISDOM_STUDIO_EPHEMERAL="true",
    ):
        from studio_api.schemas import StudioConfig
        from studio_api.store import save_studio_config

        save_studio_config(StudioConfig(license_key="leak", initialized=True))
        assert not (tmp_path / "studio.json").exists()


def test_ephemeral_default_off(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    with _boot_studio(tmp_path, monkeypatch) as client:
        body = client.get("/api/config").json()
        assert body["ephemeral"] is False


def test_ephemeral_swaps_data_dir_to_tmp_when_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    """With ``WISDOM_STUDIO_DATA_DIR`` unset, ephemeral mode must override.

    The override isolates the SDK SQLite to a per-process tmp dir so a
    forker who accidentally mounts a shared volume across containers can't
    leak agent state between visitors.
    """
    monkeypatch.delenv("WISDOM_STUDIO_DATA_DIR", raising=False)
    monkeypatch.setenv("WISDOM_STUDIO_EPHEMERAL", "true")

    import studio_api.settings as settings_module

    importlib.reload(settings_module)

    resolved = settings_module.settings.data_dir
    assert resolved.name.startswith("wisdom-studio-ephemeral-")
    assert resolved.exists()
    assert resolved.is_absolute()


def test_ephemeral_respects_explicit_data_dir(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An operator-supplied ``WISDOM_STUDIO_DATA_DIR`` is always honored.

    Forkers who deliberately point ephemeral mode at a known path (perhaps
    a per-machine volume already isolated at the orchestrator layer) must
    not have their choice silently overridden by the tmp-dir swap.
    """
    explicit = tmp_path / "operator-chosen"
    monkeypatch.setenv("WISDOM_STUDIO_DATA_DIR", str(explicit))
    monkeypatch.setenv("WISDOM_STUDIO_EPHEMERAL", "true")

    import studio_api.settings as settings_module

    importlib.reload(settings_module)

    assert settings_module.settings.data_dir == explicit
    assert "wisdom-studio-ephemeral-" not in str(settings_module.settings.data_dir)


def test_non_ephemeral_never_swaps_data_dir(monkeypatch: pytest.MonkeyPatch) -> None:
    """Without ephemeral, the default data dir is preserved as-is."""
    monkeypatch.delenv("WISDOM_STUDIO_DATA_DIR", raising=False)
    monkeypatch.delenv("WISDOM_STUDIO_EPHEMERAL", raising=False)

    import studio_api.settings as settings_module

    importlib.reload(settings_module)

    assert settings_module.settings.data_dir == Path(".wisdom-studio")


# --- 2.9 Token cap per session (v0.7) ----------------------------------------


def test_token_cap_per_session_exposed_in_config(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    with _boot_studio(
        tmp_path,
        monkeypatch,
        WISDOM_STUDIO_TOKEN_CAP_PER_SESSION="50000",
    ) as client:
        body = client.get("/api/config").json()
        assert body["token_cap_per_session"] == 50000


def test_token_cap_unset_returns_null(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    with _boot_studio(tmp_path, monkeypatch) as client:
        body = client.get("/api/config").json()
        assert body["token_cap_per_session"] is None


# --- 2.10 Session-end CTA (v0.7) ---------------------------------------------


def test_session_end_cta_round_trips(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    with _boot_studio(
        tmp_path,
        monkeypatch,
        WISDOM_STUDIO_SESSION_END_CTA_HREF="https://example.com/signup",
        WISDOM_STUDIO_SESSION_END_CTA_LABEL="Get your own",
    ) as client:
        body = client.get("/api/config").json()
        assert body["session_end_cta_href"] == "https://example.com/signup"
        assert body["session_end_cta_label"] == "Get your own"


def test_session_end_cta_empty_string_is_none(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``WISDOM_STUDIO_SESSION_END_CTA_HREF=`` (empty) must read as null.

    Same convention as ``WISDOM_STUDIO_SIGNUP_URL`` — explicit opt-out without
    needing to unset the env var, so forks that always pass the var through
    can disable the CTA by setting it blank.
    """
    with _boot_studio(
        tmp_path,
        monkeypatch,
        WISDOM_STUDIO_SESSION_END_CTA_HREF="",
        WISDOM_STUDIO_SESSION_END_CTA_LABEL="",
    ) as client:
        body = client.get("/api/config").json()
        assert body["session_end_cta_href"] is None
        assert body["session_end_cta_label"] is None


# --- 2.11 Session lifecycle (TTL + cap enforcement, v0.7) --------------------


def test_session_state_inactive_when_ttl_expired(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``refresh_state`` flips to ``session_ended`` once ``expires_at`` passes."""
    from datetime import UTC, datetime, timedelta

    with _boot_studio(
        tmp_path,
        monkeypatch,
        WISDOM_STUDIO_SESSION_TTL_MINUTES="30",
    ):
        from studio_api.sessions import AgentSession

        # Build a minimally-faked session — refresh_state only reads
        # `started_at` / `expires_at` and (for the cap branch) the SDK agent.
        session = AgentSession.__new__(AgentSession)
        session.detail = type("_D", (), {"agent_id": "x"})()
        session.agent = None  # not touched when TTL is the gate
        session.tokens_used = 0
        session.state = "active"
        session.started_at = datetime.now(UTC) - timedelta(minutes=31)
        session.expires_at = datetime.now(UTC) - timedelta(minutes=1)
        import asyncio

        result = asyncio.run(session.refresh_state())
        assert result.state == "session_ended"


def test_session_state_inactive_when_token_cap_reached(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """When the SDK's cost aggregate >= cap, state flips to ``token_cap_reached``."""
    from datetime import UTC, datetime

    with _boot_studio(
        tmp_path,
        monkeypatch,
        WISDOM_STUDIO_TOKEN_CAP_PER_SESSION="100",
    ):
        from studio_api.sessions import AgentSession

        session = AgentSession.__new__(AgentSession)
        session.detail = type("_D", (), {"agent_id": "x"})()

        class _FakeBackend:
            async def cost_summary_aggregate(
                self, *, agent_id: str, since: str | None, until: str | None
            ) -> dict[str, object]:
                return {"total_input_tokens": 75, "total_output_tokens": 50}

        class _FakeAgent:
            agent_id = "x"
            _backend = _FakeBackend()

        session.agent = _FakeAgent()
        session.tokens_used = 0
        session.state = "active"
        session.started_at = datetime.now(UTC)
        session.expires_at = None

        import asyncio

        result = asyncio.run(session.refresh_state())
        assert result.state == "token_cap_reached"
        assert result.tokens_used == 125


def test_session_state_endpoint_returns_active_by_default(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """GET /api/agents/{id}/session is reachable even without TTL / cap configured.

    Returns ``active`` because no clock or cap is configured. The SPA only
    polls when one of them is set, but the endpoint must still answer
    cleanly.
    """
    with _boot_studio(tmp_path, monkeypatch) as client:
        client.post(
            "/api/agents",
            json={"name": "Probe", "archetype": "balanced", "llm_provider": "ollama"},
        )

    captured: dict[str, object] = {}

    class _FakeAgent:
        def __init__(self, agent_id: str) -> None:
            self.agent_id = agent_id

        async def initialize(self) -> None:
            return None

        def on(self, _name: str, _handler: object) -> object:
            return object()

        def off(self, _token: object) -> None:
            return None

        async def close(self) -> None:
            return None

    def _fake_build_agent(detail, *, provider_api_key, license_key):  # type: ignore[no-untyped-def]
        captured["called"] = True
        return _FakeAgent(detail.agent_id)

    with _boot_studio(tmp_path, monkeypatch) as client:
        import studio_api.sessions as sessions_module

        monkeypatch.setattr(sessions_module, "build_agent", _fake_build_agent)
        response = client.get("/api/agents/probe/session")
        assert response.status_code == 200
        assert response.json()["state"] == "active"


def test_chat_returns_410_when_token_cap_reached(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Defense-in-depth: chat endpoint refuses to bill the LLM once the cap trips.

    The SPA's SessionEndedView renders the same structured body, so a
    scripted client that ignores the SPA banner still gets a clean 410 with
    ``error: token_cap_reached`` rather than burning more tokens.
    """
    with _boot_studio(
        tmp_path,
        monkeypatch,
        WISDOM_STUDIO_TOKEN_CAP_PER_SESSION="100",
        ANTHROPIC_API_KEY="sk-test",
    ) as client:
        client.post(
            "/api/agents",
            json={"name": "Probe", "archetype": "balanced", "llm_provider": "anthropic"},
        )

    class _FakeBackend:
        async def cost_summary_aggregate(
            self, *, agent_id: str, since: str | None, until: str | None
        ) -> dict[str, object]:
            return {"total_input_tokens": 200, "total_output_tokens": 0}

    class _FakeAgent:
        def __init__(self, agent_id: str) -> None:
            self.agent_id = agent_id
            self._backend = _FakeBackend()

        async def initialize(self) -> None:
            return None

        def on(self, _name: str, _handler: object) -> object:
            return object()

        def off(self, _token: object) -> None:
            return None

        async def close(self) -> None:
            return None

    def _fake_build_agent(detail, *, provider_api_key, license_key):  # type: ignore[no-untyped-def]
        return _FakeAgent(detail.agent_id)

    with _boot_studio(
        tmp_path,
        monkeypatch,
        WISDOM_STUDIO_TOKEN_CAP_PER_SESSION="100",
        ANTHROPIC_API_KEY="sk-test",
    ) as client:
        import studio_api.sessions as sessions_module

        monkeypatch.setattr(sessions_module, "build_agent", _fake_build_agent)

        # Anchor the session clock so refresh_state queries the cost backend.
        # In production the WS connect handler does this; in the test we call
        # it directly so the chat endpoint sees a started session.
        import asyncio

        session = asyncio.run(sessions_module.session_manager.get_or_create("probe"))
        asyncio.run(session.mark_started())

        response = client.post("/api/agents/probe/chat", json={"message": "hi", "capture": False})
        assert response.status_code == 410
        body = response.json()
        assert body["error"] == "token_cap_reached"
        assert body["agent_id"] == "probe"
        assert body["tokens_used"] == 200
        assert body["token_cap"] == 100


def test_chat_returns_410_when_ttl_expired(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Same defense-in-depth gate, TTL branch."""
    from datetime import UTC, datetime, timedelta

    with _boot_studio(
        tmp_path,
        monkeypatch,
        WISDOM_STUDIO_SESSION_TTL_MINUTES="5",
        ANTHROPIC_API_KEY="sk-test",
    ) as client:
        client.post(
            "/api/agents",
            json={"name": "Probe", "archetype": "balanced", "llm_provider": "anthropic"},
        )

    class _FakeAgent:
        def __init__(self, agent_id: str) -> None:
            self.agent_id = agent_id

        async def initialize(self) -> None:
            return None

        def on(self, _name: str, _handler: object) -> object:
            return object()

        def off(self, _token: object) -> None:
            return None

        async def close(self) -> None:
            return None

    def _fake_build_agent(detail, *, provider_api_key, license_key):  # type: ignore[no-untyped-def]
        return _FakeAgent(detail.agent_id)

    with _boot_studio(
        tmp_path,
        monkeypatch,
        WISDOM_STUDIO_SESSION_TTL_MINUTES="5",
        ANTHROPIC_API_KEY="sk-test",
    ) as client:
        import studio_api.sessions as sessions_module

        monkeypatch.setattr(sessions_module, "build_agent", _fake_build_agent)

        import asyncio

        session = asyncio.run(sessions_module.session_manager.get_or_create("probe"))
        # Force the session into an expired window — equivalent to a visitor
        # idling past the TTL.
        session.started_at = datetime.now(UTC) - timedelta(minutes=10)
        session.expires_at = datetime.now(UTC) - timedelta(minutes=5)

        response = client.post("/api/agents/probe/chat", json={"message": "hi", "capture": False})
        assert response.status_code == 410
        body = response.json()
        assert body["error"] == "session_ended"
