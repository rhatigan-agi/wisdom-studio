import { create } from "zustand";
import type { AgentSummary, CognitionEvent, StudioConfig } from "../types/api";

interface StudioState {
  config: StudioConfig | null;
  agents: AgentSummary[];
  selectedAgentId: string | null;
  cognitionByAgent: Record<string, CognitionEvent[]>;

  setConfig: (config: StudioConfig | null) => void;
  setAgents: (agents: AgentSummary[]) => void;
  selectAgent: (id: string | null) => void;
  appendCognitionBatch: (agentId: string, events: CognitionEvent[]) => void;
  clearCognition: (agentId: string) => void;
}

const COGNITION_BUFFER = 200;

export const useStudio = create<StudioState>((set) => ({
  config: null,
  agents: [],
  selectedAgentId: null,
  cognitionByAgent: {},

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
}));
