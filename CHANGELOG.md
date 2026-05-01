# Changelog

All notable changes to Wisdom Studio are documented in this file.

The format is based on [Keep a Changelog 1.1.0](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.7.1] - 2026-04-30

### Fixed

- **`WISDOM_STUDIO_EPHEMERAL=true` now isolates the SDK SQLite per process.**
  v0.7.0 documented that ephemeral mode "isolates" each visitor, but only the
  `studio.json` writes were actually blocked — the SDK databases under
  `data_dir/agents/` were still written to whatever path
  `WISDOM_STUDIO_DATA_DIR` resolved to. On orchestrators where an ephemeral
  container inherits a shared bind mount or RWX volume (Docker bind mounts,
  Kubernetes RWX PVCs), two visitors hitting the same path could see each
  other's agent state.

  When `ephemeral=true` and `WISDOM_STUDIO_DATA_DIR` is **not** set explicitly,
  Studio now rewrites `data_dir` to a per-process `tempfile.mkdtemp(prefix=
  "wisdom-studio-ephemeral-")`. An `atexit` handler removes the directory on
  graceful shutdown. Operators who deliberately set `WISDOM_STUDIO_DATA_DIR`
  (e.g. pointing at a per-machine volume already isolated at the orchestrator
  layer) are still respected — explicit configuration always wins.

  Forks running `EPHEMERAL=true` on Fly Machines, single-instance Cloud Run
  revisions, or any orchestrator that gives each container its own filesystem
  see no behavioral change. Forks on multi-tenant shared filesystems
  (Kubernetes ReadWriteMany, Docker bind mounts across replicas) get
  isolation by construction without code changes.

- **`SessionTimer` countdown now follows the backend's `expires_at`.** The
  visible countdown previously started a fresh `Date.now()` clock at mount
  time and decremented from `session_ttl_minutes * 60`. That diverged from
  the backend's authoritative TTL clock (anchored on first WebSocket connect
  and exposed via `GET /api/agents/{id}/session`) — a tab refresh restarted
  the visible timer at full duration even though the server still considered
  the session minutes-deep into its window.

  The component now reads `expires_at` from the polled `SessionState` in the
  Zustand store and recomputes remaining seconds each tick from
  `(expires_at - Date.now())`. Bouncing the WebSocket, refreshing the SPA,
  or remounting the page no longer resets the visible window — only the
  server timestamp matters. The `wisdom-studio:session-expired` window
  event still fires when the countdown hits zero so existing listeners
  (e.g. `AgentDetail` navigation reset) keep working.

  When chat returns 410 (`session_ended` / `token_cap_reached`), the
  structured body's `started_at` / `expires_at` / `tokens_used` fields are
  written into the store synchronously, so the SPA flips to the
  session-ended view without waiting for the next 5-second poll tick.

## [0.7.0] - 2026-04-30

### Added

- **`WISDOM_STUDIO_EPHEMERAL`** — single-visitor demo posture. Disables
  `studio.json` writes (visitor config never persists across container
  restarts), forces `hide_settings` and `hide_agent_crud` true (so the
  Settings page and agent create/delete affordances are suppressed), and
  combines with `WISDOM_STUDIO_SESSION_TTL_MINUTES` /
  `WISDOM_STUDIO_TOKEN_CAP_PER_SESSION` for bounded try-it-now boxes.
  Provider keys must come from env vars in this mode (FirstRun is hidden).
- **`WISDOM_STUDIO_TOKEN_CAP_PER_SESSION`** — hard cap on input + output
  tokens per session. Counted across every SDK-driven call (chat turns,
  dreams, critic, directive runs) via the SDK's cost aggregator. When the
  cap is reached the backend returns 410 with a structured body and the SPA
  renders a "session limit reached" view in place of the chat input.
  Defense-in-depth: the gate is enforced server-side so a scripted client
  that ignores the SPA banner can't keep burning tokens.
