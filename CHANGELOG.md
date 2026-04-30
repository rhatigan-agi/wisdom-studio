# Changelog

All notable changes to Wisdom Studio are documented in this file.

The format is based on [Keep a Changelog 1.1.0](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.6.1] - 2026-04-30

### Fixed

- **Docker image build time and reliability**. The production image now
  installs the CPU-only PyTorch wheel from `download.pytorch.org/whl/cpu`
  before resolving the rest of the install graph, dropping torch from
  ~800MB to ~200MB on disk. No Studio deployment uses the CUDA runtime,
  and SDK runtime behavior is unchanged. Significantly reduces image
  size and shaves minutes off cold builds.
- **`release.yml`**: dropped `linux/arm64` from the GHCR publish. arm64
  was being built under QEMU emulation on x86 runners (3-5× slower) and
  pushing builds past 20 minutes with no native consumer of the arm64
  image. amd64-only for now; native arm64 can be added later via a
  matrix on `runs-on: ubuntu-24.04-arm`.
- **`ci.yml`**: collapsed `astral-sh/setup-uv` + `uv python install 3.12`
  into a single step using `setup-uv`'s built-in `python-version` input,
  removing one source of intermittent 502 failures from the
  `python-build-standalone` release CDN.

### Note

- v0.6.0 was tagged but its release workflow failed before publishing
  to GHCR (multi-arch QEMU build timed out, then a transient 502 from
  the standalone Python CDN failed CI). v0.6.1 is the first release
  that actually publishes a working image.

## [0.6.0] - 2026-04-30

### Added

- **Side-by-side compare mode toggle** above the chat input. One question
  produces three answers — baseline (no context), memory-only, full
  wisdom (memory + directives) — rendered stacked under `md` and as a
  three-column grid at `md`+. Backed by the SDK's `/api/chat` endpoint;
  the SDK's bundled `ChatComparison.tsx` is fixed three-column and not
  used here so the v0.5 mobile-responsive guarantee holds.
- **Suggested conversation starters** per agent. Optional list of up to
  five entries (≤80 chars each), edited from the New Agent form and
  rendered as clickable chips above an empty chat. Solves blank-page
  paralysis in conference, internal-team, and marketing-embed contexts.
  Wired through `AgentCreate` / `AgentDetail` schemas, the YAML examples
  loader, and the persisted manifest.
- **`GET /api/examples/{slug}`** returns the full `AgentCreate` payload
  (persona, directives, archetype, starters) so the New Agent wizard can
  prefill its draft form from a template instead of immediately creating
  the agent.
- **`src/components/kiosk/`** namespace for components only useful in
  locked/demo deployments. `Banner` and `SessionTimer` move into it.
  Forkers building a non-kiosk product can delete the folder and remove
  two imports from `Shell.tsx`; nothing else depends on it.
- **`FORKING.md`** at the repo root: what to keep, what to safely delete
  for a minimal fork.
- **`WISDOM_STUDIO_SIGNUP_URL`** env var (default
  `https://wisdomlayer.ai/signup/`). When set, FirstRun and Settings
  show a "Don't have a key? Sign up →" link next to the Wisdom Layer
  license-key input. Set to empty (`WISDOM_STUDIO_SIGNUP_URL=`) to hide
  it for forks that don't have a hosted signup flow.

### Changed

- **New Agent template-click behavior.** Clicking a template no longer
  immediately creates the agent — it loads the YAML payload into the
  draft form (one shared state) and scrolls to it. Only the explicit
  Create button commits. The form shows a "Prefilled from template X"
  indicator with a Reset button so the round-trip is legible.

## [0.5.0] - 2026-04-30

Initial public release. Apache-2.0.

### Added

- **Single-port production Docker image.** Multi-stage build at the repo root
  produces one container that serves the SPA and the API on port 3000. Image
  published to GHCR as `ghcr.io/rhatigan-agi/wisdom-studio:latest` for both
  `linux/amd64` and `linux/arm64` on every `v*.*.*` tag.
- **Seven generic deployment env vars** for shaping a fork without code
  changes:
  - `WISDOM_STUDIO_BANNER_HTML` — sticky-top notice. Sanitized server-side
    with bleach so untrusted operator input cannot inject script tags.
  - `WISDOM_STUDIO_SESSION_TTL_MINUTES` — visible countdown for kiosk
    deployments; dispatches a window event on expiry.
  - `WISDOM_STUDIO_SEED_PATH` — JSON seed file applied idempotently at boot.
  - `WISDOM_STUDIO_LOCK_PROVIDER` — pin LLM (e.g. `anthropic:claude-haiku-4-5`).
    Defended both in the wizard and on the API.
  - `WISDOM_STUDIO_HIDE_SETTINGS` — read-only deployments. PUT `/api/config`
    returns 403; the wizard is short-circuited.
  - `WISDOM_STUDIO_HIDE_AGENT_CRUD` — fixed-roster deployments. POST/DELETE
    `/api/agents` return 403; the SPA hides creation and deletion controls.
  - `WISDOM_STUDIO_DOCS_URL` — surfaces a custom docs link in the sidebar.
- **Three starter persona seeds** under `examples/seeds/`: a citation-disciplined
  researcher, an Acme-Co. consumer-support agent, and an opinionated coding
  assistant. Each carries 10 memories and 3 directives.
- **`TierRestrictionError` handler** mapping SDK 1.1.0 capacity / feature-gate
  errors to HTTP 402 (cap) and 403 (feature gate) with a structured body the
  SPA renders as an upgrade modal.
- **Mobile-responsive layout.** Sidebar collapses to a slide-in drawer; the
  agent's cognition / memory pane becomes a slide-up drawer behind a FAB;
  primary touch targets meet 44px.
- **Per-agent SDK route mounts** via FastAPI sub-apps under `/agents/{id}/api/...`,
  with route precedence preserved so the SPA fallback never shadows session
  routes.
- **Cognition stream** powered directly by the SDK's `WebSocketHub`.
- **CI**: `pnpm` build, `ruff` + `pytest` for the API, Docker image build, and a
  smoke job that boots the container and curls `/api/health`.
- **Backend test surface**: 40 tests across `test_api.py`,
  `test_static_serve.py`, `test_deployment_env.py`, and
  `test_tier_restriction.py`.

### Notes

- Built on `wisdom-layer>=1.1.0,<2.0.0`. The SDK ships under its own license
  — see <https://github.com/rhatigan-agi/wisdom-layer>.
- `STUDIO_STATIC_DIR` (production) is decoupled from `WISDOM_STUDIO_DATA_DIR`
  (per-user persistence) so a single image can serve many bind-mounted data
  directories without rebuilding.

[Unreleased]: https://github.com/rhatigan-agi/wisdom-studio/compare/v0.6.1...HEAD
[0.6.1]: https://github.com/rhatigan-agi/wisdom-studio/compare/v0.6.0...v0.6.1
[0.6.0]: https://github.com/rhatigan-agi/wisdom-studio/compare/v0.5.0...v0.6.0
[0.5.0]: https://github.com/rhatigan-agi/wisdom-studio/releases/tag/v0.5.0
