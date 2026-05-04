# Example agent configurations

These YAML files define ready-to-instantiate agents that map directly to the
SDK's archetype factories (`AdminDefaults.balanced()`, `.for_research()`,
`.for_coding_assistant()`, `.for_consumer_support()`,
`.for_strategic_advisors()`, `.for_lightweight_local()`).

The Studio frontend lets you pick one as a starting point in the agent wizard.
You can also POST one to `/api/agents` to create an agent programmatically:

```bash
curl -X POST http://localhost:8765/api/agents \
  -H 'content-type: application/json' \
  -d "$(yq -o=json examples/writer.yaml)"
```

## Files

| File | Archetype | Use case |
|---|---|---|
| `writer.yaml` | balanced | Long-form drafting in your voice |
| `researcher.yaml` | research | Literature review, synthesis, citation tracking |
| `coding_assistant.yaml` | coding_assistant | Code review, refactor suggestions, repo memory |
| `support_agent.yaml` | consumer_support | Customer support with policy and history grounding |
| `generic.yaml` | balanced | Blank slate; build your own from here |
| `team_researcher.yaml` | research | Multi-agent demo: surfaces findings into the shared pool |
| `team_synthesizer.yaml` | research | Multi-agent demo: runs Team Dream to synthesize across the pool |
| `team_critic.yaml` | research | Multi-agent demo: walks provenance, endorses or contests insights |

## Multi-agent demo (wisdom-layer 1.2.0+)

The three `team_*.yaml` files form a runnable demo of the workspace
features (shared memory pool, Team Dream, agent-to-agent messaging,
provenance walk). Requires an Enterprise license — without one, the
agents still work in single-agent mode but the Workspace tab will show
the upgrade gate.

1. Create all three from the agent wizard's "Start from example" picker.
2. Chat with `team_researcher` and `team_critic` so each captures a few
   memories, then click "Share to workspace" on the most useful ones.
3. Open the **Workspace** tab in the sidebar.
4. In the **Team Insights** tab, pick `team_synthesizer` as the
   synthesizer and run a Team Dream.
5. Click **Walk provenance** on the result — the modal shows each
   contributor's `source_memory_id` back-pointer without ever exposing
   the underlying private memory. That isolation is the patent-defensible
   moat.
