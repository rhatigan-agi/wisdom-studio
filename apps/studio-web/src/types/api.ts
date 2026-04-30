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

export interface ChatRequest {
  message: string;
  capture?: boolean;
}

export interface ChatResponse {
  response: string;
  memories_used: number;
  composed_chars: number;
  truncated_layers: string[];
  snapshot_id: string;
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
