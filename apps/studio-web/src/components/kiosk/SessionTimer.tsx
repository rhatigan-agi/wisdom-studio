import { useEffect, useState } from "react";
import { Clock } from "lucide-react";
import { useStudio } from "../../lib/store";

export const SESSION_EXPIRED_EVENT = "wisdom-studio:session-expired";

// Kiosk / conference deployments set `WISDOM_STUDIO_SESSION_TTL_MINUTES` to
// reset the visitor experience after a fixed window. The server doesn't
// enforce the TTL itself — that's the SDK's per-session lifecycle. Studio
// just renders a visible countdown and dispatches a window event when it
// hits zero so listeners (e.g. AgentDetail) can navigate away or reset
// transient UI state.
export function SessionTimer(): JSX.Element | null {
  const ttlMinutes = useStudio((s) => s.config?.session_ttl_minutes ?? null);
  const [secondsLeft, setSecondsLeft] = useState<number | null>(
    ttlMinutes ? ttlMinutes * 60 : null,
  );

  useEffect(() => {
    if (!ttlMinutes) {
      setSecondsLeft(null);
      return;
    }
    setSecondsLeft(ttlMinutes * 60);
    const start = Date.now();
    const total = ttlMinutes * 60;
    const id = window.setInterval(() => {
      const elapsed = Math.floor((Date.now() - start) / 1000);
      const remaining = Math.max(0, total - elapsed);
      setSecondsLeft(remaining);
      if (remaining === 0) {
        window.clearInterval(id);
        window.dispatchEvent(new CustomEvent(SESSION_EXPIRED_EVENT));
      }
    }, 1000);
    return () => window.clearInterval(id);
  }, [ttlMinutes]);

  if (secondsLeft === null) return null;

  const mm = Math.floor(secondsLeft / 60);
  const ss = secondsLeft % 60;
  const expired = secondsLeft === 0;

  return (
    <div
      className={`flex items-center gap-1.5 rounded-md border px-2 py-1 text-[11px] font-mono ${
        expired
          ? "border-red-700/40 bg-red-700/10 text-red-200"
          : "border-zinc-700 bg-zinc-900/60 text-zinc-300"
      }`}
      title={expired ? "Session expired" : "Time remaining in this session"}
    >
      <Clock className="h-3 w-3" />
      {expired ? "expired" : `${mm}:${String(ss).padStart(2, "0")}`}
    </div>
  );
}