- **Backend-anchored session TTL.** The TTL clock now starts on first
  WebSocket connect (rather than client wall-clock), is exposed via
  `GET /api/agents/{agent_id}/session`, and gates the chat endpoint
  server-side. The visible countdown in `SessionTimer` continues to render
  client-side, but the server is now the source of truth — bouncing the WS
  can't reset a visitor's countdown, and a closed tab can't extend it.
- **`WISDOM_STUDIO_SESSION_END_CTA_HREF`** /
  **`WISDOM_STUDIO_SESSION_END_CTA_LABEL`** — optional CTA shown on the
  session-ended / cap-reached view. Forks point this at signup, marketing,
  or a calendar URL. Empty string suppresses the CTA entirely (same
  convention as `WISDOM_STUDIO_SIGNUP_URL`).
- **`SessionStateError`** in the frontend API client. Mirrors the backend's
  410-with-structured-body for `session_ended` / `token_cap_reached`. The
  SPA flips to the end-state view synchronously on `chat()` failure rather
  than waiting for the next 5-second poll tick.

### Changed

- **`WISDOM_STUDIO_SIGNUP_URL` default is now empty.** Previously defaulted
  to `https://wisdomlayer.ai/signup/`. The public source no longer ships a
  hardcoded commercial CTA — when the env var is unset, the FirstRun /
  Settings link is suppressed. Deployments that want the CTA (including the
  hosted Wisdom Layer demo) set the env var explicitly. Same applies to the
  README's "unlock higher caps" line, which now points at
  `WISDOM_LAYER_LICENSE` rather than a specific signup URL.

### Internal

- **`fly.toml.example`** — committed template for forks deploying to Fly.io.
  Mirrors the `.env` / `.env.example` split: `fly.toml` is gitignored for
  per-fork operational config; the example documents the shape (1 GB RAM,
  `min_machines_running=1`, `/api/health` healthcheck, non-secret env in
  `[env]`, secrets via `fly secrets set`).
- **`studio_api.cost`** — single touch point around the SDK cost subsystem.
  Today it wraps `BaseBackend.cost_summary_aggregate`; when SDK 1.1.1 ships
  a public `cost.recorded` event, the implementation can swap to an
  in-process subscription without touching any call sites in
  `SessionManager`.
- **README**: dropped the stale `linux/arm64` claim from the highlights bullet.
  v0.6.1 narrowed the GHCR publish to amd64-only; the README still advertised
  multi-arch.

### Fixed

- **Provider-key and license env vars are now actually honored.**
  `docker-compose.yml`, the Dockerfile, and `.env.example` have always
  advertised that `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `GEMINI_API_KEY`,
  `LITELLM_API_KEY`, and `WISDOM_LAYER_LICENSE` could be passed as bare env
  vars to skip the FirstRun wizard. The backend never read them — the keys
  were only consumable through the GUI. Cloud and Docker deploys (Fly,
  Railway, headless boxes) hit the wizard despite a fully-provisioned
  environment.

  Studio now reads these env vars at startup. Setting any provider key flips
  `GET /api/config` → `initialized=true` so the SPA bypasses the wizard, and
  `SessionManager._resolve_provider_key` falls back to env when no persisted
  value exists for the requested provider. Persisted keys (saved through the
  GUI) still win over env so a self-hoster can override an env default
  through the Settings page. Env-supplied secrets are never returned in
  `GET /api/config` and never written to `studio.json`.

  No code change is required for forks that were already setting these env
  vars — the behavior matches what the docs always promised.

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

[Unreleased]: https://github.com/rhatigan-agi/wisdom-studio/compare/v0.7.1...HEAD
[0.7.1]: https://github.com/rhatigan-agi/wisdom-studio/compare/v0.7.0...v0.7.1
[0.7.0]: https://github.com/rhatigan-agi/wisdom-studio/compare/v0.6.1...v0.7.0
[0.6.1]: https://github.com/rhatigan-agi/wisdom-studio/compare/v0.6.0...v0.6.1
[0.6.0]: https://github.com/rhatigan-agi/wisdom-studio/compare/v0.5.0...v0.6.0
[0.5.0]: https://github.com/rhatigan-agi/wisdom-studio/releases/tag/v0.5.0
