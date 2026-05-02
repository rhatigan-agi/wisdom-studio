import { useCallback, useEffect, useState } from "react";
import { Check, RefreshCw, X } from "lucide-react";
import { api } from "../../lib/api";
import type { CognitionEvent } from "../../types/api";
import type { Directive, DirectiveProposal, DirectiveStatus } from "../../types/sdk";

interface Props {
  agentId: string;
  // Cognition stream is threaded in so the panel can refresh when a dream
  // cycle promotes / proposes / decays directives. Without this the panel
  // would show stale data until the user tabbed away and back.
  cognition: CognitionEvent[];
}

const STATUS_TONES: Record<DirectiveStatus, string> = {
  active: "border-amber-700/40 bg-amber-900/10 text-amber-200",
  provisional: "border-zinc-700 bg-zinc-900/40 text-zinc-300",
  permanent: "border-emerald-700/40 bg-emerald-900/10 text-emerald-200",
  inactive: "border-zinc-800 bg-zinc-900/20 text-zinc-500",
};

export function DirectivesPanel({ agentId, cognition }: Props): JSX.Element {
  const [directives, setDirectives] = useState<Directive[] | null>(null);
  const [proposals, setProposals] = useState<DirectiveProposal[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [showInactive, setShowInactive] = useState(false);

  const refresh = useCallback(async (): Promise<void> => {
    setError(null);
    try {
      const [list, pending] = await Promise.all([
        api.listDirectives(agentId, showInactive),
        api.listProposals(agentId),
      ]);
      setDirectives(list);
      setProposals(pending);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  }, [agentId, showInactive]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  // Refresh when the cognition stream signals a directive change. The SDK
  // emits these from approve / reject / dream consolidation paths.
  useEffect(() => {
    const last = cognition[cognition.length - 1];
    if (!last) return;
    if (last.type.startsWith("directive.") || last.type === "dream.cycle.completed") {
      void refresh();
    }
  }, [cognition, refresh]);

  const onApprove = async (id: string): Promise<void> => {
    setBusyId(id);
    try {
      await api.approveProposal(agentId, id);
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusyId(null);
    }
  };

  const onReject = async (id: string): Promise<void> => {
    setBusyId(id);
    try {
      await api.rejectProposal(agentId, id);
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusyId(null);
    }
  };

  const loading = directives === null && proposals === null && !error;

  return (
    <div className="flex h-full flex-col">
      <div className="flex items-center justify-between border-b border-zinc-800 px-3 py-2">
        <label className="flex items-center gap-2 text-[11px] text-zinc-400">
          <input
            type="checkbox"
            checked={showInactive}
            onChange={(e) => setShowInactive(e.target.checked)}
            className="h-3 w-3 accent-amber-500"
          />
          Include inactive
        </label>
        <button
          type="button"
          onClick={() => void refresh()}
          className="flex items-center gap-1 text-[11px] text-zinc-500 hover:text-zinc-200"
          aria-label="Refresh directives"
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

        {proposals && proposals.length > 0 && (
          <section className="mb-4">
            <p className="mb-2 text-[10px] uppercase tracking-wider text-amber-400">
              Pending proposals · {proposals.length}
            </p>
            <ul className="space-y-2">
              {proposals.map((p) => (
                <li
                  key={p.id}
                  className="rounded border border-amber-700/30 bg-amber-900/5 px-2 py-1.5"
                >
                  <div className="flex items-center justify-between text-zinc-500">
                    <span className="text-amber-300">{p.action}</span>
                    <span>conf {p.confidence.toFixed(2)}</span>
                  </div>
                  <p className="mt-1 whitespace-pre-wrap break-words text-zinc-200">{p.text}</p>
                  {p.reasoning && (
                    <p className="mt-1 text-zinc-500">{p.reasoning}</p>
                  )}
                  <div className="mt-2 flex items-center gap-2">
                    <button
                      type="button"
                      onClick={() => void onApprove(p.id)}
                      disabled={busyId === p.id}
                      className="flex items-center gap-1 rounded border border-emerald-700/40 bg-emerald-900/20 px-2 py-0.5 text-emerald-200 hover:bg-emerald-900/40 disabled:opacity-50"
                    >
                      <Check className="h-3 w-3" />
                      Approve
                    </button>
                    <button
                      type="button"
                      onClick={() => void onReject(p.id)}
                      disabled={busyId === p.id}
                      className="flex items-center gap-1 rounded border border-zinc-700 bg-zinc-900/40 px-2 py-0.5 text-zinc-300 hover:bg-zinc-800 disabled:opacity-50"
                    >
                      <X className="h-3 w-3" />
                      Reject
                    </button>
                  </div>
                </li>
              ))}
            </ul>
          </section>
        )}

        <section>
          <p className="mb-2 text-[10px] uppercase tracking-wider text-zinc-500">
            Directives {directives !== null && `· ${directives.length}`}
          </p>
          {directives && directives.length === 0 && (
            <div className="text-zinc-600">
              No directives yet. The agent earns these from dream cycles or human approval.
            </div>
          )}
          <ul className="space-y-1">
            {directives?.map((d) => (
              <li
                key={d.id}
                className={`rounded border px-2 py-1.5 ${STATUS_TONES[d.status]}`}
              >
                <div className="flex items-center justify-between text-[10px] uppercase tracking-wider opacity-70">
                  <span>{d.status}</span>
                  <span>used {d.usage_count}×</span>
                </div>
                <p className="mt-1 whitespace-pre-wrap break-words">{d.text}</p>
              </li>
            ))}
          </ul>
        </section>
      </div>
    </div>
  );
}
