import { useEffect, useRef, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { Activity, ChevronDown, ChevronRight, Database, Lightbulb, Sparkles, Send, Trash, Trash2, Lock, X, PanelRightOpen, Layers } from "lucide-react";
import { SessionStateError, TierError, api } from "../lib/api";
import { useStudio } from "../lib/store";
import { SESSION_EXPIRED_EVENT } from "../components/kiosk/SessionTimer";
import { SessionEndedView } from "../components/kiosk/SessionEndedView";
import { ChatMarkdown } from "../components/ChatMarkdown";
import { MemoryMapOverlay } from "../components/MemoryMapOverlay";
import { useMemoryMap } from "../components/useMemoryMap";
import { DirectivesPanel } from "../components/insights/Directives";
import { JournalsPanel } from "../components/insights/Journals";
import { DreamsPanel } from "../components/insights/Dreams";
import { CriticPanel } from "../components/insights/Critic";
import type {
  AgentDetail as AgentDetailType,
  ChatCompareResponse,
  ChatMessage,
  CognitionEvent,
} from "../types/api";

type SidePane = "cognition" | "memories" | "insights";
type InsightsTab = "directives" | "journals" | "dreams" | "critic";

interface MemorySearchHit {
  id?: string;
  event_type?: string;
  content?: Record<string, unknown>;
  similarity?: number;
  salience?: number;
  created_at?: string;
}

// Discriminated union: a single chat row is either a user/agent text line
// or a compare-mode card carrying three side-by-side answers from the SDK's
// /api/chat endpoint. Agent lines optionally carry an `informed` snapshot
// (memories + directives the response was grounded in) for the per-message
// "What informed this?" disclosure.
interface InformedBy {
  memories: string[];
  directives: string[];
}

type ChatLine =
  | { role: "user"; text: string; ts: string }
  | { role: "agent"; text: string; ts: string; informed?: InformedBy }
  | { role: "compare"; question: string; result: ChatCompareResponse; ts: string };

// Stable empty array for the cognition fallback. `useStudio((s) => x ?? [])`
// returns a new `[]` per call when `x` is undefined; Object.is then reports
// the selector value as changed every render, defeating zustand's bail-out.
const EMPTY_COGNITION: readonly CognitionEvent[] = Object.freeze([]);

// One-shot dream-button onboarding hint. Stored as a single boolean flag.
// Persistent installs use localStorage so a returning user isn't prompted
// again; ephemeral demos use sessionStorage so the next visitor (different
// tab, same browser) still sees the hint.
const DREAM_HINT_KEY = "wisdom-studio:dream-hint-seen";

function dreamHintStorage(ephemeral: boolean): Storage | null {
  // Privacy-mode browsers can throw on storage access; treat that as "no
  // persistence" (the hint will re-show next session, harmless).
  try {
    return ephemeral ? window.sessionStorage : window.localStorage;
  } catch {
    return null;
  }
}

function readDreamHintFlag(ephemeral: boolean): boolean {
  const store = dreamHintStorage(ephemeral);
  if (!store) return false;
  try {
    return store.getItem(DREAM_HINT_KEY) === "1";
  } catch {
    return false;
  }
}

function writeDreamHintFlag(ephemeral: boolean): void {
  const store = dreamHintStorage(ephemeral);
  if (!store) return;
  try {
    store.setItem(DREAM_HINT_KEY, "1");
  } catch {
    // Storage quota / private mode — silently no-op. The hint will re-show
    // on next mount, which is acceptable for a low-stakes onboarding nudge.
  }
}

type WsState = "idle" | "connecting" | "live" | "closed" | "reconnecting" | "lost";

// Backoff schedule for the cognition WebSocket reconnect loop. Bounded to
// five attempts (~9s total) so a permanently-down backend can't burn a
// visitor's tab in an infinite reconnect loop. Manual retry from the "lost"
// banner resets the counter.
const WS_BACKOFF_MS = [250, 500, 1000, 2000, 5000] as const;

// Close codes that signal an *intentional* close — never reconnect.
//  1000     = normal closure (component unmount, browser nav, our cleanup)
//  4000-4999 = application close from the backend (4404 unknown agent,
//              4500 boot failed). Retrying would just spam the server.
function isIntentionalClose(code: number): boolean {
  return code === 1000 || (code >= 4000 && code < 5000);
}

export function AgentDetail(): JSX.Element {
  const { agentId = "" } = useParams<{ agentId: string }>();
  const navigate = useNavigate();
  const setAgents = useStudio((s) => s.setAgents);
  const hideCrud = useStudio((s) => s.config?.hide_agent_crud ?? false);
  const [detail, setDetail] = useState<AgentDetailType | null>(null);
  const [chat, setChat] = useState<ChatLine[]>([]);
  const [draft, setDraft] = useState("");
  const [sending, setSending] = useState(false);
  const [dreaming, setDreaming] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [compareMode, setCompareMode] = useState(false);

  const appendCognitionBatch = useStudio((s) => s.appendCognitionBatch);
  const cognition = useStudio(
    (s) => s.cognitionByAgent[agentId] ?? (EMPTY_COGNITION as CognitionEvent[]),
  );
  const clearCognition = useStudio((s) => s.clearCognition);

  const [sidePane, setSidePane] = useState<SidePane>("cognition");
  const [insightsTab, setInsightsTab] = useState<InsightsTab>("directives");
  const [memoryQuery, setMemoryQuery] = useState("");
  const [memories, setMemories] = useState<MemorySearchHit[]>([]);
  const [memoriesLoading, setMemoriesLoading] = useState(false);
  const [memoriesError, setMemoriesError] = useState<string | null>(null);
  const [tierError, setTierError] = useState<TierError | null>(null);

  // Mobile-only: side pane is hidden by default and revealed via the
  // floating action button in the chat column. Desktop ignores this state
  // because the lg-breakpoint grid renders both columns side-by-side.
  const [paneOpen, setPaneOpen] = useState(false);

  const [wsState, setWsState] = useState<WsState>("idle");
  // Bumped by the "Reconnect" button in the lost-connection banner. The WS
  // effect depends on this, so incrementing it tears down any current
  // socket + retry timer and starts a fresh connect cycle from attempt 0.
  const [wsConnectKey, setWsConnectKey] = useState(0);

  // Memory map: dedup'd union of seed-probe results and live captures from
  // the cognition stream. Rendered as a floating bottom-right overlay
  // (MemoryMapOverlay) independent of the side pane. Wait until the WS
  // reports `live` before probing the SDK memory route — the per-agent
  // sub-app is mounted lazily by SessionManager and probing it earlier
  // 404s.
  const mapNodes = useMemoryMap(agentId, cognition, wsState === "live");

  // Server-confirmed session lifecycle. Polled when the deployment configures
  // a TTL or token cap; otherwise stays null and the surface renders normally.
  // The polled state is mirrored into the store so SessionTimer can read
  // `expires_at` directly from the backend authority. SessionStateError on
  // chat flips this synchronously so the visitor doesn't see the chat input
  // after they've been gated.
  const sessionTtl = useStudio((s) => s.config?.session_ttl_minutes ?? null);
  const tokenCap = useStudio((s) => s.config?.token_cap_per_session ?? null);
  const sessionGated = sessionTtl !== null || tokenCap !== null;
  const setSessionState = useStudio((s) => s.setSessionState);
  const sessionStateName = useStudio((s) => s.sessionState?.state ?? "active");
  const ephemeral = useStudio((s) => s.config?.ephemeral ?? false);

  // One-shot dream-button hint. Surfaces after the visitor has sent two
  // messages, then never again on this browser/tab. Persistent installs use
  // localStorage (don't re-prompt across tabs); ephemeral demos use
  // sessionStorage so a fresh visitor in the same browser still sees it.
  const [dreamHintDismissed, setDreamHintDismissed] = useState<boolean>(() =>
    readDreamHintFlag(ephemeral),
  );
  const dismissDreamHint = (): void => {
    setDreamHintDismissed(true);
    writeDreamHintFlag(ephemeral);
  };
  const userMessageCount = chat.filter((l) => l.role === "user").length;
  const showDreamHint =
    !dreamHintDismissed && userMessageCount >= 2 && !dreaming && sessionStateName === "active";

  // Per-agent UI state must reset when the route changes. Without this,
  // switching from agent A to agent B carries A's chat history into B's
  // composer — and because we thread prior turns back to the SDK as
  // grounding context, B will capture facts from A's conversation into
  // *B's* memory store. Memory itself is correctly isolated per-agent
  // (separate SQLite files); the bleed is purely a frontend state issue.
  // Memory-search results are also agent-scoped, so reset those too.
  useEffect(() => {
    setChat([]);
    setTierError(null);
    setMemories([]);
    setMemoryQuery("");
    setMemoriesError(null);
    setDraft("");
  }, [agentId]);

  useEffect(() => {
    if (!agentId || !sessionGated) {
      setSessionState(null);
      return;
    }
    let cancelled = false;
    const tick = async (): Promise<void> => {
      try {
        const state = await api.getSessionState(agentId);
        if (!cancelled) setSessionState(state);
      } catch {
        // Network blips shouldn't kick a visitor out — they'll see the
        // gated state on the next /chat attempt regardless.
      }
    };
    void tick();
    const id = window.setInterval(() => void tick(), 5000);
    return () => {
      cancelled = true;
      window.clearInterval(id);
    };
  }, [agentId, sessionGated, setSessionState]);

  useEffect(() => {
    return () => {
      // Clear when the user navigates away so a stale countdown from one
      // agent doesn't bleed into the dashboard for the next.
      setSessionState(null);
    };
  }, [agentId, setSessionState]);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const fetched = await api.getAgent(agentId);
        if (!cancelled) setDetail(fetched);
      } catch (error) {
        console.error("studio: load agent failed", error);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [agentId]);

  // Session-TTL deployments dispatch this event when the visible countdown
  // hits zero. We treat it as a "reset to dashboard" signal so the next
  // visitor lands on a clean view rather than mid-conversation.
  useEffect(() => {
    const onExpired = (): void => {
      navigate("/", { replace: true });
    };
    window.addEventListener(SESSION_EXPIRED_EVENT, onExpired);
    return () => window.removeEventListener(SESSION_EXPIRED_EVENT, onExpired);
  }, [navigate]);

  // Owned WebSocket lifecycle with bounded auto-reconnect. Vanilla
  // WebSocket so we control connect/close exactly — third-party hooks were
  // tearing the socket down on unrelated re-renders. SDK WebSocketHub
  // batches events on a 100 ms flush interval and sends them as a JSON
  // array per message; each event has shape `{type, timestamp, data}`.
  //
  // Reconnect policy: transient transport-level closes (network blips,
  // backend restarts under deploy) trigger backoff retries. Intentional
  // closes — code 1000 (cleanup / browser nav) and the 4xxx app codes from
  // `cognition_socket` — are respected and surface as a "closed" state
  // with a manual retry option. After WS_BACKOFF_MS exhausts we go to
  // "lost", and the banner's Reconnect button bumps `wsConnectKey` to
  // reset the cycle.
  //
  // React 18 StrictMode runs effect → cleanup → effect on every mount in
  // dev. The first cleanup closes a still-CONNECTING socket, which the
  // browser surfaces as a "close" event. The `closedByCleanup` flag
  // suppresses any state transitions from that stale socket so it can't
  // race the second socket's `open` and flip wsState back to "closed".
  useEffect(() => {
    if (!agentId) return;
    const proto = window.location.protocol === "https:" ? "wss" : "ws";
    const url = `${proto}://${window.location.host}/ws/cognition/${agentId}`;

    let closedByCleanup = false;
    let ws: WebSocket | null = null;
    let retryTimer: number | null = null;
    let retryCount = 0;

    const connect = (): void => {
      setWsState(retryCount === 0 ? "connecting" : "reconnecting");
      const socket = new WebSocket(url);
      ws = socket;
      socket.onopen = (): void => {
        if (closedByCleanup) return;
        retryCount = 0;
        setWsState("live");
      };
      socket.onclose = (event: CloseEvent): void => {
        if (closedByCleanup) return;
        if (isIntentionalClose(event.code)) {
          setWsState("closed");
          return;
        }
        if (retryCount >= WS_BACKOFF_MS.length) {
          setWsState("lost");
          return;
        }
        const delay = WS_BACKOFF_MS[retryCount];
        retryCount += 1;
        setWsState("reconnecting");
        retryTimer = window.setTimeout(() => {
          retryTimer = null;
          if (!closedByCleanup) connect();
        }, delay);
      };
      socket.onerror = (): void => {
        // Do not transition state here — `onerror` always fires before
        // `onclose`, and `onclose` carries the close code we need to
        // decide between "closed", "reconnecting", or "lost".
      };
      socket.onmessage = (event: MessageEvent<string>): void => {
        if (closedByCleanup) return;
        let parsed: unknown;
        try {
          parsed = JSON.parse(event.data);
        } catch {
          return;
        }
        const batch = Array.isArray(parsed) ? parsed : [parsed];
        const events: CognitionEvent[] = batch.map((raw) => {
          const r = raw as { type: string; timestamp: string; data?: Record<string, unknown> };
          return {
            agent_id: agentId,
            type: r.type,
            timestamp: r.timestamp,
            data: r.data ?? {},
          };
        });
        appendCognitionBatch(agentId, events);
      };
    };

    connect();

    return () => {
      closedByCleanup = true;
      if (retryTimer !== null) {
        window.clearTimeout(retryTimer);
        retryTimer = null;
      }
      if (ws) {
        // Detach handlers BEFORE close so any error/close fired by the
        // close itself can't reach the (now-stale) closure.
        ws.onopen = null;
        ws.onclose = null;
        ws.onerror = null;
        ws.onmessage = null;
        if (ws.readyState === WebSocket.OPEN || ws.readyState === WebSocket.CONNECTING) {
          ws.close();
        }
      }
    };
  }, [agentId, appendCognitionBatch, wsConnectKey]);

  const sendMessage = async (message: string): Promise<void> => {
    if (!message || sending) return;
    setSending(true);
    setDraft("");
    const userLine: ChatLine = { role: "user", text: message, ts: new Date().toISOString() };
    setChat((prev) => [...prev, userLine]);
    try {
      if (compareMode) {
        // Compare-mode hits the SDK's /api/chat (mode=all) for a single side-
        // by-side baseline / memory / wisdom answer. It is intentionally
        // *not* captured to memory — the demo would otherwise pollute the
        // grounding for the next compare with stale baseline answers.
        const result = await api.chatCompare(agentId, message, "all");
        setChat((prev) => [
          ...prev,
          { role: "compare", question: message, result, ts: new Date().toISOString() },
        ]);
      } else {
        // Thread the most recent N turns back to the backend so the SDK can
        // resolve pronouns + follow-ups. Compare-mode lines are skipped (they
        // don't have a single role) and the just-appended user line isn't
        // included — `message` is sent separately. Capping at 12 keeps the
        // wire payload bounded; older turns still surface through memory
        // semantic search.
        const priorMessages: ChatMessage[] = chat
          .filter(
            (line): line is Extract<ChatLine, { role: "user" | "agent" }> =>
              line.role === "user" || line.role === "agent",
          )
          .slice(-12)
          .map((line) => ({ role: line.role, content: line.text }));
        const result = await api.chat(agentId, message, priorMessages);
        setChat((prev) => [
          ...prev,
          {
            role: "agent",
            text: result.response,
            ts: new Date().toISOString(),
            informed: {
              memories: result.memories_used_snippets ?? [],
              directives: result.directives_used ?? [],
            },
          },
        ]);
      }
    } catch (error) {
      if (error instanceof TierError) {
        setTierError(error);
      } else if (error instanceof SessionStateError) {
        // Surface the server-confirmed end-state immediately rather than
        // waiting for the next 5-second poll tick — keeps the chat input
        // from sticking around after the user is gated.
        setSessionState({
          agent_id: error.body.agent_id,
          state: error.body.error,
          started_at: error.body.started_at,
          expires_at: error.body.expires_at,
          tokens_used: error.body.tokens_used,
          token_cap: error.body.token_cap,
          session_ttl_minutes: sessionTtl,
        });
      } else {
        const text = error instanceof Error ? error.message : String(error);
        setChat((prev) => [
          ...prev,
          { role: "agent", text: `[error] ${text}`, ts: new Date().toISOString() },
        ]);
      }
    } finally {
      setSending(false);
    }
  };

  const onSend = (event: React.FormEvent): void => {
    event.preventDefault();
    void sendMessage(draft.trim());
  };

  const onDelete = async (): Promise<void> => {
    if (!detail) return;
    const confirmed = window.confirm(
      `Delete "${detail.name}"? This removes the agent's directives and memory database. This cannot be undone.`,
    );
    if (!confirmed) return;
    setDeleting(true);
    try {
      await api.deleteAgent(agentId);
      const agents = await api.listAgents();
      setAgents(agents);
      navigate("/", { replace: true });
    } catch (err) {
      console.error("studio: delete failed", err);
      setDeleting(false);
    }
  };

  const onDream = async (): Promise<void> => {
    dismissDreamHint();
    setDreaming(true);
    try {
      await api.triggerDream(agentId);
    } catch (error) {
      if (error instanceof TierError) {
        setTierError(error);
      } else {
        console.error("studio: dream trigger failed", error);
      }
    } finally {
      setDreaming(false);
    }
  };

  const onSearchMemories = async (event: React.FormEvent): Promise<void> => {
    event.preventDefault();
    const q = memoryQuery.trim();
    if (!q) {
      setMemories([]);
      return;
    }
    setMemoriesLoading(true);
    setMemoriesError(null);
    try {
      const result = await api.searchMemories(agentId, { query: q, limit: 50 });
      setMemories(result as MemorySearchHit[]);
    } catch (err) {
      setMemoriesError(err instanceof Error ? err.message : String(err));
    } finally {
      setMemoriesLoading(false);
    }
  };

  if (!detail) {
    return <div className="flex h-full items-center justify-center text-zinc-500">Loading…</div>;
  }

  const sidePaneNode = (
    <>
      <header className="flex items-center justify-between border-b border-zinc-800 px-2 py-2">
        <div className="flex items-center gap-1">
          <PaneTab
            active={sidePane === "cognition"}
            onClick={() => setSidePane("cognition")}
            icon={<Activity className="h-3.5 w-3.5" />}
            label={`Cognition · ${wsState}`}
          />
          <PaneTab
            active={sidePane === "memories"}
            onClick={() => setSidePane("memories")}
            icon={<Database className="h-3.5 w-3.5" />}
            label="Memories"
          />
          <PaneTab
            active={sidePane === "insights"}
            onClick={() => setSidePane("insights")}
            icon={<Lightbulb className="h-3.5 w-3.5" />}
            label="Insights"
          />
        </div>
        <div className="flex items-center gap-1">
          {sidePane === "cognition" && (
            <button
              type="button"
              onClick={() => clearCognition(agentId)}
              title="Clear stream"
              className="px-2 text-zinc-500 hover:text-zinc-200"
            >
              <Trash2 className="h-3.5 w-3.5" />
            </button>
          )}
          <button
            type="button"
            onClick={() => setPaneOpen(false)}
            className="rounded-md p-1 text-zinc-500 hover:text-zinc-200 lg:hidden"
            aria-label="Close pane"
          >
            <X className="h-4 w-4" />
          </button>
        </div>
      </header>
      {sidePane === "cognition" && (
        <>
          {(wsState === "lost" || wsState === "closed") && (
            <WsReconnectBanner
              state={wsState}
              onRetry={() => setWsConnectKey((k) => k + 1)}
            />
          )}
          <CognitionStream events={cognition} />
        </>
      )}
      {sidePane === "memories" && (
        <MemoryBrowser
          agentId={agentId}
          query={memoryQuery}
          setQuery={setMemoryQuery}
          onSearch={onSearchMemories}
          loading={memoriesLoading}
          error={memoriesError}
          memories={memories}
        />
      )}
      {sidePane === "insights" && (
        <InsightsPane
          agentId={agentId}
          tab={insightsTab}
          setTab={setInsightsTab}
          cognition={cognition}
        />
      )}
    </>
  );

  return (
    <div className="relative grid h-full grid-cols-1 lg:grid-cols-[1fr_360px]">
      <section className="flex h-full min-h-0 flex-col">
        <header className="flex flex-wrap items-center justify-between gap-2 border-b border-zinc-800 bg-zinc-900/40 px-4 py-3 sm:px-6">
          <div className="min-w-0">
            <h1 className="truncate text-base font-semibold text-zinc-100">{detail.name}</h1>
            <p className="truncate text-xs text-zinc-500">
              {detail.archetype} · {detail.llm_provider} · {detail.storage_kind}
            </p>
          </div>
          <div className="flex items-center gap-2">
            <div className="relative">
              <button
                type="button"
                onClick={onDream}
                disabled={dreaming}
                className="flex min-h-[36px] items-center gap-1 rounded-md border border-violet-700/40 bg-violet-700/10 px-3 py-1.5 text-xs text-violet-200 hover:bg-violet-700/20 disabled:opacity-50"
              >
                <Sparkles className="h-3.5 w-3.5" />
                {dreaming ? "Dreaming…" : "Dream now"}
              </button>
              {showDreamHint && <DreamHint onDismiss={dismissDreamHint} />}
            </div>
            {!hideCrud && (
              <button
                type="button"
                onClick={onDelete}
                disabled={deleting}
                title="Delete agent"
                className="flex min-h-[36px] items-center gap-1 rounded-md border border-red-700/40 bg-red-700/10 px-3 py-1.5 text-xs text-red-200 hover:bg-red-700/20 disabled:opacity-50"
              >
                <Trash className="h-3.5 w-3.5" />
                {deleting ? "Deleting…" : "Delete"}
              </button>
            )}
          </div>
        </header>

        {sessionStateName !== "active" ? (
          <div className="flex-1 overflow-y-auto">
            <SessionEndedView state={sessionStateName} />
          </div>
        ) : (
          <ChatStream
            chat={chat}
            sending={sending}
            starters={detail.conversation_starters ?? []}
            onPickStarter={(text) => setDraft(text)}
          />
        )}

        <form
          onSubmit={onSend}
          className={`border-t border-zinc-800 bg-zinc-900/40 px-4 py-3 sm:px-6 ${
            sessionStateName !== "active" ? "hidden" : ""
          }`}
        >
          <div className="mb-2 flex items-center justify-between gap-2">
            <label className="flex items-center gap-2 text-xs text-zinc-400">
              <button
                type="button"
                role="switch"
                aria-checked={compareMode}
                onClick={() => setCompareMode((v) => !v)}
                className={`flex items-center gap-1.5 rounded-full border px-2.5 py-1 transition ${
                  compareMode
                    ? "border-emerald-600 bg-emerald-900/20 text-emerald-100"
                    : "border-zinc-700 bg-zinc-900/40 text-zinc-300 hover:border-zinc-600"
                }`}
              >
                <Layers className="h-3.5 w-3.5" />
                Compare mode
              </button>
              <span className="hidden text-zinc-500 sm:inline">
                {compareMode
                  ? "Side-by-side: baseline · memory · wisdom"
                  : "Single grounded reply"}
              </span>
            </label>
          </div>
          <div className="flex items-center gap-2">
            <input
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              placeholder={compareMode ? "Ask once — see all three answers…" : "Message your agent…"}
              className="flex-1 rounded-md border border-zinc-700 bg-zinc-950 px-3 py-2 text-sm text-zinc-100 focus:border-emerald-500 focus:outline-none"
            />
            <button
              type="submit"
              disabled={sending || !draft.trim()}
              className="flex h-11 min-w-[64px] items-center justify-center gap-1 rounded-md bg-emerald-600 px-3 text-sm font-medium text-emerald-50 hover:bg-emerald-500 disabled:opacity-50"
              aria-label="Send"
            >
              <Send className="h-4 w-4" />
              <span className="hidden sm:inline">Send</span>
            </button>
          </div>
        </form>
      </section>

      {/* Desktop: side pane shares the grid. Hidden under lg, where it's
          revealed via a slide-up drawer triggered by the FAB below. */}
      <aside className="hidden h-full min-h-0 flex-col border-l border-zinc-800 bg-zinc-900/40 lg:flex">
        {sidePaneNode}
      </aside>

      {/* Mobile FAB: opens the side pane drawer. Tucked above the input so
          it doesn't cover the chat scroll. */}
      <button
        type="button"
        onClick={() => setPaneOpen(true)}
        className="fixed bottom-20 right-4 z-30 flex h-12 w-12 items-center justify-center rounded-full border border-zinc-700 bg-zinc-900/90 text-zinc-200 shadow-lg hover:bg-zinc-800 lg:hidden"
        aria-label="Open cognition / memory pane"
      >
        <PanelRightOpen className="h-5 w-5" />
      </button>

      {paneOpen && (
        <div
          className="fixed inset-0 z-40 lg:hidden"
          role="dialog"
          aria-modal="true"
          onClick={() => setPaneOpen(false)}
        >
          <div className="absolute inset-0 bg-black/60" />
          <aside
            onClick={(e) => e.stopPropagation()}
            className="absolute inset-y-0 right-0 flex w-full max-w-md flex-col border-l border-zinc-800 bg-zinc-900"
          >
            {sidePaneNode}
          </aside>
        </div>
      )}

      {/* Floating memory minimap. Always rendered (md+ only); shows an empty
          state until the agent captures its first memory. Hidden once the
          session ends so the SessionEndedView isn't competing with it. */}
      {sessionStateName === "active" && <MemoryMapOverlay nodes={mapNodes} />}

      {tierError && <TierModal error={tierError} onDismiss={() => setTierError(null)} />}
    </div>
  );
}

