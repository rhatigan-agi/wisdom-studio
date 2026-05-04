// TypeScript mirrors of `studio_api.schemas`. Keep in lockstep with the
// Studio control-plane surface. Per-agent operations (memory, dreams,
// directives, status, …) hit the SDK dashboard routes mounted under
// `/agents/{id}/api/...`, whose shapes are owned by the SDK.

export type LLMProvider = "anthropic" | "openai" | "gemini" | "ollama" | "litellm";
export type StorageKind = "sqlite" | "postgres";
export type Archetype =
  | "balanced"
  | "research"
  | "coding_assistant"
  | "consumer_support"
  | "strategic_advisors"
  | "lightweight_local";

export interface LockedLLM {
  provider: LLMProvider;
  model: string | null;
}

export interface StudioConfig {
  // User-saved (round-trip through PUT /api/config)
  license_key: string | null;
  provider_keys: Partial<Record<LLMProvider, string>>;
  initialized: boolean;
  // Runtime-only (sourced from server env on every load; not writable)
  banner_html: string | null;
  session_ttl_minutes: number | null;
  docs_url: string | null;
  signup_url: string | null;
  locked_llm: LockedLLM | null;
  hide_settings: boolean;
  hide_agent_crud: boolean;
  // Ephemeral / try-it-now posture. When `ephemeral` is true the SPA hides
  // Save/Export/Download affordances and the Settings page is suppressed
  // (the server forces `hide_settings`). `token_cap_per_session` and the
  // session_end_cta_* fields shape the session-ended view.
  ephemeral: boolean;
  token_cap_per_session: number | null;
  session_end_cta_href: string | null;
  session_end_cta_label: string | null;
}

export interface StudioConfigUpdate {
  license_key?: string | null;
  provider_keys?: Partial<Record<LLMProvider, string>>;
}

export interface AgentCreate {
  name: string;
  role?: string;
  archetype: Archetype;
  persona?: string;
  directives?: string[];
  llm_provider: LLMProvider;
  llm_model?: string | null;
  llm_tier?: "sota" | "high" | "mid" | "low" | null;
  storage_kind?: StorageKind;
  storage_url?: string | null;
  conversation_starters?: string[];
}

export interface AgentSummary {
  agent_id: string;
  name: string;
  role: string;
  archetype: Archetype;
  llm_provider: LLMProvider;
  storage_kind: StorageKind;
  created_at: string;
  last_active_at: string | null;
}

export interface AgentDetail extends AgentSummary {
  persona: string;
  directives: string[];
  llm_model: string | null;
  storage_url: string | null;
  conversation_starters: string[];
}

export interface ChatMessage {
  role: "user" | "agent";
  content: string;
}

export interface ChatRequest {
  message: string;
  capture?: boolean;
  // Recent prior turns. Forwarded to the SDK's `respond_loop` as
  // `session_context` so follow-ups resolve against actual prior turns
  // instead of being treated as standalone prompts.
  prior_messages?: ChatMessage[];
}

export interface ChatResponse {
  response: string;
  memories_used: number;
  composed_chars: number;
  truncated_layers: string[];
  snapshot_id: string;
  // Studio gathers these AFTER respond_loop() returns so the SPA can show
  // "what informed this answer" without depending on SDK-internal state.
  // Empty when retrieval fails (logged server-side, swallowed) or when the
  // agent has no relevant memories / no active directives.
  memories_used_snippets: string[];
  directives_used: string[];
}

// SDK dashboard `/api/chat` (mounted at /agents/{id}/api/chat). The SDK route
// answers a single question across up to three cognitive layers — baseline
// (no context), memory-only, and full wisdom (memory + directives) — so the
// contrast itself is the demo. Studio renders the response in a responsive
// grid so it works on mobile, where the SDK's bundled ChatComparison.tsx
// uses fixed three-column grids.
export type ChatCompareMode = "baseline" | "memory" | "compare" | "all";

export interface ChatCompareRequest {
  question: string;
  mode: ChatCompareMode;
}

