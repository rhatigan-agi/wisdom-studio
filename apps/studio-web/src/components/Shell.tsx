import { useEffect, useState } from "react";
import { Link, NavLink, Outlet, useLocation, useNavigate } from "react-router-dom";
import { Plus, Settings as SettingsIcon, BookOpen, Menu, X, Network } from "lucide-react";
import clsx from "clsx";
import { useStudio } from "../lib/store";
import type { AgentSummary } from "../types/api";
import { Banner } from "./kiosk/Banner";
import { SessionTimer } from "./kiosk/SessionTimer";

export function Shell(): JSX.Element {
  const agents = useStudio((s) => s.agents);
  const config = useStudio((s) => s.config);
  const navigate = useNavigate();
  const location = useLocation();
  const [drawerOpen, setDrawerOpen] = useState(false);

  // Auto-close the drawer on route change so a tap on a nav item dismisses
  // the overlay without an extra interaction.
  useEffect(() => {
    setDrawerOpen(false);
  }, [location.pathname]);

  const hideSettings = config?.hide_settings ?? false;
  const hideCrud = config?.hide_agent_crud ?? false;
  const docsUrl = config?.docs_url ?? null;

  const sidebar = (
    <>
      <div className="flex items-center justify-between gap-2 px-5 py-4 text-sm font-semibold tracking-wide text-zinc-100">
        <span className="flex items-center gap-2">
          <img src="/wisdom-icon.png" alt="" className="h-5 w-5" />
          Wisdom Studio
        </span>
        <button
          type="button"
          onClick={() => setDrawerOpen(false)}
          className="rounded-md p-2 text-zinc-400 hover:bg-zinc-800/60 hover:text-zinc-100 md:hidden"
          aria-label="Close menu"
        >
          <X className="h-5 w-5" />
        </button>
      </div>

      <nav className="flex-1 overflow-y-auto px-2 pb-4 text-sm">
        {!hideCrud && (
          <button
            type="button"
            onClick={() => navigate("/new")}
            className="mb-3 flex min-h-[44px] w-full items-center gap-2 rounded-md border border-emerald-700/40 bg-emerald-700/10 px-3 py-2 text-emerald-200 hover:bg-emerald-700/20"
          >
            <Plus className="h-4 w-4" />
            New agent
          </button>
        )}

        <div className="px-1 py-1 text-xs uppercase tracking-wider text-zinc-500">
          Agents
        </div>
        {agents.length === 0 ? (
          <div className="px-3 py-2 text-xs text-zinc-500">
            {hideCrud
              ? "No agents available."
              : "No agents yet. Create one to get started."}
          </div>
        ) : (
          <ul className="space-y-1">
            {agents.map((agent) => (
              <li key={agent.agent_id}>
                <NavLink
                  to={`/agents/${agent.agent_id}`}
                  className={({ isActive }) =>
                    clsx(
                      "block rounded-md px-3 py-2 transition",
                      isActive
                        ? "bg-zinc-800 text-zinc-100"
                        : "text-zinc-400 hover:bg-zinc-800/60 hover:text-zinc-100",
                    )
                  }
                >
                  <div className="flex items-center justify-between">
                    <span className="truncate">{agent.name}</span>
                    <span className="ml-2 shrink-0 rounded bg-zinc-800 px-1.5 py-0.5 font-mono text-[10px] text-zinc-400">
                      {agent.archetype}
                    </span>
                  </div>
                  <div className="mt-0.5 truncate text-xs text-zinc-500">
                    {agent.role || "—"}
                  </div>
                </NavLink>
              </li>
            ))}
          </ul>
        )}
      </nav>

      <div className="border-t border-zinc-800 p-2">
        <NavLink
          to="/workspace"
          className={({ isActive }) =>
            clsx(
              "flex min-h-[44px] items-center gap-2 rounded-md px-3 py-2 text-sm",
              isActive
                ? "bg-zinc-800 text-zinc-100"
                : "text-zinc-400 hover:bg-zinc-800/60 hover:text-zinc-100",
            )
          }
        >
          <Network className="h-4 w-4" />
          Workspace
        </NavLink>
        {docsUrl && (
          <a
            href={docsUrl}
            target="_blank"
            rel="noreferrer"
            className="flex min-h-[44px] items-center gap-2 rounded-md px-3 py-2 text-sm text-zinc-400 hover:bg-zinc-800/60 hover:text-zinc-100"
          >
            <BookOpen className="h-4 w-4" />
            Docs
          </a>
        )}
        {!hideSettings && (
          <Link
            to="/settings"
            className="flex min-h-[44px] items-center gap-2 rounded-md px-3 py-2 text-sm text-zinc-400 hover:bg-zinc-800/60 hover:text-zinc-100"
          >
            <SettingsIcon className="h-4 w-4" />
            Settings
          </Link>
        )}
      </div>
    </>
  );

  return (
    <div className="flex h-full flex-col bg-zinc-950">
      <Banner />

      {/* Mobile top bar: hamburger + SessionTimer. Hidden on md+ where the
          sidebar is always visible and carries the timer itself. */}
      <header className="flex items-center justify-between gap-3 border-b border-zinc-800 bg-zinc-900/60 px-4 py-2 md:hidden">
        <button
          type="button"
          onClick={() => setDrawerOpen(true)}
          className="flex h-11 w-11 items-center justify-center rounded-md text-zinc-200 hover:bg-zinc-800/60"
          aria-label="Open menu"
        >
          <Menu className="h-5 w-5" />
        </button>
        <span className="flex items-center gap-2 text-sm font-semibold text-zinc-100">
          <img src="/wisdom-icon.png" alt="" className="h-4 w-4" />
          Wisdom Studio
        </span>
        <SessionTimer />
      </header>

      <div className="grid flex-1 grid-cols-1 overflow-hidden md:grid-cols-[260px_1fr]">
        {/* Desktop sidebar — always rendered at md+. */}
        <aside className="hidden flex-col border-r border-zinc-800 bg-zinc-900/40 md:flex">
          <div className="hidden items-center justify-between gap-2 px-5 py-4 text-sm font-semibold tracking-wide text-zinc-100 md:flex">
            <span className="flex items-center gap-2">
              <img src="/wisdom-icon.png" alt="" className="h-5 w-5" />
              Wisdom Studio
            </span>
            <SessionTimer />
          </div>
          <DesktopNav
            agents={agents}
            hideCrud={hideCrud}
            hideSettings={hideSettings}
            docsUrl={docsUrl}
            onNewAgent={() => navigate("/new")}
          />
        </aside>

        {/* Mobile drawer overlay. */}
        {drawerOpen && (
          <div
            className="fixed inset-0 z-40 md:hidden"
            role="dialog"
            aria-modal="true"
            onClick={() => setDrawerOpen(false)}
          >
            <div className="absolute inset-0 bg-black/60" />
            <aside
              onClick={(e) => e.stopPropagation()}
              className="absolute inset-y-0 left-0 flex w-72 max-w-[85vw] flex-col border-r border-zinc-800 bg-zinc-900"
            >
              {sidebar}
            </aside>
          </div>
        )}

        <main className="overflow-hidden">
          <Outlet />
        </main>
      </div>
    </div>
  );
}

