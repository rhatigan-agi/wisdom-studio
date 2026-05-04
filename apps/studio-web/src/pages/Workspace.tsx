import { useCallback, useEffect, useMemo, useState } from "react";
import {
  Brain,
  ExternalLink,
  Loader2,
  MessagesSquare,
  Network,
  Sparkles,
  ThumbsDown,
  ThumbsUp,
  Users,
} from "lucide-react";
import { api } from "../lib/api";
import { useStudio } from "../lib/store";
import type {
  AgentMessage,
  ProvenanceContribution,
  SharedMemory,
  TeamInsight,
  TeamInsightProvenance,
  WorkspaceAgentRecord,
  WorkspaceStatus,
  WorkspaceStatusUnavailable,
} from "../types/api";

type Tab = "shared" | "insights" | "messages";

// Workspace surface for wisdom-layer 1.2.0+. The page reads workspace status
// once on mount and either renders an upgrade CTA (no license / wrong tier)
// or the three multi-agent surfaces. Each tab mounts its own data fetcher
// so a slow inbox doesn't block the shared-memory list rendering.
export function Workspace(): JSX.Element {
  const agents = useStudio((s) => s.agents);
  const [status, setStatus] = useState<WorkspaceStatus | null>(null);
  const [workspaceAgents, setWorkspaceAgents] = useState<WorkspaceAgentRecord[]>([]);
  const [tab, setTab] = useState<Tab>("shared");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const next = await api.workspaceStatus();
        if (cancelled) return;
        setStatus(next);
        if (next.available) {
          const records = await api.workspaceAgents();
          if (cancelled) return;
          setWorkspaceAgents(records);
        }
      } catch (err) {
        if (!cancelled) setError(err instanceof Error ? err.message : String(err));
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  if (status === null && error === null) {
    return <CenteredSpinner label="Loading workspace…" />;
  }

  if (error !== null) {
    return (
      <div className="h-full overflow-y-auto px-8 py-10">
        <Header />
        <div className="mt-6 rounded-md border border-rose-900/40 bg-rose-900/10 p-4 text-sm text-rose-200">
          Failed to load workspace: {error}
        </div>
      </div>
    );
  }

  if (status && !status.available) {
    return (
      <div className="h-full overflow-y-auto px-8 py-10">
        <Header />
        <UnavailableCTA status={status} />
      </div>
    );
  }

  return (
    <div className="h-full overflow-y-auto px-4 py-6 md:px-8 md:py-10">
      <Header />
      <SummaryStrip status={status!} workspaceAgents={workspaceAgents} />

      <nav className="mt-6 flex gap-1 border-b border-zinc-800 text-sm" role="tablist">
        <TabButton active={tab === "shared"} onClick={() => setTab("shared")} icon={Brain}>
          Shared Memory
        </TabButton>
        <TabButton active={tab === "insights"} onClick={() => setTab("insights")} icon={Sparkles}>
          Team Insights
        </TabButton>
        <TabButton
          active={tab === "messages"}
          onClick={() => setTab("messages")}
          icon={MessagesSquare}
        >
          Messages
        </TabButton>
      </nav>

      <section className="mt-6">
        {tab === "shared" && (
          <SharedMemoryTab agents={agents} workspaceAgents={workspaceAgents} />
        )}
        {tab === "insights" && <TeamInsightsTab workspaceAgents={workspaceAgents} />}
        {tab === "messages" && <MessagesTab workspaceAgents={workspaceAgents} />}
      </section>
    </div>
  );
}

function Header(): JSX.Element {
  return (
    <header>
      <h1 className="text-2xl font-semibold text-zinc-100">Workspace</h1>
      <p className="mt-1 text-sm text-zinc-400">
        Multi-agent shared memory, team insights, and inter-agent messaging — the
        wisdom-layer 1.2.0 collaboration surface.
      </p>
    </header>
  );
}

