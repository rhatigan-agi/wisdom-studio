import { useMemo, useState } from "react";

// Lightweight read-only "memory map" — a 2D SVG node cloud showing the
// agent's accumulated memories. Sized to fit a 360-px side pane; nothing
// fancier than fixed-radius polar layout, hash-derived positions, hover
// tooltips. The brief calls for "lands or hides": if the data source
// returns nothing the parent gates the tab on `nodes.length` so the
// panel disappears entirely with no visitor-visible failure.
//
// Positions are deterministic (hash → angle/ring) so re-renders don't
// cause nodes to jitter. We avoid a force-directed sim deliberately —
// that needs ~300 LOC + a layout tick — and we avoid Three.js / WebGL
// because the SDK dashboard's MemoryGalaxy already covers that need
// for power users who navigate to the mounted dashboard.

export interface MemoryNode {
  id: string;
  kind: string;
  snippet: string;
  createdAt: string | null;
  source: "seed" | "live";
}

// Polar layout params. Three concentric rings hold up to 8 / 16 / 24 nodes
// without overlap at the chosen radii; beyond ~48 nodes we overflow onto a
// fourth ring. Good enough for a demo agent with a few dozen memories.
const VIEW = 320;
const CENTER = VIEW / 2;
const RINGS = [56, 100, 140, 175];
const RING_CAPACITY = [8, 16, 24, 32];
const NODE_RADIUS = 6;

interface KindStyle {
  fill: string;
  stroke: string;
  label: string;
}

// Same color family as the cognition stream's `eventColor()` — keeps the
// visual vocabulary consistent across panes.
const KIND_STYLES: Record<string, KindStyle> = {
  directive: { fill: "#fbbf24", stroke: "#92400e", label: "Directive" },
  dream: { fill: "#a78bfa", stroke: "#5b21b6", label: "Dream" },
  consolidated: { fill: "#a78bfa", stroke: "#5b21b6", label: "Consolidated" },
  journal: { fill: "#7dd3fc", stroke: "#075985", label: "Journal" },
  fact: { fill: "#34d399", stroke: "#065f46", label: "Fact" },
  conversation: { fill: "#34d399", stroke: "#065f46", label: "Conversation" },
};
const DEFAULT_STYLE: KindStyle = {
  fill: "#a1a1aa",
  stroke: "#3f3f46",
  label: "Memory",
};

function styleFor(kind: string): KindStyle {
  return KIND_STYLES[kind] ?? DEFAULT_STYLE;
}

// FNV-1a 32-bit. Stable, dependency-free, good enough for layout hashing.
function hash(input: string): number {
  let h = 2166136261;
  for (let i = 0; i < input.length; i += 1) {
    h ^= input.charCodeAt(i);
    h = Math.imul(h, 16777619);
  }
  return h >>> 0;
}

interface PlacedNode extends MemoryNode {
  x: number;
  y: number;
}

function place(nodes: MemoryNode[]): PlacedNode[] {
  // Bucket nodes into rings by stable hash, then space them around each
  // ring. The hash decides which ring (so a given memory always lives in
  // the same orbit) and a per-ring counter spaces them evenly.
  const buckets: MemoryNode[][] = RINGS.map(() => []);
  for (const node of nodes) {
    const h = hash(node.id);
    let target = h % RINGS.length;
    for (let attempts = 0; attempts < RINGS.length; attempts += 1) {
      const idx = (target + attempts) % RINGS.length;
      if (buckets[idx].length < RING_CAPACITY[idx]) {
        buckets[idx].push(node);
        break;
      }
    }
  }
  const placed: PlacedNode[] = [];
  buckets.forEach((bucket, ringIdx) => {
    const radius = RINGS[ringIdx];
    bucket.forEach((node, i) => {
      const offset = (hash(node.id) % 1000) / 1000;
      const angle = ((i + offset) / Math.max(bucket.length, 1)) * Math.PI * 2;
      placed.push({
        ...node,
        x: CENTER + radius * Math.cos(angle),
        y: CENTER + radius * Math.sin(angle),
      });
    });
  });
  return placed;
}

