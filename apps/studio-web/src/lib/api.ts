import type {
  AgentCreate,
  AgentDetail,
  AgentSummary,
  ChatCompareMode,
  ChatCompareRequest,
  ChatCompareResponse,
  ChatMessage,
  ChatRequest,
  ChatResponse,
  ExampleSummary,
  MemoryEntry,
  SessionState,
  SessionStateName,
  StudioConfig,
  StudioConfigUpdate,
} from "../types/api";

// Cap kinds mirror `wisdom_layer.errors.CapKind` (SDK 1.1.0). Keep these in
// sync with the backend handler in `studio_api/main.py::handle_tier_restriction`.
export type CapKind = "agents" | "memories" | "messages_30d";

interface TierFeatureGate {
  error: "feature_gated";
  feature: string | null;
  required_tier: string | null;
  upgrade_url: string;
  message: string;
}

interface TierCapReached {
  error: "cap_reached";
  cap_kind: CapKind;
  current: number;
  limit: number;
  reset_at: string | null;
  upgrade_url: string;
  message: string;
}

export type TierErrorBody = TierFeatureGate | TierCapReached;

// Thrown when the API returns 402 (cap reached) or 403 with a tier-shaped
// body. Callers catch this to render an upgrade modal instead of a raw
// error string. Other 4xx/5xx responses still surface as plain `Error`.
export class TierError extends Error {
  readonly status: number;
  readonly body: TierErrorBody;

  constructor(status: number, body: TierErrorBody) {
    super(body.message);
    this.name = "TierError";
    this.status = status;
    this.body = body;
  }
}

function isTierBody(payload: unknown): payload is TierErrorBody {
  if (typeof payload !== "object" || payload === null) return false;
  const err = (payload as { error?: unknown }).error;
  return err === "feature_gated" || err === "cap_reached";
}

interface SessionEndedBody {
  error: SessionStateName;
  agent_id: string;
  tokens_used: number;
  token_cap: number | null;
  started_at: string | null;
  expires_at: string | null;
}

// Thrown when the server returns 410 because a kiosk / ephemeral session has
// either timed out (`session_ended`) or hit its token cap
// (`token_cap_reached`). The SPA renders the configured CTA in response;
// generic 410s without this shape still surface as plain `Error`.
export class SessionStateError extends Error {
  readonly status: number;
  readonly body: SessionEndedBody;

  constructor(body: SessionEndedBody) {
    super(body.error);
    this.name = "SessionStateError";
    this.status = 410;
    this.body = body;
  }
}

function isSessionEndedBody(payload: unknown): payload is SessionEndedBody {
  if (typeof payload !== "object" || payload === null) return false;
  const err = (payload as { error?: unknown }).error;
  return err === "session_ended" || err === "token_cap_reached";
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, {
    headers: { "content-type": "application/json", ...(init?.headers ?? {}) },
    ...init,
  });
  if (!response.ok) {
    // Tier-restriction responses arrive as 402 (cap) or 403 (feature gate)
    // with a structured JSON body. Anything else is a generic error string.
    if (response.status === 402 || response.status === 403) {
      try {
        const body = await response.clone().json();
        if (isTierBody(body)) throw new TierError(response.status, body);
      } catch (err) {
        if (err instanceof TierError) throw err;
        // Fall through to the generic path on JSON parse failure.
      }
    }
    // 410 with a session-ended shape is the kiosk / ephemeral end-state. The
    // SPA renders the configured CTA on this; non-shaped 410s fall through.
    if (response.status === 410) {
      try {
        const body = await response.clone().json();
        if (isSessionEndedBody(body)) throw new SessionStateError(body);
      } catch (err) {
        if (err instanceof SessionStateError) throw err;
      }
    }
    const message = await response.text();
    throw new Error(`${response.status} ${response.statusText}: ${message}`);
  }
  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}

// Studio's own control-plane API.
const studio = "/api";

// SDK dashboard routes mounted per-agent at /agents/{id}/api/...
const sdk = (agentId: string): string => `/agents/${agentId}/api`;

