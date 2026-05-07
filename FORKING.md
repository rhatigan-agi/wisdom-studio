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

## Deploying behind auth

Studio ships single-user/local — no login screen, every request resolves to
`User(id="local")`. This is a deliberate scope decision: a reference UI
should not pick a winner among Clerk / Auth0 / NextAuth / OIDC providers.
There are two seams for forks that need real auth.

### Option A — trust an upstream auth proxy

The cheapest path. Put the app behind any reverse proxy that authenticates
the user and writes the result into a header, then point Studio at the
header:

```bash
WISDOM_STUDIO_TRUST_USER_HEADER=X-Authenticated-User
# Optional. Defaults to loopback (127.0.0.0/8 + ::1/128) — same-host proxy.
# Set this if your proxy lives on a different host.
WISDOM_STUDIO_TRUSTED_PROXY_CIDRS=10.0.0.0/8
```

The dependency in `studio_api/auth.py:get_current_user` reads that header
**only when the immediate peer is in the CIDR allowlist**. Untrusted peers
are refused with `503 auth_proxy_misconfigured` — fail-closed, so a
mis-deployed fork goes dark rather than open.

Three short recipes that work with this seam:

**Caddy basic-auth** (Caddyfile, 5 lines):

```caddyfile
studio.example.com {
    basic_auth {
        alice $2a$14$...   # bcrypt hash from `caddy hash-password`
    }
    header_up X-Authenticated-User {http.auth.user.id}
    reverse_proxy localhost:3000
}
```

**Cloudflare Access** (free tier, no Caddy needed): publish the app on a
hostname routed through your Cloudflare zone, attach an Access policy, and
forward `Cf-Access-Authenticated-User-Email` as the user id:

```bash
WISDOM_STUDIO_TRUST_USER_HEADER=Cf-Access-Authenticated-User-Email
WISDOM_STUDIO_TRUSTED_PROXY_CIDRS=173.245.48.0/20,103.21.244.0/22  # CF egress
```

(Cloudflare publishes their full IP ranges at <https://www.cloudflare.com/ips/>.
Pin the CIDR list so a request that bypasses the tunnel can't impersonate a CF edge.)

**Tailscale serve** (zero-config personal use): expose the app on your
tailnet only and let Tailscale identify the device. Tailscale serve does
not write a header by default — combine with `tailscale serve --bg` and a
small Caddy in front, or simply rely on tailnet ACLs and skip the header
entirely (`WISDOM_STUDIO_TRUST_USER_HEADER` unset, `User(id="local")`).

### Option B — override the dependency

For JWT, OAuth, session-cookie, or any flow you want to own end-to-end:

```python
# your_fork/app.py
from studio_api.auth import User, get_current_user
from studio_api.main import app

async def my_resolver(request) -> User:
    token = request.headers.get("Authorization", "").removeprefix("Bearer ")
    claims = verify_jwt(token)            # your code
    return User(id=claims["sub"])

app.dependency_overrides[get_current_user] = my_resolver
```

Studio doesn't ship a JWT verifier on purpose — that surface area belongs
in the fork, not in the reference UI.

### Where to wire `Depends(get_current_user)`

Studio's default routes don't enforce authorization on the user (the agent
id is the access boundary). If your fork wants per-user routing, add the
dependency to whichever endpoints care:

```python
from studio_api.auth import CurrentUser

@app.get("/api/agents", response_model=list[AgentSummary])
async def get_agents(user: CurrentUser) -> list[AgentSummary]:
    return list_agents_for(user.id)   # filter by your user→agent table
```

`GET /api/whoami` is included as a working consumer of the seam — hit it
to verify your auth wiring before threading the dependency into the rest
of the surface.

## Out of scope for this repo

- A SaaS hosted version of Studio.
- A plugin marketplace or extension API.
- Tools, integrations, or vertical UIs — those belong in your fork.
- Multi-tenant accounts and per-user data isolation — by design; the auth
  seam above gets you the *identity*; partitioning sessions, agents, and
  shared memory by `user.id` is your fork's job.
