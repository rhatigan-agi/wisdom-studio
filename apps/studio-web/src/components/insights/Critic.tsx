import { useCallback, useEffect, useState } from "react";
import { Play, RefreshCw } from "lucide-react";
import { api } from "../../lib/api";
import type { AuditReport, EntropyLevel, EntropySnapshot, RiskLevel } from "../../types/sdk";

interface Props {
  agentId: string;
}

const ENTROPY_TONES: Record<EntropyLevel, string> = {
  healthy: "border-emerald-700/40 bg-emerald-900/10 text-emerald-200",
  elevated: "border-amber-700/40 bg-amber-900/10 text-amber-200",
  high: "border-rose-700/40 bg-rose-900/10 text-rose-200",
  critical: "border-red-700/40 bg-red-900/20 text-red-200",
};

const RISK_TONES: Record<RiskLevel, string> = {
  low: "text-emerald-300",
  medium: "text-amber-300",
  high: "text-rose-300",
  critical: "text-red-300",
};

export function CriticPanel({ agentId }: Props): JSX.Element {
  const [entropy, setEntropy] = useState<EntropySnapshot | null>(null);
  const [audit, setAudit] = useState<AuditReport | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [auditing, setAuditing] = useState(false);

  const loadEntropy = useCallback(async (): Promise<void> => {
    setError(null);
    try {
      const snap = await api.criticEntropy(agentId);
      setEntropy(snap);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  }, [agentId]);

  useEffect(() => {
    void loadEntropy();
  }, [loadEntropy]);

  const onRunAudit = async (): Promise<void> => {
    setAuditing(true);
    setError(null);
    try {
      const report = await api.runCriticAudit(agentId);
      setAudit(report);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setAuditing(false);
    }
  };

  const loading = entropy === null && !error;

  return (
    <div className="flex h-full flex-col">
      <div className="flex items-center justify-between border-b border-zinc-800 px-3 py-2">
        <span className="text-[11px] text-zinc-400">Entropy + on-demand audit</span>
        <button
          type="button"
          onClick={() => void loadEntropy()}
          className="flex items-center gap-1 text-[11px] text-zinc-500 hover:text-zinc-200"
          aria-label="Refresh entropy"
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

        {entropy && (
          <section className="mb-4">
            <p className="mb-2 text-[10px] uppercase tracking-wider text-zinc-500">
              Directive entropy
            </p>
            <div className={`rounded border px-2 py-2 ${ENTROPY_TONES[entropy.level]}`}>
              <div className="flex items-center justify-between">
                <span className="text-[10px] uppercase tracking-wider opacity-80">
                  {entropy.level}
                </span>
                <span className="font-mono">{entropy.entropy_score.toFixed(2)}</span>
              </div>
              <div className="mt-2 grid grid-cols-3 gap-2 text-zinc-300">
                <Stat label="churn" value={entropy.churn.toFixed(2)} />
                <Stat label="volume" value={String(entropy.volume)} />
                <Stat label="staleness" value={entropy.staleness.toFixed(2)} />
              </div>
              <p className="mt-2 text-[10px] text-zinc-400">
                {entropy.total_directives} total directives
              </p>
            </div>
          </section>
        )}

        <section>
          <div className="mb-2 flex items-center justify-between">
            <p className="text-[10px] uppercase tracking-wider text-zinc-500">Audit</p>
            <button
              type="button"
              onClick={() => void onRunAudit()}
              disabled={auditing}
              className="flex items-center gap-1 rounded border border-rose-700/40 bg-rose-900/10 px-2 py-0.5 text-rose-200 hover:bg-rose-900/30 disabled:opacity-50"
            >
              <Play className="h-3 w-3" />
              {auditing ? "Auditing…" : "Run audit"}
            </button>
          </div>

          {!audit && !auditing && (
            <div className="text-zinc-600">
              No audit yet. Auditing scans recent outputs for drift, contradictions, and
              directive adherence — may take several seconds.
            </div>
          )}

          {audit && (
            <div className="rounded border border-rose-700/30 bg-rose-900/5 px-2 py-1.5">
              <p className="text-[10px] text-zinc-500">{audit.period}</p>
              <div className="mt-2 grid grid-cols-2 gap-2 text-zinc-300">
                <Stat label="consistency" value={audit.consistency_score.toFixed(2)} />
                <Stat label="adherence" value={audit.directive_adherence.toFixed(2)} />
                <Stat label="drift" value={audit.narrative_drift_score.toFixed(2)} />
                <Stat label="self-correct" value={audit.self_correction_rate.toFixed(2)} />
              </div>
              {audit.flags.length > 0 && (
                <div className="mt-3">
                  <p className="mb-1 text-[10px] uppercase tracking-wider text-zinc-500">
                    Flags · {audit.flags.length}
                  </p>
                  <ul className="space-y-1">
                    {audit.flags.map((flag, i) => (
                      <li
                        key={i}
                        className="rounded border border-zinc-800 bg-zinc-950/60 px-2 py-1"
                      >
                        <div className="flex items-center justify-between">
                          <span className="text-zinc-300">{flag.category}</span>
                          <span className={RISK_TONES[flag.severity]}>{flag.severity}</span>
                        </div>
                        <p className="mt-1 text-zinc-400">{flag.description}</p>
                        {flag.evidence && (
                          <p className="mt-1 text-zinc-500">{flag.evidence}</p>
                        )}
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </div>
          )}
        </section>
      </div>
    </div>
  );
}

function Stat(props: { label: string; value: string }): JSX.Element {
  return (
    <div>
      <p className="text-[10px] uppercase tracking-wider text-zinc-500">{props.label}</p>
      <p className="text-zinc-200">{props.value}</p>
    </div>
  );
}
