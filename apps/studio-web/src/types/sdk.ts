// TypeScript mirrors of the SDK pydantic schemas served by the per-agent
// SDK sub-app at `/agents/{id}/api/...`. Source of truth is
// `wisdom_layer.types` (and the route modules under
// `wisdom_layer.dashboard.routes.*`) inside the installed SDK.
//
// These types are hand-written rather than codegen'd because the SDK is
// pinned to a stable major version and the surfaces below are small.
// When upgrading the `wisdom-layer` pin, re-verify these match by reading
// the corresponding pydantic models — drift is the most common bug here.
//
// Conventions:
//   - All `*_at` timestamps are ISO 8601 strings.
//   - Optional fields are `... | null` (matches pydantic `... | None`),
//     except where the SDK omits a field rather than serializing null.
//   - Snake-case is preserved on the wire; rename only at component
//     boundaries if needed.

// --- Directives ----------------------------------------------------------

// Mirrors `wisdom_layer.types.DirectiveStatus`.
//   provisional → active → permanent (always-applied) → inactive
export type DirectiveStatus = "active" | "provisional" | "permanent" | "inactive";

// Mirrors `wisdom_layer.types.Directive`.
export interface Directive {
  id: string;
  text: string;
  status: DirectiveStatus;
  // Reserved for future per-directive overrides; not user-settable in
  // SDK 1.x. Present in the wire shape so we keep it for round-tripping.
  priority: string;
  usage_count: number;
  created_at: string;
  last_used: string | null;
}

// Mirrors `wisdom_layer.types.DirectiveProposal`.
export interface DirectiveProposal {
  id: string;
  // "add", "modify", "remove"
  action: string;
  text: string;
  reasoning: string;
  // 0.0 – 1.0 confidence from the proposal pipeline (typically dreams).
  confidence: number;
  source_memory_ids: string[];
}

// --- Journals ------------------------------------------------------------

// Wire shape from `agent.journals.history()` (raw storage row, not a
// pydantic model in the SDK). Synthesized at the end of a dream cycle.
export interface JournalEntry {
  id: string;
  agent_id: string;
  content: string;
  memory_ids: string[];
  created_at: string;
}

// --- Dreams --------------------------------------------------------------

// Mirrors the dict returned by `GET /api/dreams/schedule/status` in
// `wisdom_layer.dashboard.routes.dreams`. Both fields are null on a
// fresh agent that has never run a cycle.
export interface DreamScheduleStatus {
  next_run: string | null;
  last_run: string | null;
}

// Per-phase cost row on a `DreamReport`. Mirrors
// `wisdom_layer.types.PhaseCost`.
export interface PhaseCost {
  phase: string;
  model: string;
  tokens_in: number;
  tokens_out: number;
  usd: number;
  duration_ms: number;
  calls: number;
}

// Mirrors `wisdom_layer.types.DreamReport`. The `cost_breakdown` /
// `total_*` fields are populated by the SDK's `/api/dreams/history`
// route (which enriches each cycle from the cost ledger); raw cycles
// from older deployments leave them at zero defaults.
export interface DreamReport {
  cycle_id: string;
  started_at: string;
  completed_at: string;
  phases_completed: string[];
  reconsolidated: number;
  new_insights: number;
  decayed: number;
  directives_proposed: number;
  journal_entry_id: string | null;
  cost_breakdown: PhaseCost[];
  total_tokens: number;
  total_usd: number;
  total_duration_ms: number;
}

// --- Critic --------------------------------------------------------------

// Mirrors `wisdom_layer.types.RiskLevel`. The critic-entropy route maps
// some legacy values into a different vocabulary
// ("low" → "healthy", "moderate" → "elevated"); see `EntropySnapshot`.
export type RiskLevel = "low" | "medium" | "high" | "critical";

// Mirrors `wisdom_layer.types.CriticFlag`.
export interface CriticFlag {
  category: string;
  description: string;
  severity: RiskLevel;
  evidence: string;
}

// Mirrors `wisdom_layer.types.CriticReview`.
export interface CriticReview {
  id: string;
  agent_id: string;
  output_text: string;
  context: Record<string, unknown> | null;
  risk_level: RiskLevel;
  flags: CriticFlag[];
  rationale: string;
  pass_through: boolean;
  directive_ids: string[];
  created_at: string;
}

// Output of `GET /api/critic/audits` — the SDK runs `agent.critic.audit()`
// and serializes via `model_dump()`. Mirrors
// `wisdom_layer.types.AuditReport`.
export interface AuditReport {
  period: string;
  consistency_score: number;
  narrative_drift_score: number;
  self_correction_rate: number;
  directive_adherence: number;
  flags: CriticFlag[];
}

// Output of `GET /api/critic/entropy` — the SDK route flattens
// `EntropyReport.components` and remaps `level` so the dashboard can
// render a single readable verdict. See
// `wisdom_layer.dashboard.routes.critic._LEVEL_MAP`.
export type EntropyLevel = "healthy" | "elevated" | "high" | "critical";

export interface EntropySnapshot {
  entropy_score: number;
  level: EntropyLevel;
  churn: number;
  volume: number;
  staleness: number;
  total_directives: number;
}