function SummaryStrip(props: {
  status: WorkspaceStatus;
  workspaceAgents: WorkspaceAgentRecord[];
}): JSX.Element {
  if (!props.status.available) return <></>;
  return (
    <div className="mt-4 flex flex-wrap gap-3 text-xs text-zinc-400">
      <span className="rounded-md border border-zinc-800 bg-zinc-900/60 px-3 py-1">
        <span className="text-zinc-500">Workspace:</span>{" "}
        <span className="font-mono text-zinc-200">{props.status.workspace_id}</span>
      </span>
      <span className="rounded-md border border-zinc-800 bg-zinc-900/60 px-3 py-1">
        <Users className="mr-1 inline h-3 w-3" />
        {props.workspaceAgents.length} bound agent
        {props.workspaceAgents.length === 1 ? "" : "s"}
      </span>
    </div>
  );
}

function UnavailableCTA(props: { status: WorkspaceStatusUnavailable }): JSX.Element {
  const { reason, message, upgrade_url } = props.status;
  const headline =
    reason === "license_missing"
      ? "Multi-agent workspace is dormant"
      : reason === "enterprise_required"
        ? "Enterprise license required"
        : "Workspace unavailable";
  return (
    <div className="mt-8 rounded-lg border border-zinc-800 bg-zinc-900/40 p-6">
      <h2 className="text-lg font-medium text-zinc-100">{headline}</h2>
      <p className="mt-2 max-w-2xl text-sm text-zinc-400">{message}</p>
      {upgrade_url && (
        <a
          href={upgrade_url}
          target="_blank"
          rel="noreferrer"
          className="mt-4 inline-flex items-center gap-2 rounded-md bg-emerald-600 px-4 py-2 text-sm font-medium text-emerald-50 hover:bg-emerald-500"
        >
          Upgrade <ExternalLink className="h-4 w-4" />
        </a>
      )}
    </div>
  );
}

function TabButton(props: {
  active: boolean;
  onClick: () => void;
  icon: typeof Brain;
  children: React.ReactNode;
}): JSX.Element {
  const Icon = props.icon;
  return (
    <button
      role="tab"
      aria-selected={props.active}
      onClick={props.onClick}
      className={
        props.active
          ? "flex items-center gap-2 border-b-2 border-emerald-500 px-4 py-2 font-medium text-zinc-100"
          : "flex items-center gap-2 border-b-2 border-transparent px-4 py-2 text-zinc-400 hover:text-zinc-200"
      }
    >
      <Icon className="h-4 w-4" />
      {props.children}
    </button>
  );
}

function CenteredSpinner(props: { label: string }): JSX.Element {
  return (
    <div className="flex h-full items-center justify-center text-sm text-zinc-500">
      <Loader2 className="mr-2 h-4 w-4 animate-spin" />
      {props.label}
    </div>
  );
}

// --- Shared Memory tab -----------------------------------------------------

