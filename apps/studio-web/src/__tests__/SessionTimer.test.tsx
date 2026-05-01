import { act, cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { SESSION_EXPIRED_EVENT, SessionTimer } from "../components/kiosk/SessionTimer";
import { useStudio } from "../lib/store";
import type { SessionState } from "../types/api";

function setSessionState(patch: Partial<SessionState> | null): void {
  if (patch === null) {
    useStudio.setState({ sessionState: null });
    return;
  }
  useStudio.setState({
    sessionState: {
      agent_id: "test",
      state: "active",
      started_at: new Date().toISOString(),
      expires_at: null,
      tokens_used: 0,
      token_cap: null,
      session_ttl_minutes: null,
      ...patch,
    },
  });
}

beforeEach(() => {
  // Pin a fixed wall clock so `new Date(expires_at) - Date.now()` is stable
  // across the run. `setSystemTime(0)` puts "now" at the unix epoch so
  // `expires_at = ttl_seconds * 1000` produces an exact remaining count.
  vi.useFakeTimers();
  vi.setSystemTime(0);
});

afterEach(() => {
  cleanup();
  vi.useRealTimers();
  useStudio.setState({ sessionState: null });
});

describe("SessionTimer", () => {
  it("renders nothing when no expires_at is in the store", () => {
    setSessionState(null);
    const { container } = render(<SessionTimer />);
    expect(container.firstChild).toBeNull();
  });

  it("counts down from a backend-supplied expires_at in mm:ss", () => {
    setSessionState({ expires_at: new Date(60_000).toISOString() });
    render(<SessionTimer />);
    expect(screen.getByText("1:00")).toBeInTheDocument();
    act(() => {
      vi.advanceTimersByTime(1500);
    });
    expect(screen.queryByText("1:00")).not.toBeInTheDocument();
  });

  it("dispatches the session-expired event when expires_at is reached", () => {
    setSessionState({ expires_at: new Date(60_000).toISOString() });
    const listener = vi.fn();
    window.addEventListener(SESSION_EXPIRED_EVENT, listener);
    render(<SessionTimer />);
    act(() => {
      vi.advanceTimersByTime(60_500);
    });
    expect(listener).toHaveBeenCalled();
    expect(screen.getByText("expired")).toBeInTheDocument();
    window.removeEventListener(SESSION_EXPIRED_EVENT, listener);
  });

  it("re-syncs to a new expires_at when the store updates", () => {
    setSessionState({ expires_at: new Date(60_000).toISOString() });
    render(<SessionTimer />);
    expect(screen.getByText("1:00")).toBeInTheDocument();

    // Backend pushes a fresh expires_at (e.g. on first WS connect anchor).
    act(() => {
      setSessionState({ expires_at: new Date(120_000).toISOString() });
    });
    expect(screen.getByText("2:00")).toBeInTheDocument();
  });
});