interface MemoryMapProps {
  nodes: MemoryNode[];
}

export function MemoryMap({ nodes }: MemoryMapProps): JSX.Element | null {
  const [hoverId, setHoverId] = useState<string | null>(null);
  const placed = useMemo(() => place(nodes), [nodes]);
  const hover = useMemo(
    () => placed.find((n) => n.id === hoverId) ?? null,
    [placed, hoverId],
  );

  if (placed.length === 0) return null;

  const counts = placed.reduce<Record<string, number>>((acc, node) => {
    const label = styleFor(node.kind).label;
    acc[label] = (acc[label] ?? 0) + 1;
    return acc;
  }, {});
  const legend = Object.entries(counts).sort(([, a], [, b]) => b - a);

  return (
    <div className="flex h-full flex-col">
      <div className="border-b border-zinc-800 px-3 py-2 text-[11px] text-zinc-500">
        {placed.length} {placed.length === 1 ? "memory" : "memories"} ·{" "}
        <span className="text-zinc-400">hover a node to inspect</span>
      </div>
      <div className="relative flex-1 overflow-hidden">
        <svg
          viewBox={`0 0 ${VIEW} ${VIEW}`}
          className="h-full w-full"
          role="img"
          aria-label="Memory map"
        >
          {RINGS.map((r) => (
            <circle
              key={r}
              cx={CENTER}
              cy={CENTER}
              r={r}
              fill="none"
              stroke="#27272a"
              strokeWidth={0.5}
              strokeDasharray="2 3"
            />
          ))}
          <circle cx={CENTER} cy={CENTER} r={3} fill="#52525b" />
          {placed.map((node) => {
            const style = styleFor(node.kind);
            const isHover = node.id === hoverId;
            return (
              <circle
                key={node.id}
                cx={node.x}
                cy={node.y}
                r={isHover ? NODE_RADIUS + 2 : NODE_RADIUS}
                fill={style.fill}
                stroke={style.stroke}
                strokeWidth={1}
                opacity={hoverId && !isHover ? 0.35 : 0.9}
                onMouseEnter={() => setHoverId(node.id)}
                onMouseLeave={() => setHoverId((cur) => (cur === node.id ? null : cur))}
                style={{ cursor: "pointer", transition: "opacity 120ms" }}
              />
            );
          })}
        </svg>
        {hover && (
          <div className="pointer-events-none absolute inset-x-2 bottom-2 rounded-md border border-zinc-700 bg-zinc-950/95 p-2 text-[11px] text-zinc-200 shadow-lg">
            <div className="mb-1 flex items-center justify-between gap-2">
              <span
                className="rounded px-1.5 py-0.5 text-[10px] uppercase tracking-wider"
                style={{ backgroundColor: `${styleFor(hover.kind).fill}33`, color: styleFor(hover.kind).fill }}
              >
                {hover.kind}
              </span>
              {hover.createdAt && (
                <span className="font-mono text-[10px] text-zinc-500">
                  {new Date(hover.createdAt).toLocaleTimeString([], { hour12: false })}
                </span>
              )}
            </div>
            <p className="break-words leading-snug text-zinc-300">
              {hover.snippet || <span className="text-zinc-600">(no preview)</span>}
            </p>
          </div>
        )}
      </div>
      <div className="flex flex-wrap gap-x-3 gap-y-1 border-t border-zinc-800 px-3 py-2 text-[10px] text-zinc-500">
        {legend.map(([label, count]) => {
          const style = Object.values(KIND_STYLES).find((s) => s.label === label) ?? DEFAULT_STYLE;
          return (
            <span key={label} className="flex items-center gap-1">
              <span
                className="inline-block h-2 w-2 rounded-full"
                style={{ backgroundColor: style.fill }}
              />
              {label} · {count}
            </span>
          );
        })}
      </div>
    </div>
  );
}
