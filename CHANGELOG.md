# Changelog

All notable changes to Wisdom Studio are documented in this file.

The format is based on [Keep a Changelog 1.1.0](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.9.2] - 2026-05-04

Two small UI fixes for the multi-agent demo flow.

### Fixed

- **`TypeError: Cannot read properties of undefined (reading 'toFixed')` on the
  Workspace tab.** `team_score` is omitted from the shared-memory row payload
  when a memory has not yet received any endorse / contest votes. The renderer
  now defaults to `0.00` rather than crashing the row
  (`apps/studio-web/src/pages/Workspace.tsx`).
- **Memory map overlay now refreshes after "Share to workspace".** The share
  operation creates a new memory on the originating agent's backend but does
  not emit a `memory.captured` cognition event, so the bottom-right
  `MemoryMapOverlay` stayed stale until the next page load. `useMemoryMap`
  now exposes a `refresh()` callback that re-probes the seed search; the
  share button on each `MemoryRow` invokes it on success
  (`apps/studio-web/src/components/useMemoryMap.ts`,
  `apps/studio-web/src/pages/AgentDetail.tsx`).

## [0.9.1] - 2026-05-03

Security and dependency maintenance. No user-facing behavior changes —
this release only updates build-time and CI tooling to clear two
moderate-severity advisories transitively pulled in by Vite 5 and
Vitest 2.

### Security