function TierModal(props: { error: TierError; onDismiss: () => void }): JSX.Element {
  const { body } = props.error;
  const isCap = body.error === "cap_reached";
  const title = isCap
    ? capTitle(body.cap_kind)
    : `${body.feature ?? "This feature"} requires the ${body.required_tier ?? "Pro"} tier`;
  const detail = isCap ? capDetail(body) : (body.message ?? "");

  return (
    <div
      role="dialog"
      aria-modal="true"
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 px-4"
      onClick={props.onDismiss}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        className="w-full max-w-md rounded-xl border border-zinc-700 bg-zinc-900 p-6 shadow-2xl"
      >
        <header className="mb-3 flex items-start justify-between gap-3">
          <div className="flex items-center gap-2">
            <Lock className="h-4 w-4 text-amber-400" />
            <h2 className="text-base font-semibold text-zinc-100">{title}</h2>
          </div>
          <button
            type="button"
            onClick={props.onDismiss}
            className="text-zinc-500 hover:text-zinc-200"
            aria-label="Dismiss"
          >
            <X className="h-4 w-4" />
          </button>
        </header>
        <p className="text-sm text-zinc-300">{detail}</p>
        <div className="mt-5 flex items-center justify-end gap-2">
          <button
            type="button"
            onClick={props.onDismiss}
            className="rounded-md border border-zinc-700 px-3 py-1.5 text-sm text-zinc-300 hover:border-zinc-600"
          >
            Close
          </button>
          {body.upgrade_url && (
            <a
              href={body.upgrade_url}
              target="_blank"
              rel="noreferrer"
              className="rounded-md bg-emerald-600 px-3 py-1.5 text-sm font-medium text-emerald-50 hover:bg-emerald-500"
            >
              Learn more
            </a>
          )}
        </div>
      </div>
    </div>
  );
}

