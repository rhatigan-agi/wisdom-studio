import { useState } from "react";
import { Orbit, Minus, Plus } from "lucide-react";
import { MemoryMap, type MemoryNode } from "./MemoryMap";

// Floating bottom-right minimap. Renders independently of the side pane so
// the cognition / memories tabs are unaffected. Always present once the
// page is up — empty state lands gracefully so users can see "this is where
// memory will appear" before the agent has captured anything.
//
// Hidden on small screens (md-and-up only) — at <768px the chat input takes
// the full width and a corner overlay would obscure it. The side-pane
// experience already covers mobile.

interface Props {
  nodes: MemoryNode[];
}

const COLLAPSE_KEY = "wisdom-studio:memory-map-collapsed";

function readCollapsed(): boolean {
  try {
    return window.localStorage.getItem(COLLAPSE_KEY) === "1";
  } catch {
    return false;
  }
}

function writeCollapsed(value: boolean): void {
  try {
    window.localStorage.setItem(COLLAPSE_KEY, value ? "1" : "0");
  } catch {
    // Privacy-mode browsers can throw — collapse state just won't persist.
  }
}

export function MemoryMapOverlay({ nodes }: Props): JSX.Element {
  const [collapsed, setCollapsed] = useState<boolean>(readCollapsed);
  const count = nodes.length;

  const toggle = (): void => {
    setCollapsed((prev) => {
      const next = !prev;
      writeCollapsed(next);
      return next;
    });
  };

  if (collapsed) {
    return (
      <button
        type="button"
        onClick={toggle}
        title={`Memory map · ${count} ${count === 1 ? "memory" : "memories"}`}
        aria-label="Expand memory map"
        className="fixed bottom-4 right-4 z-30 hidden h-10 w-10 items-center justify-center rounded-full border border-zinc-700 bg-zinc-900/90 text-zinc-300 shadow-lg backdrop-blur hover:bg-zinc-800 hover:text-zinc-100 md:flex"
      >
        <Orbit className="h-4 w-4" />
        {count > 0 && (
          <span className="absolute -right-1 -top-1 flex h-4 min-w-[16px] items-center justify-center rounded-full bg-emerald-600 px-1 text-[10px] font-medium text-white">
            {count > 99 ? "99+" : count}
          </span>
        )}
      </button>
    );
  }

  return (
    <div
      role="complementary"
      aria-label="Memory map"
      className="fixed bottom-4 right-4 z-30 hidden h-[260px] w-[260px] flex-col overflow-hidden rounded-lg border border-zinc-700 bg-zinc-900/95 shadow-2xl backdrop-blur md:flex"
    >
      <div className="flex items-center justify-between gap-2 border-b border-zinc-800 px-3 py-1.5 text-[11px] text-zinc-400">
        <span className="flex items-center gap-1.5">
          <Orbit className="h-3.5 w-3.5 text-zinc-500" />
          Memory map
        </span>
        <button
          type="button"
          onClick={toggle}
          aria-label="Collapse memory map"
          className="rounded p-0.5 text-zinc-500 hover:bg-zinc-800 hover:text-zinc-200"
        >
          <Minus className="h-3.5 w-3.5" />
        </button>
      </div>
      {count === 0 ? (
        <EmptyState />
      ) : (
        <div className="min-h-0 flex-1">
          <MemoryMap nodes={nodes} />
        </div>
      )}
    </div>
  );
}

function EmptyState(): JSX.Element {
  return (
    <div className="flex flex-1 flex-col items-center justify-center gap-2 px-4 py-6 text-center">
      <Plus className="h-5 w-5 text-zinc-600" />
      <p className="text-[11px] text-zinc-400">No memories yet</p>
      <p className="text-[10px] leading-snug text-zinc-600">
        Memories captured by the agent will appear here.
      </p>
    </div>
  );
}