export const api = {
  health: (): Promise<{ status: string; version: string }> => request(`${studio}/health`),

  getConfig: (): Promise<StudioConfig> => request(`${studio}/config`),
  updateConfig: (update: StudioConfigUpdate): Promise<StudioConfig> =>
    request(`${studio}/config`, { method: "PUT", body: JSON.stringify(update) }),

  listAgents: (): Promise<AgentSummary[]> => request(`${studio}/agents`),
  getAgent: (id: string): Promise<AgentDetail> => request(`${studio}/agents/${id}`),
  createAgent: (spec: AgentCreate): Promise<AgentDetail> =>
    request(`${studio}/agents`, { method: "POST", body: JSON.stringify(spec) }),
  deleteAgent: (id: string): Promise<void> =>
    request(`${studio}/agents/${id}`, { method: "DELETE" }),

  listExamples: (): Promise<ExampleSummary[]> => request(`${studio}/examples`),
  getExample: (slug: string): Promise<AgentCreate> => request(`${studio}/examples/${slug}`),
  createAgentFromExample: (slug: string): Promise<AgentDetail> =>
    request(`${studio}/agents/from-example/${slug}`, { method: "POST" }),

  // Studio-owned chat endpoint — thin wrapper around SDK respond_loop().
  // `priorMessages` is the recent in-SPA chat history; the backend forwards
  // it as `session_context` so the agent can thread follow-ups across turns.
  chat: (
    id: string,
    message: string,
    priorMessages: ChatMessage[] = [],
  ): Promise<ChatResponse> =>
    request(`${studio}/agents/${id}/chat`, {
      method: "POST",
      body: JSON.stringify({
        message,
        prior_messages: priorMessages.length ? priorMessages : undefined,
      } satisfies ChatRequest),
    }),

  // SDK dashboard's compare endpoint — answers the same question across
  // baseline / memory-only / full-wisdom layers. Studio uses this for the
  // demo-mode toggle that makes the wisdom layer's contribution visible.
  chatCompare: (
    id: string,
    question: string,
    mode: ChatCompareMode = "all",
  ): Promise<ChatCompareResponse> =>
    request(`${sdk(id)}/chat`, {
      method: "POST",
      body: JSON.stringify({ question, mode } satisfies ChatCompareRequest),
    }),

  // --- SDK dashboard routes -------------------------------------------------

  searchMemories: (
    id: string,
    opts: { query: string; limit?: number },
  ): Promise<MemoryEntry[]> => {
    const params = new URLSearchParams({ query: opts.query });
    if (opts.limit) params.set("limit", String(opts.limit));
    return request(`${sdk(id)}/memory/search?${params.toString()}`);
  },

  captureMemory: (
    id: string,
    body: { event_type: string; content: Record<string, unknown>; emotional_intensity?: number },
  ): Promise<{ memory_id: string }> =>
    request(`${sdk(id)}/memory/capture`, {
      method: "POST",
      body: JSON.stringify(body),
    }),

  // Convenience: capture a batch sequentially. The SDK route is per-item.
  seed: async (
    id: string,
    memories: Array<{ event_type: string; content: Record<string, unknown> }>,
  ): Promise<{ captured: number }> => {
    let captured = 0;
    for (const mem of memories) {
      await api.captureMemory(id, mem);
      captured += 1;
    }
    return { captured };
  },

  triggerDream: (id: string): Promise<Record<string, unknown>> =>
    request(`${sdk(id)}/dreams/trigger`, { method: "POST" }),

  listDirectives: (id: string, includeInactive = false): Promise<Array<Record<string, unknown>>> =>
    request(`${sdk(id)}/directives?include_inactive=${includeInactive}`),

  getStatus: (id: string): Promise<Record<string, unknown>> => request(`${sdk(id)}/status`),

  // Live session lifecycle. Polled by the SessionTimer so the SPA stays in
  // sync with backend enforcement instead of trusting client wall-clock.
  getSessionState: (id: string): Promise<SessionState> =>
    request(`${studio}/agents/${id}/session`),
};
