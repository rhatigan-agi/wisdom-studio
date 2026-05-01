import { useEffect, useState } from "react";
import { Clock } from "lucide-react";
import { useStudio } from "../../lib/store";

export const SESSION_EXPIRED_EVENT = "wisdom-studio:session-expired";

// Kiosk / conference deployments set `WISDOM_STUDIO_SESSION_TTL_MINUTES` to
// reset the visitor experience after a fixed window. The TTL clock is owned
// by the backend (anchored on first WebSocket connect, exposed via
// GET /api/agents/{id}/session). Studio polls that endpoint into the store
// and this component just renders the remaining time. Once the gate trips
// the chat endpoint returns 410 — the countdown is purely visual.
//
// The countdown is recomputed each tick from `expires_at - now`, NOT from
// `Date.now()` at mount. That way bouncing the WS, refreshing the tab, or
// re-mounting the component never resets a visitor's window — the only
// authority is the backend timestamp.
export function SessionTimer(): JSX.Element | null {
  const expiresAt = useStudio((s) => s.sessionState?.expires_at ?? null);
  const [secondsLeft, setSecondsLeft] = useState<number | null>(() =>
    computeRemaining(expiresAt),
  );

  useEffect(() => {
    if (!expiresAt) {
      setSecondsLeft(null);
      return;
    }
    const update = (): number => {
      const remaining = computeRemaining(expiresAt) ?? 0;
      setSecondsLeft(remaining);
      if (remaining === 0) {
        window.dispatchEvent(new CustomEvent(SESSION_EXPIRED_EVENT));
      }
      return remaining;
    };
    if (update() === 0) return;
    const id = window.setInterval(() => {
      if (update() === 0) window.clearInterval(id);
    }, 1000);
    return () => window.clearInterval(id);
  }, [expiresAt]);

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

function computeRemaining(expiresAt: string | null): number | null {
  if (!expiresAt) return null;
  const target = new Date(expiresAt).getTime();
  if (Number.isNaN(target)) return null;
  return Math.max(0, Math.floor((target - Date.now()) / 1000));
}