function capTitle(kind: "agents" | "memories" | "messages_30d"): string {
  switch (kind) {
    case "agents":
      return "Agent limit reached";
    case "memories":
      return "Memory limit reached";
    case "messages_30d":
      return "Monthly message limit reached";
  }
}

function capDetail(body: {
  cap_kind: "agents" | "memories" | "messages_30d";
  current: number;
  limit: number;
  reset_at: string | null;
}): string {
  const base = `${body.current.toLocaleString()} of ${body.limit.toLocaleString()} used.`;
  if (body.cap_kind === "messages_30d" && body.reset_at) {
    return `${base} Resets on ${new Date(body.reset_at).toLocaleString()}.`;
  }
  return base;
}

function ChatStream(props: {
  chat: ChatLine[];
  sending: boolean;
  starters: string[];
  onPickStarter: (text: string) => void;
}): JSX.Element {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (ref.current) ref.current.scrollTop = ref.current.scrollHeight;
  }, [props.chat, props.sending]);

  const showStarters = props.chat.length === 0 && props.starters.length > 0 && !props.sending;

  return (
    <div ref={ref} className="flex-1 space-y-4 overflow-y-auto px-6 py-6">
      {props.chat.length === 0 && (
        <div className="text-sm text-zinc-500">
          Start chatting. The agent captures every turn as a memory.
        </div>
      )}
      {showStarters && (
        <ul className="flex flex-wrap gap-2">
          {props.starters.map((starter, i) => (
            <li key={`${i}-${starter}`}>
              <button
                type="button"
                onClick={() => props.onPickStarter(starter)}
                className="rounded-full border border-zinc-700 bg-zinc-900/60 px-3 py-1.5 text-xs text-zinc-200 transition hover:border-emerald-600 hover:bg-emerald-900/20 hover:text-emerald-100"
              >
                {starter}
              </button>
            </li>
          ))}
        </ul>
      )}
      {props.chat.map((line, i) => {
        if (line.role === "compare") {
          return <CompareRow key={i} result={line.result} />;
        }
        if (line.role === "user") {
          return (
            <div key={i} className="flex justify-end">
              <div className="max-w-[80%] whitespace-pre-wrap rounded-lg bg-emerald-700/30 px-4 py-2 text-sm text-emerald-50">
                {line.text}
              </div>
            </div>
          );
        }
        return <AgentMessageRow key={i} text={line.text} informed={line.informed} />;
      })}
      {props.sending && (
        <div className="flex justify-start text-xs text-zinc-500">…thinking</div>
      )}
    </div>
  );
}

