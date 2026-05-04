import { useCallback, useEffect, useMemo, useState } from "react";
import { api } from "../lib/api";
import type { CognitionEvent, MemoryEntry } from "../types/api";
import type { MemoryNode } from "./MemoryMap";

const SEED_PROBE_QUERY = "memory";
const SEED_PROBE_LIMIT = 100;
const SNIPPET_MAX = 140;

function readSnippet(content: unknown): string {
  if (typeof content === "string") return content;
  if (content && typeof content === "object") {
    const c = content as Record<string, unknown>;
    if (typeof c.text === "string") {
      if (typeof c.role === "string") return `${c.role}: ${c.text}`;
      return c.text;
    }
    return Object.entries(c)
      .map(([k, v]) => `${k}=${typeof v === "string" ? v : JSON.stringify(v)}`)
      .join(" ");
  }
  return "";
}

function truncate(text: string): string {
  const trimmed = text.trim();
  if (trimmed.length <= SNIPPET_MAX) return trimmed;
  return `${trimmed.slice(0, SNIPPET_MAX - 1).trimEnd()}…`;
}

function entryToNode(entry: MemoryEntry, source: "seed" | "live"): MemoryNode | null {
  const id = typeof entry.id === "string" ? entry.id : null;
  if (!id) return null;
  const kind = typeof entry.event_type === "string" ? entry.event_type : "memory";
  const created = typeof entry.created_at === "string" ? entry.created_at : null;
  const snippet = truncate(readSnippet(entry.content));
  return { id, kind, snippet, createdAt: created, source };
}

// Pull memory captures off the cognition WebSocket stream. The SDK emits
// `memory.captured` (and a few siblings) carrying the new memory's id +
// content. Bad payloads are skipped silently.
function liveNodesFrom(events: CognitionEvent[]): MemoryNode[] {
  const out: MemoryNode[] = [];
  for (const event of events) {
    if (!event.type.startsWith("memory.")) continue;
    const data = event.data ?? {};
    const id =
      typeof data.memory_id === "string"
        ? data.memory_id
        : typeof data.id === "string"
          ? data.id
          : null;
    if (!id) continue;
    const kind =
      typeof data.event_type === "string"
        ? data.event_type
        : typeof data.kind === "string"
          ? data.kind
          : event.type.replace(/^memory\./, "");
    const snippet = truncate(readSnippet(data.content));
    out.push({ id, kind, snippet, createdAt: event.timestamp, source: "live" });
  }
  return out;
}

function dedupe(nodes: MemoryNode[]): MemoryNode[] {
  const seen = new Map<string, MemoryNode>();
  for (const node of nodes) {
    seen.set(node.id, node);
  }
  return Array.from(seen.values());
}

export interface MemoryMap {
  nodes: MemoryNode[];
  refresh: () => Promise<void>;
}

export function useMemoryMap(
  agentId: string,
  cognition: CognitionEvent[],
  ready: boolean,
): MemoryMap {
  const [seeds, setSeeds] = useState<MemoryNode[]>([]);

  const refresh = useCallback(async (): Promise<void> => {
    if (!agentId || !ready) return;
    try {
      const result = await api.searchMemories(agentId, {
        query: SEED_PROBE_QUERY,
        limit: SEED_PROBE_LIMIT,
      });
      const nodes = result
        .map((entry) => entryToNode(entry, "seed"))
        .filter((n): n is MemoryNode => n !== null);
      setSeeds(nodes);
    } catch {
      // Search can fail on tier-gated deployments or transient backend
      // issues. We swallow it — the parent hides the tab when the node
      // list is empty, so there's no visitor-visible failure.
    }
  }, [agentId, ready]);

  useEffect(() => {
    // The SDK dashboard sub-app at /agents/{id}/api/* is mounted lazily by
    // SessionManager on the first WS / chat / session request. Probing
    // before the session exists 404s, so we wait until the cognition WS
    // confirms the session is live.
    if (!agentId || !ready) return;
    let cancelled = false;
    (async () => {
      try {
        const result = await api.searchMemories(agentId, {
          query: SEED_PROBE_QUERY,
          limit: SEED_PROBE_LIMIT,
        });
        if (cancelled) return;
        const nodes = result
          .map((entry) => entryToNode(entry, "seed"))
          .filter((n): n is MemoryNode => n !== null);
        setSeeds(nodes);
      } catch {
        // See refresh() — same swallow rationale.
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [agentId, ready]);

  const nodes = useMemo(
    () => dedupe([...seeds, ...liveNodesFrom(cognition)]),
    [seeds, cognition],
  );
  return { nodes, refresh };
}