export interface ChatCompareResponse {
  question: string;
  mode: ChatCompareMode;
  baseline_answer: string | null;
  baseline_latency_ms: number | null;
  memory_answer: string | null;
  memory_latency_ms: number | null;
  wisdom_answer: string | null;
  wisdom_latency_ms: number | null;
  memory_count: number;
  directive_count: number;
  memories_used: string[];
  directives_used: string[];
}

// SDK WebSocketHub event shape. The hub flushes batches on a 100 ms timer,
// so the server sends `CognitionEvent[]` per WS message. Studio injects
// `agent_id` at receive time from the URL since the SDK hub does not embed
// it (each hub instance is per-agent already).
export interface CognitionEvent {
  agent_id: string;
  type: string;
  timestamp: string;
  data: Record<string, unknown>;
}

export interface ExampleSummary {
  slug: string;
  name: string;
  role: string;
  archetype: Archetype;
  persona_preview: string;
  directive_count: number;
}

// SDK memory router returns a flat list (no `{memories, total}` wrapper).
export type MemoryEntry = Record<string, unknown>;

// Live per-agent session state, returned by GET /api/agents/{id}/session and
// also baked into the 410 body when /chat is gated.
export type SessionStateName = "active" | "session_ended" | "token_cap_reached";

export interface SessionState {
  agent_id: string;
  state: SessionStateName;
  started_at: string | null;
  expires_at: string | null;
  tokens_used: number;
  token_cap: number | null;
  session_ttl_minutes: number | null;
}

// --- Multi-agent workspace (wisdom-layer 1.2.0+) ---------------------------
// All workspace surfaces are license-gated; the SPA reads `available` first
// and renders an upgrade CTA when false. The reason field discriminates the
// failure modes so callers can branch without reading `message`.

export type WorkspaceUnavailableReason =
  | "license_missing"
  | "enterprise_required"
  | "init_failed"
  | "uninitialized";

export interface WorkspaceStatusUnavailable {
  available: false;
  reason: WorkspaceUnavailableReason;
  feature: string | null;
  required_tier: string | null;
  upgrade_url: string | null;
  message: string;
}

export interface WorkspaceStatusAvailable {
  available: true;
  workspace_id: string;
  name: string;
  agent_count: number;
  initialized_at: string | null;
}

export type WorkspaceStatus = WorkspaceStatusAvailable | WorkspaceStatusUnavailable;

export interface WorkspaceAgentRecord {
  agent_id: string;
  capabilities: string[];
  registered_at: string;
  last_seen_at: string | null;
  past_success_rate: number;
}

export type SharedMemoryVisibility = "PRIVATE" | "TEAM" | "PUBLIC";

export interface SharedMemory {
  id: string;
  workspace_id: string;
  contributor_id: string;
  source_memory_id: string;
  visibility: string; // wire format: enum repr (e.g. "Visibility.TEAM")
  content: string;
  reason: string;
  endorsement_count: number;
  contention_count: number;
  base_score: number;
  team_score: number;
  shared_at: string;
  archived_at: string | null;
}

export interface TeamInsight {
  id: string;
  workspace_id: string;
  content: string;
  synthesis_prompt_hash: string;
  contributor_count: number;
  dream_cycle_id: string | null;
  created_at: string;
  archived_at: string | null;
}

export interface ProvenanceContribution {
  shared_memory_id: string;
  contributor_agent_id: string;
  source_memory_id: string;
  shared_content: string;
  contribution_weight: number;
}

export interface TeamInsightProvenance {
  team_insight: TeamInsight;
  contributions: ProvenanceContribution[];
}

export type MessagePurpose = "question" | "information" | "coordination" | "handoff";

export interface AgentMessage {
  id: string;
  workspace_id: string;
  sender_id: string;
  recipient_id: string | null;
  broadcast_capability: string | null;
  content: string;
  purpose: string; // wire repr (e.g. "MessagePurpose.QUESTION")
  thread_id: string;
  in_reply_to: string | null;
  expects_reply: boolean;
  status: string;
  created_at: string;
  read_at: string | null;
  replied_at: string | null;
  is_broadcast: boolean;
}
