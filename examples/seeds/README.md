# Seed personas

JSON files in this directory are **seed specs** — boot-time bundles that
create a single agent (if missing) and prefill its memories. Studio reads
the file pointed at by `WISDOM_STUDIO_SEED_PATH` once on startup, idempotent.

This is different from `../*.yaml` (the *example* templates surfaced in the
"Start from a template" UI). Examples are agent specs without memories;
seeds carry their own memory payload and apply on boot.

## Use one of the included personas

```bash
# Local dev (uvicorn)
WISDOM_STUDIO_SEED_PATH=examples/seeds/researcher.json \
  uv run uvicorn studio_api.main:app

# Single-port image
docker run -e WISDOM_STUDIO_SEED_PATH=/app/examples/seeds/researcher.json \
  -e WISDOM_STUDIO_HIDE_AGENT_CRUD=true \
  -p 3000:3000 ghcr.io/rhatigan-agi/wisdom-studio:latest
```

The three included personas (`researcher.json`, `support_agent.json`,
`coding_assistant.json`) are intentionally generic — no real-product
references, no proprietary tone — so you can ship them as-is for a
demo, or fork the JSON and tailor the persona, directives, and memories
to your own product.

## Schema

Each seed file matches the `SeedSpec` Pydantic model in
`apps/studio-api/studio_api/seeds.py`. Required fields:

- `agent_id` — stable id used for the on-disk directory and SDK session.
  Re-applying a seed against an existing `agent_id` is a no-op.
- `name`, `archetype`, `llm_provider` — shape the agent.
- `persona` — identity-first system text. Treated as the agent's hard
  identity layer at compose time, so write it as instructions the agent
  inhabits ("You are X. You introduce yourself as X."), not as advice
  about how to behave.
- `directives[]` — short rules surfaced on the agent manifest. **Until the
  SDK exposes a seed-time directive installer, the bundled personas also
  duplicate each rule into `memories[]` as a `kind: "directive"` entry**
  so it actually reaches the runtime context. Drop both copies if your
  fork doesn't need rules-as-memories.
- `memories[]` — each entry has `kind` (`conversation`, `fact`, `directive`,
  or `session_record`), a JSON `content` object, and an optional
  timezone-aware `created_at`. Mix biographical facts ("typical session
  shape", "self-description rule") with the meta-rules — biographical
  memories shape responses to identity questions ("what are you good
  at?") that meta-rules alone don't anchor.
- `conversation_starters[]` — up to five short suggestions (≤80 chars
  each) rendered as clickable chips on the agent's empty chat. Optional.

## Pairing seeds with deployment knobs

Common kiosk-style combination:

```bash
WISDOM_STUDIO_SEED_PATH=examples/seeds/researcher.json
WISDOM_STUDIO_HIDE_AGENT_CRUD=true
WISDOM_STUDIO_HIDE_SETTINGS=true
WISDOM_STUDIO_LOCK_PROVIDER=anthropic:claude-haiku-4-5
WISDOM_STUDIO_SESSION_TTL_MINUTES=15
WISDOM_STUDIO_BANNER_HTML='<strong>Demo</strong> · resets every 15 minutes'
```

That gives you a single, locked agent with a visible session timer, no
agent-creation UI, no settings panel, and a banner that explains the reset
behavior — suitable for an unattended kiosk or a conference booth.
