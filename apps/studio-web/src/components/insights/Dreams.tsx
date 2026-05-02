import { useCallback, useEffect, useState } from "react";
import { RefreshCw } from "lucide-react";
import { api } from "../../lib/api";
import type { CognitionEvent } from "../../types/api";
import type { DreamReport, DreamScheduleStatus } from "../../types/sdk";

interface Props {
  agentId: string;
  cognition: CognitionEvent[];
}

function formatTime(iso: string | null): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleString();
}

function formatDuration(ms: number): string {
  if (ms < 1000) return `${ms}ms`;
  const s = ms / 1000;
  if (s < 60) return `${s.toFixed(1)}s`;
  return `${(s / 60).toFixed(1)}m`;
}

export function DreamsPanel({ agentId, cognition }: Props): JSX.Element {
  const [schedule, setSchedule] = useState<DreamScheduleStatus | null>(null);
  const [history, setHistory] = useState<DreamReport[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async (): Promise<void> => {
    setError(null);
    try {
      const [s, h] = await Promise.all([
        api.dreamScheduleStatus(agentId),
        api.dreamHistory(agentId, 10),
      ]);
      setSchedule(s);
      setHistory(h);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  }, [agentId]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  // Auto-refresh when a cycle finishes so the new entry appears at the top
  // without the user clicking refresh.
  useEffect(() => {
    const last = cognition[cognition.length - 1];
    if (last?.type === "dream.cycle.completed") {
      void refresh();
    }
  }, [cognition, refresh]);

  const loading = schedule === null && history === null && !error;

  return (
    <div className="flex h-full flex-col">
      <div className="flex items-center justify-between border-b border-zinc-800 px-3 py-2">
        <span className="text-[11px] text-zinc-400">Schedule + recent cycles</span>
        <button
          type="button"
          onClick={() => void refresh()}
          className="flex items-center gap-1 text-[11px] text-zinc-500 hover:text-zinc-200"
          aria-label="Refresh dreams"
        >
          <RefreshCw className="h-3 w-3" />
        </button>
      </div>

      <div className="flex-1 overflow-y-auto px-3 py-3 font-mono text-[11px]">
        {error && (
          <div className="mb-3 rounded border border-red-500/40 bg-red-500/10 px-2 py-1 text-red-300">
            {error}
          </div>
        )}
        {loading && <div className="text-zinc-500">Loading…</div>}

        {schedule && (
          <section className="mb-4 grid grid-cols-2 gap-2">
            <div className="rounded border border-violet-700/30 bg-violet-900/10 px-2 py-1.5">
              <p className="text-[10px] uppercase tracking-wider text-violet-300">Last run</p>
              <p className="mt-1 text-zinc-200">{formatTime(schedule.last_run)}</p>
            </div>
            <div className="rounded border border-violet-700/30 bg-violet-900/10 px-2 py-1.5">
              <p className="text-[10px] uppercase tracking-wider text-violet-300">Next run</p>
              <p className="mt-1 text-zinc-200">{formatTime(schedule.next_run)}</p>
            </div>
          </section>
        )}

        <section>
          <p className="mb-2 text-[10px] uppercase tracking-wider text-zinc-500">
            Recent cycles {history !== null && `· ${history.length}`}
          </p>
          {history && history.length === 0 && (
            <div className="text-zinc-600">
              No dream cycles yet. Trigger one from the &ldquo;Dream now&rdquo; button.
            </div>
          )}
          <ul className="space-y-2">
            {history?.map((report) => (
              <li
                key={report.cycle_id}
                className="rounded border border-violet-700/30 bg-violet-900/5 px-2 py-1.5"
              >
                <div className="flex items-center justify-between text-[10px] text-zinc-500">
                  <span className="text-violet-300">
                    {new Date(report.completed_at).toLocaleString()}
                  </span>
                  <span>{formatDuration(report.total_duration_ms)}</span>
                </div>
                <div className="mt-1 grid grid-cols-3 gap-2 text-zinc-300">
                  <Stat label="reconsolidated" value={report.reconsolidated} />
                  <Stat label="insights" value={report.new_insights} />
                  <Stat label="proposals" value={report.directives_proposed} />
                </div>
                {report.total_tokens > 0 && (
                  <div className="mt-1 text-[10px] text-zinc-500">
                    {report.total_tokens.toLocaleString()} tokens · $
                    {report.total_usd.toFixed(4)}
                  </div>
                )}
              </li>
            ))}
          </ul>
        </section>
      </div>
    </div>
  );
}

function Stat(props: { label: string; value: number }): JSX.Element {
  return (
    <div>
      <p className="text-[10px] uppercase tracking-wider text-zinc-500">{props.label}</p>
      <p className="text-zinc-200">{props.value}</p>
    </div>
  );
}
