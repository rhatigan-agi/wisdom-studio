import { useCallback, useEffect, useState } from "react";
import { ChevronDown, ChevronRight, RefreshCw } from "lucide-react";
import { api } from "../../lib/api";
import type { CognitionEvent } from "../../types/api";
import type { JournalEntry } from "../../types/sdk";

interface Props {
  agentId: string;
  // Refresh when a dream cycle finishes — the SDK writes a new journal at
  // the end of every cycle, and we want it to surface without manual reload.
  cognition: CognitionEvent[];
}

const PREVIEW_CHARS = 240;

export function JournalsPanel({ agentId, cognition }: Props): JSX.Element {
  const [entries, setEntries] = useState<JournalEntry[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [openIds, setOpenIds] = useState<Set<string>>(new Set());

  const refresh = useCallback(async (): Promise<void> => {
    setError(null);
    try {
      const list = await api.listJournals(agentId, 20);
      setEntries(list);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  }, [agentId]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  useEffect(() => {
    const last = cognition[cognition.length - 1];
    if (!last) return;
    if (last.type === "journal.created" || last.type === "dream.cycle.completed") {
      void refresh();
    }
  }, [cognition, refresh]);

  const toggle = (id: string): void => {
    setOpenIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const loading = entries === null && !error;

  return (
    <div className="flex h-full flex-col">
      <div className="flex items-center justify-between border-b border-zinc-800 px-3 py-2">
        <span className="text-[11px] text-zinc-400">
          Reverse chronological · last 20
        </span>
        <button
          type="button"
          onClick={() => void refresh()}
          className="flex items-center gap-1 text-[11px] text-zinc-500 hover:text-zinc-200"
          aria-label="Refresh journals"
        >
          <RefreshCw className="h-3 w-3" />
        </button>
      </div>

      <div className="flex-1 overflow-y-auto px-3 py-3 font-mono text-[11px]">
        {error && (
          <div className="rounded border border-red-500/40 bg-red-500/10 px-2 py-1 text-red-300">
            {error}
          </div>
        )}
        {loading && <div className="text-zinc-500">Loading…</div>}
        {entries && entries.length === 0 && (
          <div className="text-zinc-600">
            No journals yet. The agent writes one at the end of each dream cycle.
          </div>
        )}

        <ul className="space-y-2">
          {entries?.map((entry) => {
            const open = openIds.has(entry.id);
            const needsToggle = entry.content.length > PREVIEW_CHARS;
            const body =
              open || !needsToggle
                ? entry.content
                : `${entry.content.slice(0, PREVIEW_CHARS)}…`;
            return (
              <li
                key={entry.id}
                className="rounded border border-sky-700/30 bg-sky-900/5 px-2 py-1.5"
              >
                <div className="flex items-center justify-between text-[10px] text-zinc-500">
                  <span className="text-sky-300">
                    {new Date(entry.created_at).toLocaleString()}
                  </span>
                  <span>{entry.memory_ids.length} memories</span>
                </div>
                <p className="mt-1 whitespace-pre-wrap break-words text-zinc-200">{body}</p>
                {needsToggle && (
                  <button
                    type="button"
                    onClick={() => toggle(entry.id)}
                    className="mt-1 flex items-center gap-1 text-zinc-500 hover:text-zinc-200"
                    aria-expanded={open}
                  >
                    {open ? (
                      <ChevronDown className="h-3 w-3" />
                    ) : (
                      <ChevronRight className="h-3 w-3" />
                    )}
                    {open ? "Collapse" : "Expand"}
                  </button>
                )}
              </li>
            );
          })}
        </ul>
      </div>
    </div>
  );
}