// Floating popover anchored to the Dream button. Renders absolutely so it
// can drape below the header without disturbing layout. Caller controls
// visibility — this component only renders the chrome and the dismiss
// button. Forkable: it's a generic onboarding pattern, not demo-specific.
function DreamHint(props: { onDismiss: () => void }): JSX.Element {
  return (
    <div
      role="tooltip"
      className="absolute right-0 top-[calc(100%+8px)] z-20 w-64 rounded-md border border-violet-600/50 bg-zinc-950/95 p-3 text-xs text-zinc-200 shadow-xl"
    >
      <div className="absolute -top-1.5 right-6 h-3 w-3 rotate-45 border-l border-t border-violet-600/50 bg-zinc-950" />
      <div className="flex items-start gap-2">
        <Sparkles className="mt-0.5 h-3.5 w-3.5 shrink-0 text-violet-300" />
        <p className="flex-1 leading-snug">
          Try a <span className="text-violet-200">dream cycle</span> — the agent
          consolidates this conversation into long-term memory and may surface a new
          directive.
        </p>
        <button
          type="button"
          onClick={props.onDismiss}
          className="text-zinc-500 hover:text-zinc-200"
          aria-label="Dismiss hint"
        >
          <X className="h-3.5 w-3.5" />
        </button>
      </div>
    </div>
  );
}