function SharedMemoryTab(props: {
  agents: ReturnType<typeof useStudio.getState>["agents"];
  workspaceAgents: WorkspaceAgentRecord[];
}): JSX.Element {
  const [rows, setRows] = useState<SharedMemory[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [provenanceFor, setProvenanceFor] = useState<TeamInsight | null>(null);

  const refresh = useCallback(async () => {
    try {
      const next = await api.listSharedMemory({ limit: 100 });
      setRows(next);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const agentNames = useMemo(() => agentNameMap(props.agents), [props.agents]);

  if (error) {
    return <ErrorRow message={`Failed to load shared memory: ${error}`} />;
  }
  if (rows === null) return <CenteredSpinner label="Loading shared memory…" />;
  if (rows.length === 0) {
    return (
      <EmptyState
        title="Pool is empty"
        body="Share an agent's memory from the agent's chat view to seed the pool. Once two or more agents have contributed, run a Team Dream to synthesize a cross-agent insight."
      />
    );
  }

  return (
    <div className="grid gap-3">
      {rows.map((row) => (
        <SharedMemoryCard
          key={row.id}
          row={row}
          contributorName={agentNames.get(row.contributor_id) ?? row.contributor_id}
          allAgents={props.workspaceAgents}
          onChanged={refresh}
        />
      ))}
      {provenanceFor && (
        <ProvenanceWalkModal
          insight={provenanceFor}
          onClose={() => setProvenanceFor(null)}
        />
      )}
    </div>
  );
}

function SharedMemoryCard(props: {
  row: SharedMemory;
  contributorName: string;
  allAgents: WorkspaceAgentRecord[];
  onChanged: () => void;
}): JSX.Element {
  const { row, contributorName } = props;
  const [voter, setVoter] = useState<string>("");
  const [busy, setBusy] = useState(false);
  const [contestReason, setContestReason] = useState("");
  const [showContest, setShowContest] = useState(false);

  const otherAgents = useMemo(
    () => props.allAgents.filter((a) => a.agent_id !== row.contributor_id),
    [props.allAgents, row.contributor_id],
  );

  useEffect(() => {
    if (!voter && otherAgents.length > 0) setVoter(otherAgents[0].agent_id);
  }, [voter, otherAgents]);

  async function endorse(): Promise<void> {
    if (!voter) return;
    setBusy(true);
    try {
      await api.endorseSharedMemory(row.id, voter);
      props.onChanged();
    } finally {
      setBusy(false);
    }
  }

  async function contest(): Promise<void> {
    if (!voter || !contestReason.trim()) return;
    setBusy(true);
    try {
      await api.contestSharedMemory(row.id, voter, contestReason.trim());
      setContestReason("");
      setShowContest(false);
      props.onChanged();
    } finally {
      setBusy(false);
    }
  }

  return (
    <article className="rounded-lg border border-zinc-800 bg-zinc-900/40 p-4">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="text-xs uppercase tracking-wider text-zinc-500">
            shared by{" "}
            <span className="font-mono text-zinc-300">{contributorName}</span> ·{" "}
            {new Date(row.shared_at).toLocaleString()}
          </div>
          <p className="mt-2 break-words text-sm text-zinc-100">{row.content}</p>
          {row.reason && (
            <p className="mt-2 text-xs italic text-zinc-400">“{row.reason}”</p>
          )}
        </div>
        <span className="shrink-0 rounded bg-zinc-800 px-2 py-0.5 font-mono text-[10px] text-zinc-400">
          {visibilityLabel(row.visibility)}
        </span>
      </div>

      <div className="mt-3 flex flex-wrap items-center gap-3 text-xs text-zinc-400">
        <span>
          <ThumbsUp className="mr-1 inline h-3 w-3" /> {row.endorsement_count}
        </span>
        <span>
          <ThumbsDown className="mr-1 inline h-3 w-3" /> {row.contention_count}
        </span>
        <span>
          team score:{" "}
          <span className="font-mono text-zinc-200">{row.team_score.toFixed(2)}</span>
        </span>
      </div>

      {otherAgents.length > 0 && (
        <div className="mt-3 flex flex-wrap items-center gap-2 text-xs">
          <label className="text-zinc-500">Vote as:</label>
          <select
            value={voter}
            onChange={(e) => setVoter(e.target.value)}
            className="rounded-md border border-zinc-700 bg-zinc-900 px-2 py-1 text-zinc-200"
          >
            {otherAgents.map((a) => (
              <option key={a.agent_id} value={a.agent_id}>
                {a.agent_id}
              </option>
            ))}
          </select>
          <button
            type="button"
            disabled={busy || !voter}
            onClick={endorse}
            className="rounded-md border border-emerald-700/40 bg-emerald-700/10 px-3 py-1 text-emerald-200 hover:bg-emerald-700/20 disabled:opacity-50"
          >
            Endorse
          </button>
          <button
            type="button"
            onClick={() => setShowContest((v) => !v)}
            className="rounded-md border border-rose-700/40 bg-rose-700/10 px-3 py-1 text-rose-200 hover:bg-rose-700/20"
          >
            Contest…
          </button>
        </div>
      )}
      {showContest && (
        <div className="mt-2 flex flex-wrap items-center gap-2 text-xs">
          <input
            value={contestReason}
            onChange={(e) => setContestReason(e.target.value)}
            placeholder="Why is this wrong?"
            className="min-w-[16rem] flex-1 rounded-md border border-zinc-700 bg-zinc-900 px-2 py-1 text-zinc-200"
          />
          <button
            type="button"
            disabled={busy || !contestReason.trim()}
            onClick={contest}
            className="rounded-md border border-rose-700/40 bg-rose-700/10 px-3 py-1 text-rose-200 hover:bg-rose-700/20 disabled:opacity-50"
          >
            Submit
          </button>
        </div>
      )}
    </article>
  );
}

// --- Team Insights tab -----------------------------------------------------

function TeamInsightsTab(props: {
  workspaceAgents: WorkspaceAgentRecord[];
}): JSX.Element {
  const [rows, setRows] = useState<TeamInsight[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [synth, setSynth] = useState<string>("");
  const [running, setRunning] = useState(false);
  const [runResult, setRunResult] = useState<string | null>(null);
  const [provenanceFor, setProvenanceFor] = useState<TeamInsight | null>(null);

  const refresh = useCallback(async () => {
    try {
      const next = await api.listTeamInsights(50);
      setRows(next);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  useEffect(() => {
    if (!synth && props.workspaceAgents.length > 0) {
      setSynth(props.workspaceAgents[0].agent_id);
    }
  }, [synth, props.workspaceAgents]);

  async function runDream(): Promise<void> {
    if (!synth) return;
    setRunning(true);
    setRunResult(null);
    try {
      const result = await api.runTeamDream(synth, 2);
      if (result.synthesized) {
        setRunResult(`Synthesized insight ${result.insight.id}.`);
      } else {
        setRunResult(`Below threshold (need ≥${result.min_contributors} contributors).`);
      }
      await refresh();
    } catch (err) {
      setRunResult(`Failed: ${err instanceof Error ? err.message : String(err)}`);
    } finally {
      setRunning(false);
    }
  }

  return (
    <div className="space-y-4">
      <div className="rounded-lg border border-zinc-800 bg-zinc-900/40 p-4">
        <h2 className="flex items-center gap-2 text-sm font-medium text-zinc-200">
          <Sparkles className="h-4 w-4 text-emerald-400" />
          Run Team Dream
        </h2>
        <p className="mt-1 text-xs text-zinc-400">
          Synthesizes a cross-agent insight from the shared pool. The synthesizer
          agent's LLM does the synthesis; provenance is recorded for the walk view.
        </p>
        <div className="mt-3 flex flex-wrap items-center gap-2 text-xs">
          <label className="text-zinc-500">Synthesizer:</label>
          <select
            value={synth}
            onChange={(e) => setSynth(e.target.value)}
            className="rounded-md border border-zinc-700 bg-zinc-900 px-2 py-1 text-zinc-200"
          >
            {props.workspaceAgents.map((a) => (
              <option key={a.agent_id} value={a.agent_id}>
                {a.agent_id}
              </option>
            ))}
          </select>
          <button
            type="button"
            disabled={running || !synth}
            onClick={runDream}
            className="flex items-center gap-1 rounded-md border border-emerald-700/40 bg-emerald-700/10 px-3 py-1 text-emerald-200 hover:bg-emerald-700/20 disabled:opacity-50"
          >
            {running && <Loader2 className="h-3 w-3 animate-spin" />}
            Run
          </button>
          {runResult && <span className="text-zinc-400">{runResult}</span>}
        </div>
      </div>

      {error && <ErrorRow message={`Failed to load team insights: ${error}`} />}
      {rows === null && !error && <CenteredSpinner label="Loading team insights…" />}
      {rows !== null && rows.length === 0 && (
        <EmptyState
          title="No team insights yet"
          body="Run a Team Dream above to synthesize one from the shared pool. You'll need at least two agents that have shared memories."
        />
      )}
      {rows && rows.length > 0 && (
        <div className="grid gap-3">
          {rows.map((row) => (
            <TeamInsightCard
              key={row.id}
              insight={row}
              onWalk={() => setProvenanceFor(row)}
            />
          ))}
        </div>
      )}

      {provenanceFor && (
        <ProvenanceWalkModal
          insight={provenanceFor}
          onClose={() => setProvenanceFor(null)}
        />
      )}
    </div>
  );
}

function TeamInsightCard(props: {
  insight: TeamInsight;
  onWalk: () => void;
}): JSX.Element {
  const { insight } = props;
  return (
    <article className="rounded-lg border border-zinc-800 bg-zinc-900/40 p-4">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="text-xs uppercase tracking-wider text-zinc-500">
            {new Date(insight.created_at).toLocaleString()} ·{" "}
            {insight.contributor_count} contributor
            {insight.contributor_count === 1 ? "" : "s"}
          </div>
          <p className="mt-2 break-words text-sm text-zinc-100">{insight.content}</p>
        </div>
        <button
          type="button"
          onClick={props.onWalk}
          className="flex shrink-0 items-center gap-1 rounded-md border border-zinc-700 bg-zinc-800/40 px-3 py-1 text-xs text-zinc-200 hover:bg-zinc-800"
        >
          <Network className="h-3 w-3" />
          Walk provenance
        </button>
      </div>
    </article>
  );
}

// --- Provenance Walk modal -------------------------------------------------
// This is the moat visualization: we surface every contributor's
// `source_memory_id` as an opaque back-pointer, and explicitly call out that
// the underlying private memory content never crosses the workspace boundary.

function ProvenanceWalkModal(props: {
  insight: TeamInsight;
  onClose: () => void;
}): JSX.Element {
  const [data, setData] = useState<TeamInsightProvenance | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const next = await api.walkInsightProvenance(props.insight.id);
        if (!cancelled) setData(next);
      } catch (err) {
        if (!cancelled) setError(err instanceof Error ? err.message : String(err));
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [props.insight.id]);

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 px-4"
      role="dialog"
      aria-modal="true"
      onClick={props.onClose}
    >
      <div
        className="max-h-[90vh] w-full max-w-2xl overflow-y-auto rounded-lg border border-zinc-800 bg-zinc-950 p-6 shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        <header className="flex items-start justify-between gap-3">
          <div>
            <h2 className="flex items-center gap-2 text-lg font-medium text-zinc-100">
              <Network className="h-5 w-5 text-emerald-400" />
              Provenance walk
            </h2>
            <p className="mt-1 text-xs text-zinc-400">
              Every contribution carries an opaque{" "}
              <code className="rounded bg-zinc-800 px-1 py-0.5 text-[11px]">
                source_memory_id
              </code>{" "}
              back-pointer. The underlying private memory never crosses the
              workspace boundary — only the contributing agent can resolve it.
            </p>
          </div>
          <button
            type="button"
            onClick={props.onClose}
            className="rounded-md p-1 text-zinc-400 hover:bg-zinc-800 hover:text-zinc-100"
            aria-label="Close"
          >
            ✕
          </button>
        </header>

        <section className="mt-4 rounded-md border border-emerald-900/40 bg-emerald-900/10 p-3">
          <div className="text-xs uppercase tracking-wider text-emerald-400">
            Synthesized insight
          </div>
          <p className="mt-1 break-words text-sm text-zinc-100">
            {props.insight.content}
          </p>
        </section>

        {error && <ErrorRow message={`Walk failed: ${error}`} />}
        {!data && !error && <CenteredSpinner label="Walking provenance…" />}
        {data && (
          <ol className="mt-4 space-y-3">
            {data.contributions.map((c, idx) => (
              <ProvenanceContributionRow key={c.shared_memory_id} idx={idx} contribution={c} />
            ))}
          </ol>
        )}
      </div>
    </div>
  );
}

function ProvenanceContributionRow(props: {
  idx: number;
  contribution: ProvenanceContribution;
}): JSX.Element {
  const { contribution: c } = props;
  return (
    <li className="rounded-md border border-zinc-800 bg-zinc-900/40 p-3">
      <div className="flex items-center justify-between gap-3 text-xs text-zinc-500">
        <span>
          #{props.idx + 1} — contributor{" "}
          <span className="font-mono text-zinc-200">{c.contributor_agent_id}</span>
        </span>
        <span>weight: {c.contribution_weight.toFixed(2)}</span>
      </div>
      <p className="mt-2 break-words text-sm text-zinc-100">{c.shared_content}</p>
      <div className="mt-2 grid grid-cols-1 gap-2 text-[11px] text-zinc-500 md:grid-cols-2">
        <div>
          shared_memory_id:{" "}
          <span className="break-all font-mono text-zinc-300">{c.shared_memory_id}</span>
        </div>
        <div>
          source_memory_id:{" "}
          <span
            className="break-all font-mono text-zinc-400"
            title="Opaque back-pointer — Studio cannot resolve this to private content."
          >
            {c.source_memory_id}
          </span>
        </div>
      </div>
    </li>
  );
}

// --- Messages tab ----------------------------------------------------------

function MessagesTab(props: {
  workspaceAgents: WorkspaceAgentRecord[];
}): JSX.Element {
  const [viewer, setViewer] = useState<string>("");
  const [inbox, setInbox] = useState<AgentMessage[] | null>(null);
  const [openThread, setOpenThread] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!viewer && props.workspaceAgents.length > 0) {
      setViewer(props.workspaceAgents[0].agent_id);
    }
  }, [viewer, props.workspaceAgents]);

  const refreshInbox = useCallback(async () => {
    if (!viewer) return;
    try {
      const next = await api.getInbox(viewer, { unread_only: false, limit: 50 });
      setInbox(next);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  }, [viewer]);

  useEffect(() => {
    void refreshInbox();
  }, [refreshInbox]);

  return (
    <div className="grid gap-4 lg:grid-cols-[1fr_1fr]">
      <div>
        <SendMessageCard
          workspaceAgents={props.workspaceAgents}
          onSent={refreshInbox}
        />
      </div>
      <div>
        <div className="rounded-lg border border-zinc-800 bg-zinc-900/40 p-4">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <h2 className="flex items-center gap-2 text-sm font-medium text-zinc-200">
              <MessagesSquare className="h-4 w-4 text-emerald-400" />
              Inbox
            </h2>
            <div className="flex items-center gap-2 text-xs">
              <label className="text-zinc-500">View as:</label>
              <select
                value={viewer}
                onChange={(e) => setViewer(e.target.value)}
                className="rounded-md border border-zinc-700 bg-zinc-900 px-2 py-1 text-zinc-200"
              >
                {props.workspaceAgents.map((a) => (
                  <option key={a.agent_id} value={a.agent_id}>
                    {a.agent_id}
                  </option>
                ))}
              </select>
              <button
                type="button"
                onClick={refreshInbox}
                className="rounded-md border border-zinc-700 bg-zinc-800/40 px-2 py-1 text-zinc-200 hover:bg-zinc-800"
              >
                Refresh
              </button>
            </div>
          </div>

          {error && <ErrorRow message={`Inbox failed: ${error}`} />}
          {inbox === null && !error && <CenteredSpinner label="Loading…" />}
          {inbox !== null && inbox.length === 0 && (
            <p className="mt-3 text-sm text-zinc-500">No messages.</p>
          )}
          {inbox && inbox.length > 0 && (
            <ul className="mt-3 space-y-2">
              {inbox.map((m) => (
                <li
                  key={m.id}
                  className={
                    m.read_at
                      ? "rounded-md border border-zinc-800 bg-zinc-900/30 p-3"
                      : "rounded-md border border-emerald-800/40 bg-emerald-900/10 p-3"
                  }
                >
                  <div className="flex items-center justify-between text-xs text-zinc-500">
                    <span>
                      from{" "}
                      <span className="font-mono text-zinc-300">{m.sender_id}</span>
                      {m.is_broadcast && (
                        <span className="ml-2 rounded bg-zinc-800 px-1.5 py-0.5 font-mono text-[10px]">
                          BROADCAST
                        </span>
                      )}
                    </span>
                    <span>{new Date(m.created_at).toLocaleString()}</span>
                  </div>
                  <p className="mt-1 break-words text-sm text-zinc-100">{m.content}</p>
                  <div className="mt-2 flex items-center gap-2 text-xs">
                    <button
                      type="button"
                      onClick={() => setOpenThread(m.thread_id)}
                      className="rounded-md border border-zinc-700 bg-zinc-800/40 px-2 py-0.5 text-zinc-200 hover:bg-zinc-800"
                    >
                      View thread
                    </button>
                    {!m.read_at && viewer && (
                      <button
                        type="button"
                        onClick={async () => {
                          await api.markMessageRead(m.id, viewer);
                          await refreshInbox();
                        }}
                        className="rounded-md border border-zinc-700 bg-zinc-800/40 px-2 py-0.5 text-zinc-200 hover:bg-zinc-800"
                      >
                        Mark read
                      </button>
                    )}
                  </div>
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>
      {openThread && viewer && (
        <ThreadModal
          threadId={openThread}
          viewer={viewer}
          onClose={() => setOpenThread(null)}
          onReplied={refreshInbox}
        />
      )}
    </div>
  );
}

function SendMessageCard(props: {
  workspaceAgents: WorkspaceAgentRecord[];
  onSent: () => void;
}): JSX.Element {
  const [mode, setMode] = useState<"direct" | "broadcast">("direct");
  const [sender, setSender] = useState("");
  const [recipient, setRecipient] = useState("");
  const [capability, setCapability] = useState("general");
  const [content, setContent] = useState("");
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<string | null>(null);

  useEffect(() => {
    if (!sender && props.workspaceAgents.length > 0) {
      setSender(props.workspaceAgents[0].agent_id);
    }
    if (!recipient && props.workspaceAgents.length > 1) {
      setRecipient(props.workspaceAgents[1].agent_id);
    }
  }, [sender, recipient, props.workspaceAgents]);

  async function send(): Promise<void> {
    if (!sender || !content.trim()) return;
    setBusy(true);
    setResult(null);
    try {
      if (mode === "direct") {
        if (!recipient) return;
        await api.sendMessage({
          sender_id: sender,
          recipient_id: recipient,
          content: content.trim(),
          purpose: "question",
        });
      } else {
        await api.broadcastMessage({
          sender_id: sender,
          broadcast_capability: capability.trim() || "general",
          content: content.trim(),
          purpose: "information",
        });
      }
      setContent("");
      setResult("Sent.");
      props.onSent();
    } catch (err) {
      setResult(`Failed: ${err instanceof Error ? err.message : String(err)}`);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="rounded-lg border border-zinc-800 bg-zinc-900/40 p-4">
      <h2 className="flex items-center gap-2 text-sm font-medium text-zinc-200">
        <MessagesSquare className="h-4 w-4 text-emerald-400" />
        Send message
      </h2>

      <div className="mt-3 flex gap-2 text-xs">
        <button
          type="button"
          onClick={() => setMode("direct")}
          className={
            mode === "direct"
              ? "rounded-md bg-zinc-800 px-3 py-1 font-medium text-zinc-100"
              : "rounded-md border border-zinc-700 px-3 py-1 text-zinc-300"
          }
        >
          Direct
        </button>
        <button
          type="button"
          onClick={() => setMode("broadcast")}
          className={
            mode === "broadcast"
              ? "rounded-md bg-zinc-800 px-3 py-1 font-medium text-zinc-100"
              : "rounded-md border border-zinc-700 px-3 py-1 text-zinc-300"
          }
        >
          Broadcast
        </button>
      </div>

      <div className="mt-3 grid gap-2 text-xs">
        <label className="text-zinc-500">From</label>
        <select
          value={sender}
          onChange={(e) => setSender(e.target.value)}
          className="rounded-md border border-zinc-700 bg-zinc-900 px-2 py-1 text-zinc-200"
        >
          {props.workspaceAgents.map((a) => (
            <option key={a.agent_id} value={a.agent_id}>
              {a.agent_id}
            </option>
          ))}
        </select>

        {mode === "direct" ? (
          <>
            <label className="text-zinc-500">To</label>
            <select
              value={recipient}
              onChange={(e) => setRecipient(e.target.value)}
              className="rounded-md border border-zinc-700 bg-zinc-900 px-2 py-1 text-zinc-200"
            >
              {props.workspaceAgents
                .filter((a) => a.agent_id !== sender)
                .map((a) => (
                  <option key={a.agent_id} value={a.agent_id}>
                    {a.agent_id}
                  </option>
                ))}
            </select>
          </>
        ) : (
          <>
            <label className="text-zinc-500">Capability</label>
            <input
              value={capability}
              onChange={(e) => setCapability(e.target.value)}
              placeholder="general"
              className="rounded-md border border-zinc-700 bg-zinc-900 px-2 py-1 text-zinc-200"
            />
          </>
        )}

        <label className="text-zinc-500">Content</label>
        <textarea
          value={content}
          onChange={(e) => setContent(e.target.value)}
          rows={4}
          className="rounded-md border border-zinc-700 bg-zinc-900 px-2 py-1 text-sm text-zinc-100"
        />

        <div className="mt-1 flex items-center gap-2">
          <button
            type="button"
            disabled={busy || !sender || !content.trim()}
            onClick={send}
            className="rounded-md border border-emerald-700/40 bg-emerald-700/10 px-3 py-1 text-emerald-200 hover:bg-emerald-700/20 disabled:opacity-50"
          >
            Send
          </button>
          {result && <span className="text-zinc-400">{result}</span>}
        </div>
      </div>
    </div>
  );
}

function ThreadModal(props: {
  threadId: string;
  viewer: string;
  onClose: () => void;
  onReplied: () => void;
}): JSX.Element {
  const [messages, setMessages] = useState<AgentMessage[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [reply, setReply] = useState("");
  const [busy, setBusy] = useState(false);

  const refresh = useCallback(async () => {
    try {
      const next = await api.getThread(props.threadId);
      setMessages(next);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  }, [props.threadId]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  async function send(): Promise<void> {
    if (!messages || !reply.trim() || messages.length === 0) return;
    setBusy(true);
    try {
      const last = messages[messages.length - 1];
      await api.replyToMessage(last.id, {
        sender_id: props.viewer,
        content: reply.trim(),
        purpose: "information",
      });
      setReply("");
      await refresh();
      props.onReplied();
    } finally {
      setBusy(false);
    }
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 px-4"
      role="dialog"
      aria-modal="true"
      onClick={props.onClose}
    >
      <div
        className="max-h-[90vh] w-full max-w-2xl overflow-y-auto rounded-lg border border-zinc-800 bg-zinc-950 p-6 shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        <header className="flex items-center justify-between gap-3">
          <h2 className="text-lg font-medium text-zinc-100">Thread</h2>
          <button
            type="button"
            onClick={props.onClose}
            className="rounded-md p-1 text-zinc-400 hover:bg-zinc-800 hover:text-zinc-100"
            aria-label="Close"
          >
            ✕
          </button>
        </header>

        {error && <ErrorRow message={`Thread failed: ${error}`} />}
        {!messages && !error && <CenteredSpinner label="Loading thread…" />}
        {messages && (
          <ol className="mt-4 space-y-2">
            {messages.map((m) => (
              <li
                key={m.id}
                className="rounded-md border border-zinc-800 bg-zinc-900/40 p-3"
              >
                <div className="flex items-center justify-between text-xs text-zinc-500">
                  <span>
                    <span className="font-mono text-zinc-300">{m.sender_id}</span>
                    {m.recipient_id && (
                      <span>
                        {" "}
                        →{" "}
                        <span className="font-mono text-zinc-300">{m.recipient_id}</span>
                      </span>
                    )}
                  </span>
                  <span>{new Date(m.created_at).toLocaleString()}</span>
                </div>
                <p className="mt-1 break-words text-sm text-zinc-100">{m.content}</p>
              </li>
            ))}
          </ol>
        )}

        <div className="mt-4 grid gap-2 text-xs">
          <label className="text-zinc-500">Reply as {props.viewer}</label>
          <textarea
            value={reply}
            onChange={(e) => setReply(e.target.value)}
            rows={3}
            className="rounded-md border border-zinc-700 bg-zinc-900 px-2 py-1 text-sm text-zinc-100"
          />
          <div>
            <button
              type="button"
              disabled={busy || !reply.trim()}
              onClick={send}
              className="rounded-md border border-emerald-700/40 bg-emerald-700/10 px-3 py-1 text-emerald-200 hover:bg-emerald-700/20 disabled:opacity-50"
            >
              Send reply
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

// --- Shared helpers --------------------------------------------------------

function ErrorRow(props: { message: string }): JSX.Element {
  return (
    <div className="mt-3 rounded-md border border-rose-900/40 bg-rose-900/10 p-3 text-sm text-rose-200">
      {props.message}
    </div>
  );
}

function EmptyState(props: { title: string; body: string }): JSX.Element {
  return (
    <div className="rounded-lg border border-dashed border-zinc-800 px-6 py-10 text-center">
      <h3 className="text-base font-medium text-zinc-200">{props.title}</h3>
      <p className="mx-auto mt-2 max-w-md text-sm text-zinc-400">{props.body}</p>
    </div>
  );
}

function visibilityLabel(raw: string): string {
  // SDK returns enum repr like "Visibility.TEAM"; strip the prefix.
  return raw.includes(".") ? raw.split(".").pop()! : raw;
}

function agentNameMap(
  agents: ReturnType<typeof useStudio.getState>["agents"],
): Map<string, string> {
  return new Map(agents.map((a) => [a.agent_id, a.name]));
}
