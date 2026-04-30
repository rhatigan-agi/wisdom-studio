import { useEffect } from "react";
import { Navigate, Route, Routes, useNavigate } from "react-router-dom";
import { api } from "./lib/api";
import { useStudio } from "./lib/store";
import { Shell } from "./components/Shell";
import { FirstRun } from "./pages/FirstRun";
import { Dashboard } from "./pages/Dashboard";
import { NewAgent } from "./pages/NewAgent";
import { AgentDetail } from "./pages/AgentDetail";
import { Settings } from "./pages/Settings";

export default function App() {
  const setConfig = useStudio((s) => s.setConfig);
  const setAgents = useStudio((s) => s.setAgents);
  const config = useStudio((s) => s.config);
  const navigate = useNavigate();

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const cfg = await api.getConfig();
        if (cancelled) return;
        setConfig(cfg);
        // hide_settings deployments shadow the first-run wizard — provider
        // keys come from server env (or are not needed) and the PUT route
        // returns 403 anyway. Skip straight to the dashboard.
        if (!cfg.initialized && !cfg.hide_settings) {
          navigate("/setup", { replace: true });
          return;
        }
        const agents = await api.listAgents();
        if (cancelled) return;
        setAgents(agents);
      } catch (error) {
        console.error("studio: bootstrap failed", error);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [navigate, setAgents, setConfig]);

  if (config === null) {
    return (
      <div className="flex h-full items-center justify-center text-zinc-500">
        Loading…
      </div>
    );
  }

  return (
    <Routes>
      <Route path="/setup" element={<FirstRun />} />
      <Route element={<Shell />}>
        <Route path="/" element={<Dashboard />} />
        <Route path="/new" element={<NewAgent />} />
        <Route path="/agents/:agentId" element={<AgentDetail />} />
        <Route path="/settings" element={<Settings />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Route>
    </Routes>
  );
}
