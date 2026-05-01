"""Test fixtures for the Studio API.

Each test gets an isolated `WISDOM_STUDIO_DATA_DIR` so persistence tests do not
clobber a developer's local agents directory.

The `_isolate_env` autouse fixture below strips every variable that the
production settings module reads from the environment (or from a developer's
repo-root `.env`). Without it, a developer running tests from a checkout that
also hosts a `make dev` config — Anthropic key, license, banner, ephemeral
mode, etc. — would see those values leak into the reloaded settings module
and break tests that assert "absent by default" semantics. Tests that need
specific values still set them via `monkeypatch.setenv`.
"""

from __future__ import annotations

import importlib
import os
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

# Env vars the Studio settings module reads. Anything matching these prefixes
# or names is wiped before each test; the dotenv loader is also disabled via
# `STUDIO_DISABLE_DOTENV` so the repo-root `.env` cannot reintroduce them.
_LEAKY_PREFIXES: tuple[str, ...] = ("WISDOM_STUDIO_", "WISDOM_LAYER_")
_LEAKY_KEYS: tuple[str, ...] = (
    "ANTHROPIC_API_KEY",
    "OPENAI_API_KEY",
    "GEMINI_API_KEY",
    "LITELLM_API_KEY",
)


@pytest.fixture(autouse=True)
def _isolate_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("STUDIO_DISABLE_DOTENV", "1")
    for key in list(os.environ):
        if key.startswith(_LEAKY_PREFIXES) or key in _LEAKY_KEYS:
            monkeypatch.delenv(key, raising=False)


@pytest.fixture
def studio_app(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    monkeypatch.setenv("WISDOM_STUDIO_DATA_DIR", str(tmp_path))

    # Reload modules so they pick up the new data_dir setting.
    import studio_api.settings as settings_module

    importlib.reload(settings_module)
    import studio_api.store as store_module

    importlib.reload(store_module)
    import studio_api.sessions as sessions_module

    importlib.reload(sessions_module)
    import studio_api.main as main_module

    importlib.reload(main_module)

    with TestClient(main_module.app) as client:
        yield client
