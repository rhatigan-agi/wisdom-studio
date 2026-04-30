"""Reference agent configs shipped with Studio.

YAML files in ``examples/`` (at the repo root, configurable via
``WISDOM_STUDIO_EXAMPLES_DIR``) define ready-to-instantiate agents. Studio
exposes them as templates the wizard can preload.

These are *reference scaffolding*, not products — fork them, change them,
delete them. Studio never reads back from this directory at runtime once
an agent has been created.
"""

from __future__ import annotations

import logging
from pathlib import Path

import yaml
from pydantic import ValidationError

from studio_api.schemas import AgentCreate, ExampleSummary
from studio_api.settings import settings

logger = logging.getLogger(__name__)


def _examples_dir() -> Path:
    return settings.examples_dir


def list_examples() -> list[ExampleSummary]:
    """Discover YAML examples on disk and return summaries."""
    base = _examples_dir()
    if not base.exists():
        logger.warning("studio.examples.dir_missing", extra={"dir": str(base)})
        return []

    summaries: list[ExampleSummary] = []
    for path in sorted(base.glob("*.yaml")):
        try:
            spec = load_example(path.stem)
        except (FileNotFoundError, ValueError, ValidationError) as exc:
            logger.warning(
                "studio.examples.load_failed",
                extra={"slug": path.stem, "error": str(exc)},
            )
            continue
        summaries.append(
            ExampleSummary(
                slug=path.stem,
                name=spec.name,
                role=spec.role or "",
                archetype=spec.archetype,
                persona_preview=_first_line(spec.persona),
                directive_count=len(spec.directives),
            ),
        )
    return summaries


def load_example(slug: str) -> AgentCreate:
    """Load a single example by slug (filename without .yaml)."""
    path = _examples_dir() / f"{slug}.yaml"
    if not path.exists():
        raise FileNotFoundError(f"example not found: {slug}")
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise ValueError(f"invalid YAML in {path.name}: {exc}") from exc
    if not isinstance(raw, dict):
        raise ValueError(f"example {slug} must be a mapping at the top level")
    raw.pop("llm_tier", None)  # tier→model mapping is an SDK concern; Studio uses model directly
    return AgentCreate.model_validate(raw)


def _first_line(text: str) -> str:
    stripped = (text or "").strip()
    if not stripped:
        return ""
    first = stripped.splitlines()[0]
    return first if len(first) <= 120 else f"{first[:117]}…"


__all__ = ["list_examples", "load_example"]