// Agent message: markdown bubble + optional "what informed this answer"
// disclosure. The disclosure is the in-chat surface for the same memories
// and directives the SDK Compare endpoint reports — letting visitors see
// the grounding without flipping the Compare-mode toggle.
function AgentMessageRow(props: { text: string; informed?: InformedBy }): JSX.Element {
  const [open, setOpen] = useState(false);
  const memCount = props.informed?.memories.length ?? 0;
  const dirCount = props.informed?.directives.length ?? 0;
  const hasAny = memCount + dirCount > 0;

  return (
    <div className="flex justify-start">
      <div className="flex max-w-[80%] flex-col gap-1">
        <div className="rounded-lg bg-zinc-800 px-4 py-2 text-zinc-100">
          <ChatMarkdown text={props.text} />
        </div>
        {hasAny && (
          <div className="text-[11px]">
            <button
              type="button"
              onClick={() => setOpen((v) => !v)}
              className="flex items-center gap-1 text-zinc-500 transition hover:text-zinc-300"
              aria-expanded={open}
            >
              {open ? (
                <ChevronDown className="h-3 w-3" />
              ) : (
                <ChevronRight className="h-3 w-3" />
              )}
              <span>
                Informed by {memCount} {memCount === 1 ? "memory" : "memories"} ·{" "}
                {dirCount} {dirCount === 1 ? "directive" : "directives"}
              </span>
            </button>
            {open && (
              <div className="mt-2 space-y-2 rounded-md border border-zinc-800 bg-zinc-950/60 p-2 text-zinc-300">
                {memCount > 0 && (
                  <div>
                    <p className="mb-1 text-[10px] uppercase tracking-wider text-emerald-400">
                      Memories
                    </p>
                    <ul className="space-y-1">
                      {props.informed!.memories.map((m, idx) => (
                        <li key={idx} className="border-l-2 border-emerald-700/40 pl-2 leading-snug">
                          {m}
                        </li>
                      ))}
                    </ul>
                  </div>
                )}
                {dirCount > 0 && (
                  <div>
                    <p className="mb-1 text-[10px] uppercase tracking-wider text-amber-400">
                      Directives
                    </p>
                    <ul className="space-y-1">
                      {props.informed!.directives.map((d, idx) => (
                        <li key={idx} className="border-l-2 border-amber-700/40 pl-2 leading-snug">
                          {d}
                        </li>
                      ))}
                    </ul>
                  </div>
                )}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

// Stacked under md, three-column grid at md+. The SDK ships a similar
// component, but its grid is fixed `grid-cols-3`, which breaks the v0.5
// mobile-responsive guarantee — so Studio renders its own variant.
function CompareRow(props: { result: ChatCompareResponse }): JSX.Element {
  const { result } = props;
  return (
    <div className="rounded-lg border border-zinc-800 bg-zinc-900/40 p-3">
      <p className="mb-3 text-[11px] uppercase tracking-wider text-zinc-500">
        Compare · {result.memory_count} memories · {result.directive_count} directives
      </p>
      <div className="grid grid-cols-1 gap-3 md:grid-cols-3">
        <CompareColumn
          label="Baseline"
          tone="zinc"
          hint="No context"
          answer={result.baseline_answer}
          latencyMs={result.baseline_latency_ms}
        />
        <CompareColumn
          label="Memory"
          tone="amber"
          hint="Past interactions"
          answer={result.memory_answer}
          latencyMs={result.memory_latency_ms}
        />
        <CompareColumn
          label="Wisdom"
          tone="emerald"
          hint="Memory + directives"
          answer={result.wisdom_answer}
          latencyMs={result.wisdom_latency_ms}
        />
      </div>
    </div>
  );
}

const COMPARE_TONES = {
  zinc: "border-zinc-700 bg-zinc-950 text-zinc-200",
  amber: "border-amber-700/40 bg-amber-900/10 text-amber-100",
  emerald: "border-emerald-700/40 bg-emerald-900/10 text-emerald-100",
} as const;

function CompareColumn(props: {
  label: string;
  tone: keyof typeof COMPARE_TONES;
  hint: string;
  answer: string | null;
  latencyMs: number | null;
}): JSX.Element {
  return (
    <div className={`flex h-full flex-col rounded-md border p-3 ${COMPARE_TONES[props.tone]}`}>
      <header className="mb-2 flex items-center justify-between text-[11px] uppercase tracking-wider">
        <span>{props.label}</span>
        {props.latencyMs !== null && (
          <span className="font-mono text-[10px] opacity-60">{props.latencyMs} ms</span>
        )}
      </header>
      <p className="mb-2 text-[11px] opacity-70">{props.hint}</p>
      <p className="whitespace-pre-wrap text-sm">
        {props.answer ?? <span className="opacity-50">(no answer)</span>}
      </p>
    </div>
  );
}

// Inline notice for the cognition pane when the WS is closed or has
// exhausted its auto-reconnect budget. "lost" indicates the auto-retry
// loop gave up after WS_BACKOFF_MS attempts; "closed" means the backend
// closed with an intentional code (4404 / 4500 / 1000) and we deliberately
// did not retry. Either way the visitor gets a single-click recovery path.
function WsReconnectBanner(props: {
  state: Extract<WsState, "lost" | "closed">;
  onRetry: () => void;
}): JSX.Element {
  const message =
    props.state === "lost"
      ? "Connection lost. Cognition events paused."
      : "Connection closed by the server.";
  return (
    <div className="flex items-center justify-between gap-2 border-b border-amber-700/40 bg-amber-900/10 px-3 py-2 text-[11px] text-amber-200">
      <span>{message}</span>
      <button
        type="button"
        onClick={props.onRetry}
        className="rounded border border-amber-700/60 bg-amber-900/20 px-2 py-0.5 text-amber-100 hover:bg-amber-900/40"
      >
        Reconnect
      </button>
    </div>
  );
}

function CognitionStream(props: { events: CognitionEvent[] }): JSX.Element {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (ref.current) ref.current.scrollTop = ref.current.scrollHeight;
  }, [props.events]);

  return (
    <div ref={ref} className="flex-1 overflow-y-auto px-3 py-3 font-mono text-[11px]">
      {props.events.length === 0 ? (
        <div className="text-zinc-600">Waiting for cognition events…</div>
      ) : (
        <ul className="space-y-1">
          {props.events.map((event, i) => (
            <li key={i} className="rounded border border-zinc-800 bg-zinc-950 px-2 py-1">
              <div className="flex items-center justify-between">
                <span className={eventColor(event.type)}>{event.type}</span>
                <span className="text-zinc-600">{formatTime(event.timestamp)}</span>
              </div>
              {Object.keys(event.data).length > 0 && (
                <pre className="mt-1 overflow-hidden whitespace-pre-wrap break-all text-zinc-500">
                  {summarize(event.data)}
                </pre>
              )}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function PaneTab(props: {
  active: boolean;
  onClick: () => void;
  icon: React.ReactNode;
  label: string;
}): JSX.Element {
  return (
    <button
      type="button"
      onClick={props.onClick}
      className={`flex items-center gap-1.5 rounded-md px-2 py-1 text-[11px] uppercase tracking-wider transition ${
        props.active
          ? "bg-zinc-800 text-zinc-100"
          : "text-zinc-500 hover:bg-zinc-800/60 hover:text-zinc-200"
      }`}
    >
      {props.icon}
      {props.label}
    </button>
  );
}

function MemoryBrowser(props: {
  agentId: string;
  query: string;
  setQuery: (q: string) => void;
  onSearch: (e: React.FormEvent) => void | Promise<void>;
  loading: boolean;
  error: string | null;
  memories: MemorySearchHit[];
}): JSX.Element {
  return (
    <div className="flex h-full flex-col">
      <form onSubmit={props.onSearch} className="border-b border-zinc-800 px-3 py-2">
        <input
          value={props.query}
          onChange={(e) => props.setQuery(e.target.value)}
          placeholder="Search memories…"
          className="w-full rounded-md border border-zinc-700 bg-zinc-950 px-2 py-1.5 text-xs text-zinc-100 focus:border-emerald-500 focus:outline-none"
        />
      </form>
      <div className="flex-1 overflow-y-auto px-3 py-3 font-mono text-[11px]">
        {props.error && (
          <div className="rounded border border-red-500/40 bg-red-500/10 px-2 py-1 text-red-300">
            {props.error}
          </div>
        )}
        {props.loading && <div className="text-zinc-500">Searching…</div>}
        {!props.loading && !props.error && props.memories.length === 0 && (
          <div className="text-zinc-600">
            {props.query.trim()
              ? "No matches."
              : "Type a query and press enter to search this agent's memories."}
          </div>
        )}
        <ul className="space-y-1">
          {props.memories.map((mem, i) => (
            <MemoryRow key={mem.id ?? i} agentId={props.agentId} mem={mem} />
          ))}
        </ul>
      </div>
    </div>
  );
}

// One memory row + the "Share to workspace" affordance. The share button is
// always visible — when the workspace is unavailable the API call surfaces
// the structured error and we render a one-line CTA inline.
function MemoryRow(props: { agentId: string; mem: MemorySearchHit }): JSX.Element {
  const { mem } = props;
  const [sharing, setSharing] = useState(false);
  const [status, setStatus] = useState<string | null>(null);

  async function share(): Promise<void> {
    if (!mem.id) {
      setStatus("Cannot share: memory has no id.");
      return;
    }
    setSharing(true);
    setStatus(null);
    try {
      const result = await api.shareMemory(props.agentId, mem.id, { visibility: "TEAM" });
      setStatus(`Shared as ${result.shared_memory_id}`);
    } catch (err) {
      setStatus(err instanceof Error ? err.message : String(err));
    } finally {
      setSharing(false);
    }
  }

  return (
    <li className="rounded border border-zinc-800 bg-zinc-950 px-2 py-1.5">
      <div className="flex items-center justify-between">
        <span className="text-emerald-300">{mem.event_type ?? "memory"}</span>
        <span className="text-zinc-600">
          {mem.similarity !== undefined && `sim ${mem.similarity.toFixed(2)} · `}
          {mem.created_at ? formatTime(mem.created_at) : ""}
        </span>
      </div>
      <pre className="mt-1 whitespace-pre-wrap break-all text-zinc-400">
        {summarizeMemory(mem.content ?? {})}
      </pre>
      <div className="mt-1 flex items-center justify-between gap-2">
        <button
          type="button"
          onClick={share}
          disabled={sharing || !mem.id}
          className="rounded border border-emerald-700/40 bg-emerald-700/10 px-2 py-0.5 text-[10px] text-emerald-200 hover:bg-emerald-700/20 disabled:opacity-50"
        >
          {sharing ? "Sharing…" : "Share to workspace"}
        </button>
        {status && (
          <span className="truncate text-[10px] text-zinc-500" title={status}>
            {status}
          </span>
        )}
      </div>
    </li>
  );
}

// Insights pane: thin wrapper that owns the sub-tab nav and dispatches to
// one of four panel components. Each panel fetches its own data from the
// SDK dashboard routes mounted at /agents/{id}/api/*. Cognition is threaded
// through so panels can refresh when relevant events arrive on the WS
// (e.g., a new journal after a dream cycle completes).
function InsightsPane(props: {
  agentId: string;
  tab: InsightsTab;
  setTab: (tab: InsightsTab) => void;
  cognition: CognitionEvent[];
}): JSX.Element {
  const tabs: { id: InsightsTab; label: string }[] = [
    { id: "directives", label: "Directives" },
    { id: "journals", label: "Journals" },
    { id: "dreams", label: "Dreams" },
    { id: "critic", label: "Critic" },
  ];
  return (
    <div className="flex h-full min-h-0 flex-col">
      <nav className="flex border-b border-zinc-800 bg-zinc-950/40 px-2">
        {tabs.map((t) => (
          <button
            key={t.id}
            type="button"
            onClick={() => props.setTab(t.id)}
            className={`px-3 py-1.5 text-[11px] uppercase tracking-wider transition ${
              props.tab === t.id
                ? "border-b-2 border-emerald-500 text-zinc-100"
                : "text-zinc-500 hover:text-zinc-200"
            }`}
          >
            {t.label}
          </button>
        ))}
      </nav>
      <div className="min-h-0 flex-1">
        {props.tab === "directives" && (
          <DirectivesPanel agentId={props.agentId} cognition={props.cognition} />
        )}
        {props.tab === "journals" && (
          <JournalsPanel agentId={props.agentId} cognition={props.cognition} />
        )}
        {props.tab === "dreams" && (
          <DreamsPanel agentId={props.agentId} cognition={props.cognition} />
        )}
        {props.tab === "critic" && <CriticPanel agentId={props.agentId} />}
      </div>
    </div>
  );
}

function summarizeMemory(content: Record<string, unknown>): string {
  if ("text" in content && typeof content.text === "string") return content.text;
  if ("role" in content && "text" in content) return `${content.role}: ${content.text}`;
  return JSON.stringify(content);
}

function eventColor(name: string): string {
  if (name.startsWith("memory.")) return "text-emerald-300";
  if (name.startsWith("directive.")) return "text-amber-300";
  if (name.startsWith("dream.")) return "text-violet-300";
  if (name.startsWith("critic.")) return "text-rose-300";
  if (name.startsWith("journal.")) return "text-sky-300";
  return "text-zinc-300";
}

function formatTime(iso: string): string {
  return new Date(iso).toLocaleTimeString([], { hour12: false });
}

function summarize(data: Record<string, unknown>): string {
  const skipKeys = new Set(["event_id"]);
  const entries = Object.entries(data)
    .filter(([k]) => !skipKeys.has(k))
    .slice(0, 3);
  return entries.map(([k, v]) => `${k}=${truncate(v)}`).join("  ");
}

function truncate(value: unknown): string {
  const s = typeof value === "string" ? value : JSON.stringify(value);
  return s.length > 60 ? `${s.slice(0, 57)}…` : s;
}