// Desktop sidebar reuses the inner sections (without the mobile-only
// close-button header). Keeping it inline avoids a second component file
// for what is otherwise the same markup.
function DesktopNav(props: {
  agents: AgentSummary[];
  hideCrud: boolean;
  hideSettings: boolean;
  docsUrl: string | null;
  onNewAgent: () => void;
}): JSX.Element {
  return (
    <>
      <nav className="flex-1 overflow-y-auto px-2 pb-4 text-sm">
        {!props.hideCrud && (
          <button
            type="button"
            onClick={props.onNewAgent}
            className="mb-3 flex w-full items-center gap-2 rounded-md border border-emerald-700/40 bg-emerald-700/10 px-3 py-2 text-emerald-200 hover:bg-emerald-700/20"
          >
            <Plus className="h-4 w-4" />
            New agent
          </button>
        )}
        <div className="px-1 py-1 text-xs uppercase tracking-wider text-zinc-500">
          Agents
        </div>
        {props.agents.length === 0 ? (
          <div className="px-3 py-2 text-xs text-zinc-500">
            {props.hideCrud
              ? "No agents available."
              : "No agents yet. Create one to get started."}
          </div>
        ) : (
          <ul className="space-y-1">
            {props.agents.map((agent) => (
              <li key={agent.agent_id}>
                <NavLink
                  to={`/agents/${agent.agent_id}`}
                  className={({ isActive }) =>
                    clsx(
                      "block rounded-md px-3 py-2 transition",
                      isActive
                        ? "bg-zinc-800 text-zinc-100"
                        : "text-zinc-400 hover:bg-zinc-800/60 hover:text-zinc-100",
                    )
                  }
                >
                  <div className="flex items-center justify-between">
                    <span className="truncate">{agent.name}</span>
                    <span className="ml-2 shrink-0 rounded bg-zinc-800 px-1.5 py-0.5 font-mono text-[10px] text-zinc-400">
                      {agent.archetype}
                    </span>
                  </div>
                  <div className="mt-0.5 truncate text-xs text-zinc-500">
                    {agent.role || "—"}
                  </div>
                </NavLink>
              </li>
            ))}
          </ul>
        )}
      </nav>
      <div className="border-t border-zinc-800 p-2">
        <NavLink
          to="/workspace"
          className={({ isActive }) =>
            clsx(
              "flex items-center gap-2 rounded-md px-3 py-2 text-sm",
              isActive
                ? "bg-zinc-800 text-zinc-100"
                : "text-zinc-400 hover:bg-zinc-800/60 hover:text-zinc-100",
            )
          }
        >
          <Network className="h-4 w-4" />
          Workspace
        </NavLink>
        {props.docsUrl && (
          <a
            href={props.docsUrl}
            target="_blank"
            rel="noreferrer"
            className="flex items-center gap-2 rounded-md px-3 py-2 text-sm text-zinc-400 hover:bg-zinc-800/60 hover:text-zinc-100"
          >
            <BookOpen className="h-4 w-4" />
            Docs
          </a>
        )}
        {!props.hideSettings && (
          <Link
            to="/settings"
            className="flex items-center gap-2 rounded-md px-3 py-2 text-sm text-zinc-400 hover:bg-zinc-800/60 hover:text-zinc-100"
          >
            <SettingsIcon className="h-4 w-4" />
            Settings
          </Link>
        )}
      </div>
    </>
  );
}
