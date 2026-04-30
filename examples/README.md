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
