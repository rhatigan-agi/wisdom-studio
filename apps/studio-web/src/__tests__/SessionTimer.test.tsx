import { act, cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { SESSION_EXPIRED_EVENT, SessionTimer } from "../components/kiosk/SessionTimer";
import { useStudio } from "../lib/store";
import type { StudioConfig } from "../types/api";

function setConfig(patch: Partial<StudioConfig>): void {
  useStudio.setState({
    config: {
      license_key: null,
      provider_keys: {},
      initialized: true,
      banner_html: null,
      session_ttl_minutes: null,
      docs_url: null,
      signup_url: null,
      locked_llm: null,
      hide_settings: false,
      hide_agent_crud: false,
      ephemeral: false,
      token_cap_per_session: null,
      session_end_cta_href: null,
      session_end_cta_label: null,
      ...patch,
    },
  });
}

beforeEach(() => {
  vi.useFakeTimers();
});

afterEach(() => {
  cleanup();
  vi.useRealTimers();
  useStudio.setState({ config: null });
});

describe("SessionTimer", () => {
  it("renders nothing when no TTL is configured", () => {
    setConfig({ session_ttl_minutes: null });
    const { container } = render(<SessionTimer />);
    expect(container.firstChild).toBeNull();
  });

  it("counts down in mm:ss format", () => {
    setConfig({ session_ttl_minutes: 1 });
    render(<SessionTimer />);
    expect(screen.getByText("1:00")).toBeInTheDocument();
    act(() => {
      vi.advanceTimersByTime(1500);
    });
    // After ~1.5s the display should have decremented at least one tick.
    expect(screen.queryByText("1:00")).not.toBeInTheDocument();
  });

  it("dispatches the session-expired event when the countdown hits zero", () => {
    setConfig({ session_ttl_minutes: 1 });
    const listener = vi.fn();
    window.addEventListener(SESSION_EXPIRED_EVENT, listener);
    render(<SessionTimer />);
    act(() => {
      vi.advanceTimersByTime(60_500);
    });
    expect(listener).toHaveBeenCalledTimes(1);
    expect(screen.getByText("expired")).toBeInTheDocument();
    window.removeEventListener(SESSION_EXPIRED_EVENT, listener);
  });
});
