# Forking Wisdom Studio

Wisdom Studio is a **reference application** — a forkable starting point for
products built on the [Wisdom Layer SDK](https://pypi.org/project/wisdom-layer/).
This guide is the short version of "what to keep, what to delete" so your
fork stays lean.

If your fork is going to be a kiosk, demo, conference booth, or marketing
embed, **keep almost everything as-is** and configure via env vars (see the
README).

If your fork is going to be a real product with accounts, persistence, and
multi-user data, **delete the kiosk surface** and treat the rest as
scaffolding.

## What to keep

Anything in this list is core to Studio working at all. Don't delete unless
you know what you're replacing.

| Path | Why |
|---|---|
| `apps/studio-api/studio_api/main.py` | FastAPI entry, route registration, SPA fallback |
| `apps/studio-api/studio_api/sessions.py` | Per-agent SDK sub-app mounts and lifecycle |
| `apps/studio-api/studio_api/sdk_factory.py` | Builds `WisdomAgent` instances per archetype |
| `apps/studio-api/studio_api/sdk_mount.py` | Mounts the SDK's per-agent routers |
| `apps/studio-api/studio_api/store.py` | File-based persistence for agents and config |
| `apps/studio-api/studio_api/schemas.py` | Pydantic schemas — keep in lockstep with `types/api.ts` |
| `apps/studio-web/src/pages/AgentDetail.tsx` | The chat surface; the demo's centerpiece |
| `apps/studio-web/src/components/Shell.tsx` | App shell, sidebar, layout |
| `Dockerfile`, `docker-compose.yml`, `.github/workflows/` | Deploy infra |

## What to safely delete for a minimal fork

These exist to make the *demo* good, not to make the *system* work. If
you're building a product, none of this is load-bearing.

| Path | When to delete | What to also remove |
|---|---|---|
| `apps/studio-web/src/components/kiosk/` | You're not running a kiosk or demo deployment. | The two `kiosk/Banner` and `kiosk/SessionTimer` imports in `Shell.tsx`. |
| `examples/*.yaml` | You're shipping a single fixed agent or your own templates. | Optionally drop the template picker in `pages/NewAgent.tsx`. |
| `apps/studio-api/studio_api/seeds.py` + `WISDOM_STUDIO_SEED_PATH` | You don't need pre-seeded memory snapshots. | Remove the seed call in `main.py`'s `lifespan`. |
| The "Compare mode" toggle in `AgentDetail.tsx` | The wisdom-vs-baseline contrast isn't part of your product UX. | Delete the toggle + the `CompareRow` / `CompareColumn` components. |
| The `Conversation starters` field in `pages/NewAgent.tsx` and the chips block in `AgentDetail.tsx` | You don't need blank-page affordances. | Remove `conversation_starters` from the schemas if you also drop the field server-side. |

## Branding and theme

Studio uses a zinc-on-emerald Tailwind theme. To rebrand without forking the
component tree:

1. Edit `apps/studio-web/tailwind.config.js` — the palette is centralized.
2. Update copy in `Shell.tsx` (sidebar header) and `index.html` (title).
3. Drop a custom `WISDOM_STUDIO_BANNER_HTML` for any deployment-specific
   notice; bleach sanitizes it server-side so it's safe to expose to operators.

CSS-variable theme tokens (so a fork can swap palettes without rebuilding
the SPA) are a known follow-up — for now, edit `tailwind.config.js` directly.

## License

Studio itself is Apache-2.0 (see `LICENSE`). The Wisdom Layer SDK ships
under its own license — see <https://github.com/rhatigan-agi/wisdom-layer>.
Forks inherit Studio's license; check the SDK's terms separately for your
deployment context.

## Out of scope for this repo

- A SaaS hosted version of Studio.
- A plugin marketplace or extension API.
- Tools, integrations, or vertical UIs — those belong in your fork.
- Multi-tenant accounts and per-user data isolation — by design; if you
  need them, fork and add your own auth/persistence layer.
