import { Link } from "react-router-dom";
import { Plus } from "lucide-react";
import { useStudio } from "../lib/store";

export function Dashboard(): JSX.Element {
  const agents = useStudio((s) => s.agents);
  const hideCrud = useStudio((s) => s.config?.hide_agent_crud ?? false);

  return (
    <div className="h-full overflow-y-auto px-8 py-10">
      <header className="mb-8 flex items-end justify-between">
        <div>
          <h1 className="text-2xl font-semibold text-zinc-100">Agents</h1>
          <p className="mt-1 text-sm text-zinc-400">
            Each agent has its own genome, memory, and directive history.
          </p>
        </div>
        {!hideCrud && (
          <Link
            to="/new"
            className="flex items-center gap-2 rounded-md bg-emerald-600 px-4 py-2 text-sm font-medium text-emerald-50 hover:bg-emerald-500"
          >
            <Plus className="h-4 w-4" />
            New agent
          </Link>
        )}
      </header>

      {agents.length === 0 ? (
        <EmptyState hideCrud={hideCrud} />
      ) : (
        <ul className="grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-3">
          {agents.map((agent) => (
            <li key={agent.agent_id}>
              <Link
                to={`/agents/${agent.agent_id}`}
                className="block rounded-lg border border-zinc-800 bg-zinc-900/40 p-4 transition hover:border-zinc-700 hover:bg-zinc-900"
              >
                <div className="flex items-center justify-between">
                  <span className="font-medium text-zinc-100">{agent.name}</span>
                  <span className="rounded bg-zinc-800 px-2 py-0.5 font-mono text-[10px] text-zinc-400">
                    {agent.archetype}
                  </span>
                </div>
                <div className="mt-1 truncate text-sm text-zinc-400">
                  {agent.role || "—"}
                </div>
                <div className="mt-3 text-xs text-zinc-500">
                  {agent.llm_provider} · {agent.storage_kind}
                </div>
              </Link>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function EmptyState(props: { hideCrud: boolean }): JSX.Element {
  if (props.hideCrud) {
    return (
      <div className="rounded-lg border border-dashed border-zinc-800 px-8 py-16 text-center">
        <h2 className="text-lg font-medium text-zinc-200">No agents available</h2>
        <p className="mx-auto mt-2 max-w-md text-sm text-zinc-400">
          This deployment doesn't expose agent creation. Ask the operator to seed
          one, or visit a deployment that has agents to explore.
        </p>
      </div>
    );
  }
  return (
    <div className="rounded-lg border border-dashed border-zinc-800 px-8 py-16 text-center">
      <h2 className="text-lg font-medium text-zinc-200">No agents yet</h2>
      <p className="mx-auto mt-2 max-w-md text-sm text-zinc-400">
        Spin up a Wisdom Layer agent in 60 seconds. Pick an archetype, add a persona, point
        at an LLM, and start chatting — Studio will stream cognition events as the agent
        captures memories and forms directives.
      </p>
      <Link
        to="/new"
        className="mt-6 inline-flex items-center gap-2 rounded-md bg-emerald-600 px-4 py-2 text-sm font-medium text-emerald-50 hover:bg-emerald-500"
      >
        <Plus className="h-4 w-4" />
        Create your first agent
      </Link>
    </div>
  );
}
