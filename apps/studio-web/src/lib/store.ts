import { create } from "zustand";
import type {
  AgentSummary,
  CognitionEvent,
  SessionState,
  StudioConfig,
} from "../types/api";

interface StudioState {
  config: StudioConfig | null;
  agents: AgentSummary[];
  selectedAgentId: string | null;
  cognitionByAgent: Record<string, CognitionEvent[]>;
  // Server-confirmed lifecycle for the currently-viewed agent. Polled by
  // AgentDetail when the deployment configures a TTL or token cap; null
  // otherwise (and on tab unmount). SessionTimer reads `expires_at` from
  // here so its countdown follows the backend's authoritative clock —
  // bouncing the WS or the SPA can't reset a visitor's window.
  sessionState: SessionState | null;

  setConfig: (config: StudioConfig | null) => void;
  setAgents: (agents: AgentSummary[]) => void;
  selectAgent: (id: string | null) => void;
  appendCognitionBatch: (agentId: string, events: CognitionEvent[]) => void;
  clearCognition: (agentId: string) => void;
  setSessionState: (state: SessionState | null) => void;
}

const COGNITION_BUFFER = 200;

export const useStudio = create<StudioState>((set) => ({
  config: null,
  agents: [],
  selectedAgentId: null,
  cognitionByAgent: {},
  sessionState: null,

  setConfig: (config) => set({ config }),
  setAgents: (agents) => set({ agents }),
  selectAgent: (selectedAgentId) => set({ selectedAgentId }),
  appendCognitionBatch: (agentId, events) =>
    set((state) => {
      if (events.length === 0) return state;
      const existing = state.cognitionByAgent[agentId] ?? [];
      const next = [...existing, ...events].slice(-COGNITION_BUFFER);
      return {
        cognitionByAgent: { ...state.cognitionByAgent, [agentId]: next },
      };
    }),
  clearCognition: (agentId) =>
    set((state) => ({
      cognitionByAgent: { ...state.cognitionByAgent, [agentId]: [] },
    })),
  setSessionState: (sessionState) => set({ sessionState }),
}));