- **Vite 5 → 6.4.2** (clears [GHSA-4w7w-66w2-5vf9](https://github.com/advisories/GHSA-4w7w-66w2-5vf9) — path traversal in optimized-deps `.map` handling).
- **esbuild upgraded transitively to ≥ 0.25.0** (clears [GHSA-67mh-4wv8-2f99](https://github.com/advisories/GHSA-67mh-4wv8-2f99) — dev-server allowed any origin to issue requests and read responses).
- **Vitest 2 → 4** so the dev test runner pulls Vite 6 and esbuild ≥ 0.25 transitively. `pnpm audit` now reports zero vulnerabilities.

### Changed

- **Frontend dependencies** bumped via Dependabot's first sweep:
  - `eslint-plugin-react-hooks` 5 → 7.1.1, `eslint-plugin-react-refresh` 0.4 → 0.5.2
  - `jsdom` 25 → 29, `postcss` 8.5.12 → 8.5.13
- **CI / GitHub Actions** all bumped to current majors and SHA-pinned:
  - `actions/checkout` 4 → 6, `actions/setup-node` 4 → 6, `actions/upload-artifact` 4 → 7, `actions/download-artifact` 4 → 8
  - `pnpm/action-setup` 4 → 6
  - `docker/login-action` 3 → 4, `docker/metadata-action` 5 → 6, `docker/build-push-action` 5 → 7, `docker/setup-buildx-action` 3 → 4
  - `github/codeql-action` 3 → 4
- **Dependabot config** now groups minor/patch bumps into one PR per ecosystem per week (instead of one PR per dependency) and explicitly ignores non-LTS Node majors and Python upgrades — Python and major Node bumps require manual review (see #15).
- **CodeQL workflow** skips on Dependabot PRs to avoid a known incompatibility between the CodeQL action's diff-range analyzer and Dependabot's restricted token. CodeQL still runs on every push to `main` and on the weekly schedule, so coverage is unchanged.

### Notes

- `react-hooks/set-state-in-effect` (new in eslint-plugin-react-hooks 7) is temporarily disabled in `eslint.config.js` — 19 existing call sites flag it. Cleanup is tracked in #15.
- Four major-version bumps were deliberately deferred for a focused frontend modernization pass: TypeScript 6, React 19, lucide-react 1.x, and Python 3.14. See #15.

## [0.9.0] - 2026-05-03

Multi-agent workspace surface for Wisdom Layer 1.2.0, plus
procurement-grade security hardening. Studio is now ready for
enterprise evaluation against the multi-agent SDK.

### Added

- **Multi-agent workspace surface (wisdom-layer 1.2.0).** New top-level
  **Workspace** tab in the sidebar exposes the SDK's cross-agent
  primitives — shared memory pool, agent-to-agent messaging, and Team
  Dream synthesis — behind the SDK's Enterprise license gate. Without a
  qualifying license the page renders an upgrade affordance; agents
  themselves continue to function in single-agent mode.
  - **Shared Memory Pool tab.** Lists every memory contributed to the
    workspace pool with contributor agent, visibility, and per-memory
    endorse / contest controls. Each agent page now carries a
    "Share to workspace" button on every memory in the Memories pane;
    one click promotes the private memory into the shared pool with a
    `source_memory_id` back-pointer.
  - **Team Insights tab.** Run a Team Dream from the SPA: pick any
    agent in the workspace as the synthesizer, the SDK's
    `team_synthesize` reads the entire shared pool, and the resulting
    insight is written to the team-insights surface with full
    provenance. **Walk Provenance** modal opens per-insight and shows
    each contributing memory's source agent + opaque
    `source_memory_id` — the underlying private memory body is *never*
    returned, preserving the patent-defensible isolation boundary.
  - **Messages tab.** Agent-to-agent messaging surface backed by the
    SDK's `MessageBus`. Send direct messages or broadcast to all
    workspace agents, view per-agent inbox, open a thread modal to see
    the full reply chain, and mark messages read. Four message
    purposes (`question`, `information`, `coordination`, `handoff`)
    map to the SDK enum.
  - Backend routes added under `/api/workspace/*`:
    `GET /status`, `GET /agents`, `POST /agents/{id}/share`,
    `GET /shared`, `POST /shared/{id}/endorse`,
    `POST /shared/{id}/contest`, `GET /insights`,
    `POST /insights/team-dream`, `GET /insights/{id}/provenance`,
    `POST /messages`, `POST /messages/broadcast`,
    `POST /messages/{id}/reply`, `GET /agents/{id}/inbox`,
    `GET /threads/{id}`, `POST /messages/{id}/read`. All routes 403
    cleanly when no license is present (`TierRestrictionError` mapped
    to a structured body the SPA renders inline).
  - **Three multi-agent demo seeds** under `examples/`:
    `team_researcher.yaml`, `team_synthesizer.yaml`,
    `team_critic.yaml` — a runnable Researcher → Synthesizer → Critic
    team that exercises the full shared-pool / Team Dream / provenance
    flow in five clicks. Picker entries surface in the agent wizard's
    "Start from example" list.
  - 25 new backend tests across `test_workspace_status.py`,
    `test_workspace_pool.py`, `test_workspace_messages.py` exercise
    the license gate, share/endorse/contest flow, Team Dream payload
    shape, provenance walk, and message bus surface using
    `FakeWorkspace` / `FakeMessageBus` stand-ins.
- **`apps/studio-api`**: bumped `wisdom-layer` floor to
  `>=1.2.0,<2.0.0` (now on PyPI). The `[tool.uv.sources]` local-path
  pin used during pre-release development is removed.

- **OpenSSF Scorecard hardening.** Procurement-grade security baseline
  matching the upstream SDK:
  - `.github/workflows/scorecard.yml` — weekly + push-triggered Scorecard
    analysis, results published to the public Scorecard registry; badge
    rendered in the README.
  - `.github/workflows/codeql.yml` — Python + JavaScript static analysis
    on every push/PR/weekly schedule; results land in the repo's Code
    Scanning tab.
  - SHA-pinned every GitHub Action across `ci.yml`, `release.yml`,
    `scorecard.yml`, and `codeql.yml`. `permissions: read-all` set as the
    repo-level default; `release.yml` opts in to `packages: write` and
    `id-token: write` only on the publish job.
  - `.github/dependabot.yml` — weekly updates for GitHub Actions, Docker,
    pip (`apps/studio-api`), and npm (`apps/studio-web`).
  - `SECURITY.md` — supported versions, disclosure timeline, threat
    model, in/out-of-scope matrix, contacts (`security@wisdomlayer.ai`,
    `privacy@wisdomlayer.ai`, `governance@wisdomlayer.ai`,
    `compliance@wisdomlayer.ai`).
  - `osv-scanner.toml` — accepted-advisory list with written rationale
    (currently: vite + esbuild dev-only, not shipped in the runtime
    image).
  - `Dockerfile` digest-pins `python:3.12-slim`, `node:20-alpine`, and
    pulls `uv` from a digest-pinned `ghcr.io/astral-sh/uv` image instead
    of `pip install uv` (which Scorecard's Pinned-Dependencies check
    flags as unpinned).
  - README badges expanded to surface CI, CodeQL, OpenSSF Scorecard,
    Ruff, security-policy, Python/Node versions, and activity signals.
  - New "Security" section in README summarizes the hardening posture
    for forkers and points to `SECURITY.md`.

### Changed

- `apps/studio-api`: bumped `litellm` floor to `>=1.83.14` to clear
  GHSA-xqmj-j6mv-4862 (HIGH severity, CVSS 8.6). `uv.lock` regenerated.

## [0.8.0] - 2026-05-02

### Added

- **Insights tab on the agent page.** A third side-pane tab next to
  Cognition / Memories surfaces the four SDK-driven cognitive surfaces
  that previously required a separate `wisdom-layer-dashboard` process:
  - **Directives** — active rule list with status / usage counts, plus a
    pending-proposals queue with one-click approve / reject. Refreshes
    automatically when `directive.*` or `dream.cycle.completed` events
    arrive on the cognition WebSocket.
  - **Journals** — reverse-chronological dream-cycle journal entries with
    expand-to-read-full bodies and per-entry memory counts.
  - **Dreams** — schedule status (last run / next run), recent cycle
    history with reconsolidation / insight / proposal counts, plus token
    and USD totals when the SDK's cost ledger has populated them.
  - **Critic** — directive-entropy snapshot (healthy / elevated / high /
    critical) and an on-demand audit runner that surfaces consistency,
    drift, adherence, and self-correction scores plus any flagged
    findings.

  All four panels read directly from the per-agent SDK sub-app at
  `/agents/{id}/api/*` (already mounted by `studio_api/sdk_mount.py`) —
  no new backend routes. New TypeScript schema mirrors live in
  `apps/studio-web/src/types/sdk.ts` (hand-written from
  `wisdom_layer.types`); new API client methods in `lib/api.ts`. Visual
  conventions match the existing event-color palette: amber for
  directives, sky for journals, violet for dreams, rose for critic.

- **Cognition WebSocket auto-reconnect with bounded backoff.** Transient
  transport-level closes (network blips, backend restarts under deploy,
  cellular handoff) now trigger an automatic reconnect cycle —
  250ms / 500ms / 1s / 2s / 5s, capped at five attempts. Intentional
  closes (code `1000` from cleanup, `4xxx` application codes from the
  backend) are respected and don't retry. After the budget exhausts, the
  cognition pane surfaces a "Connection lost — Reconnect" banner so the
  visitor can restart the loop with one click. Useful for any deployment,
  not just the hosted demo: forkers on flaky home wifi or behind
  corporate proxies get the same recovery path.

### Fixed

- **Cognition WebSocket no longer drops on cold session boot.** The
  `/ws/cognition/{agent_id}` handler called `session_manager.get_or_create`
  *before* `websocket.accept()`. First-touch session boot can take several
  seconds (license validation + SQLite init + sentence-transformers cold
  load), and many browsers / proxies abandoned the WS upgrade with
  `connection rejected (400 Bad Request)` before accept fired. The handler
  now accepts the socket first, then runs `get_or_create`, surfacing any
  boot failure as a clean application close code (`4404` for unknown agent,
  `4500` for boot exceptions). Forkers no longer see the cognition pane and
  memory minimap render permanently dark on a fresh `make dev`.
- **Chat state no longer bleeds across agents.** Switching from agent A to
  agent B carried A's chat transcript into B's composer. Because the
  composer threads recent turns back to the SDK as grounding context,
  details from A's conversation could end up captured into B's *memory*
  store via the SDK's fact-extractor. (Memory itself is correctly isolated
  per-agent — separate SQLite files — the bleed was purely a frontend
  state issue.) `AgentDetail` now resets chat, draft, tier-error, and
  memory-search state whenever `agentId` changes.
- **Vite dev server no longer 404s on hard reload of `/agents/<id>`.** The
  `/agents` proxy block forwarded *every* `/agents/*` request to the
  backend, which only mounts per-agent SDK sub-apps lazily under
  `/agents/<id>/...` on first use. Hard-reloading the SPA's
  `/agents/coding-assistant` route therefore returned `{"detail":"Not
  Found"}` from FastAPI. The proxy now bypasses HTML navigations (Accept:
  text/html) to `/index.html` while still proxying SDK XHR / fetch calls
  (Accept: application/json) through to the backend.

## [0.7.3] - 2026-05-01

### Fixed

- **Production Docker image boots again.** v0.7.2's switch to a repo-root-relative
  seed-path resolver hardcoded `Path(__file__).resolve().parents[3]` for the
  anchor, which works on host (`apps/studio-api/studio_api/settings.py`, four
  levels deep) but raises `IndexError` in the production image where the package
  is flattened to `/app/studio_api/` (only two levels deep). The container
  failed with `IndexError: 3` during `studio_api.settings` import and never
  reached uvicorn.

  The anchor now walks up from `settings.py` looking for an `examples/` directory,
  which exists at the repo root in source AND at `/app/examples` in the Docker
  image. Both layouts resolve correctly without hardcoding either depth. Forks
  that restructure the tree get a safe fallback (the file's own parent directory)
  rather than an import-time crash.

  **v0.7.2 is broken at boot in the published Docker image (`ghcr.io/rhatigan-agi/wisdom-studio:0.7.2`)
  — upgrade directly to v0.7.3.** The host `make dev` flow was unaffected.

## [0.7.2] - 2026-05-01

### Added

- **Floating memory minimap (`MemoryMapOverlay`).** A bottom-right corner
  overlay (md+ only) renders the agent's captured memories as a 2D force
  graph independent of the side pane's Cognition / Memories tabs. Always
  present once the page loads — empty state shows "No memories yet" with a
  hint, then populates live as the cognition stream emits `memory.captured`
  events. Collapsible to a 40 px circle with a badge counter; collapse state
  persists in `localStorage` (`wisdom-studio:memory-map-collapsed`). Hidden
  on small screens so it doesn't obscure the chat input.
- **In-chat conversation history threading.** Chat turns now thread the most
  recent 12 user/agent messages back through the SDK's `respond_loop` as
  `session_context`, so follow-up questions ("can you elaborate on that?",
  "what about the second option?") resolve against the actual prior turn
  instead of being treated as a standalone prompt. The wire payload is
  capped to keep request size bounded; older turns continue to surface
  through the SDK's memory semantic search. New `prior_messages` field on
  `ChatRequest` (backend) and `ChatMessage[]` arg on `api.chat()` (frontend).
- **Markdown rendering in agent messages (`ChatMarkdown`).** Agent replies
  now render with `react-markdown` + `remark-gfm` so headings, lists, code
  blocks, tables, and links display correctly. User messages still render as
  plain text (whitespace-preserving) since markdown in user prompts is
  almost always unintentional formatting noise.
- **"What informed this answer" per-message disclosure.** Every agent
  message gets an "Informed by N memories · M directives" toggle. Expanding
  it shows the actual memory snippets and directive text the SDK grounded
  the response on — the same data the Compare-mode panel surfaces, but
  inline per-message, so visitors can audit the wisdom layer's contribution
  without flipping a global toggle.
- **Conversation-starter chips.** Empty chat state now renders the
  `conversation_starters` array from each seed JSON as one-click chips that
  populate the input box. (Click does **not** auto-send — it primes the
  draft so visitors can edit before submitting.) Three seed personas
  (`researcher`, `coding_assistant`, `support_agent`) ship with starter
  arrays out of the box.
- **Rewritten seed personas with biographical memories.** The three example
  seeds were rewritten identity-first: each persona now carries a coherent
  professional bio in `persona`, plus pre-seeded `event_type=biographical`
  memories captured at first boot so "what are you good at?" gives a
  grounded answer from turn one rather than a generic LLM response.
- **One-shot Dream-cycle onboarding hint.** After a visitor sends two
  messages, a dismissible tooltip anchors to the Dream button explaining
  what a dream cycle does. Persistent installs use `localStorage`;
  ephemeral demos use `sessionStorage` so each new visitor sees the hint
  exactly once.
- **`Makefile` developer entry point.** `make dev` runs backend + frontend
  together with auto-install on first run; sentinel rules re-sync only when
  lockfiles change. Other targets: `install`, `test{,-api,-web}`,
  `lint{,-api,-web}`, `typecheck`, `build`, `docker{,-run}`, `clean`. CI
  invokes the same shell commands so local and CI behavior match.

### Fixed

- **WebSocket cognition stream stays connected under React 18 StrictMode.**
  In dev, StrictMode runs effect → cleanup → effect on every mount. The
  first cleanup's `ws.close()` on a still-CONNECTING socket fired both
  `onerror` and `onclose` events, which raced the second mount's `onopen`
  and clobbered `wsState` back to `"closed"` — leaving the Cognition pane
  permanently dark and gating the memory-map seed probe (which waits for
  `wsState === "live"` before hitting the SDK memory route). The effect now
  guards every handler with a `closedByCleanup` flag and nullifies the
  handlers before close, so events fired by the close itself can't reach
  the stale closure. Production builds are unaffected (StrictMode double-
  invocation is dev-only).
- **Backend logs `studio.ws.session_boot_failed` on WS handshake errors.**
  The cognition WebSocket handler previously swallowed exceptions during
  session boot, leaving operators with a silent "WS closed" in the SPA and
  no server-side breadcrumb. Failures during `build_agent` /
  `dashboard.ws_hub` initialization now log with the exception message and
  close the socket with code 4500 and a truncated reason — making
  diagnostics tractable in production.
- **Conversation-starter chips no longer auto-send on click.** Click now
  populates the input box only; the visitor edits and submits explicitly.
  The previous behavior of auto-sending made the chips unusable as
  exploration prompts.
- **Seed path resolves correctly in both Docker and host dev.**
  `WISDOM_STUDIO_SEED_PATH` accepts a relative path and resolves it from
  the repo root (Docker `WORKDIR=/app`, host `_REPO_ROOT`). A single value
  in `.env` (`examples/seeds/researcher.json`) now works in both
  environments without a separate Docker override.
- **Backend test suite isolates from `.env` and shell environment.**
  v0.7.1's addition of `.env` loading to `settings.py` for `make dev`
  ergonomics inadvertently broke 10 tests that asserted "absent unless
  set" semantics for env knobs. Two-layer defense: a
  `STUDIO_DISABLE_DOTENV` env knob in `settings.py` short-circuits dotenv
  loading, and an autouse `_isolate_env` conftest fixture sets the knob
  AND strips every `WISDOM_STUDIO_*`, `WISDOM_LAYER_*`, and provider-key
  env var via `monkeypatch.delenv`. Both layers needed: clearing env alone
  fails (`.env` still loaded), disabling dotenv alone fails (real shell env
  still leaks).



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

[Unreleased]: https://github.com/rhatigan-agi/wisdom-studio/compare/v0.9.2...HEAD
[0.9.2]: https://github.com/rhatigan-agi/wisdom-studio/compare/v0.9.1...v0.9.2
[0.9.1]: https://github.com/rhatigan-agi/wisdom-studio/compare/v0.9.0...v0.9.1
[0.9.0]: https://github.com/rhatigan-agi/wisdom-studio/compare/v0.8.0...v0.9.0
[0.8.0]: https://github.com/rhatigan-agi/wisdom-studio/compare/v0.7.3...v0.8.0
[0.7.3]: https://github.com/rhatigan-agi/wisdom-studio/compare/v0.7.2...v0.7.3
[0.7.2]: https://github.com/rhatigan-agi/wisdom-studio/compare/v0.7.1...v0.7.2
[0.7.1]: https://github.com/rhatigan-agi/wisdom-studio/compare/v0.7.0...v0.7.1
[0.7.0]: https://github.com/rhatigan-agi/wisdom-studio/compare/v0.6.1...v0.7.0
[0.6.1]: https://github.com/rhatigan-agi/wisdom-studio/compare/v0.6.0...v0.6.1
[0.6.0]: https://github.com/rhatigan-agi/wisdom-studio/compare/v0.5.0...v0.6.0
[0.5.0]: https://github.com/rhatigan-agi/wisdom-studio/releases/tag/v0.5.0
