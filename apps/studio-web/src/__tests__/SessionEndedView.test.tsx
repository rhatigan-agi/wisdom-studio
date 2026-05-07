import { afterEach, describe, expect, it } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import { SessionEndedView } from "../components/kiosk/SessionEndedView";
import { useStudio } from "../lib/store";
import type { StudioConfig } from "../types/api";

function setConfig(patch: Partial<StudioConfig>): void {
  useStudio.setState({
    config: {
      license_key: null,
      provider_keys: {},
      initialized: true,
      env_provider_keys: [],
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

afterEach(() => {
  cleanup();
  useStudio.setState({ config: null });
});

describe("SessionEndedView", () => {
  it("renders the TTL-expiry copy when state is session_ended", () => {
    setConfig({});
    render(<SessionEndedView state="session_ended" />);
    expect(screen.getByText("Session ended")).toBeInTheDocument();
  });

  it("renders the cap copy when state is token_cap_reached", () => {
    setConfig({});
    render(<SessionEndedView state="token_cap_reached" />);
    expect(screen.getByText("Session limit reached")).toBeInTheDocument();
  });

  it("hides the CTA when no href is configured", () => {
    setConfig({ session_end_cta_href: null });
    render(<SessionEndedView state="session_ended" />);
    expect(screen.queryByRole("link")).not.toBeInTheDocument();
  });

  it("renders the CTA with the configured label and href", () => {
    setConfig({
      session_end_cta_href: "https://example.com/signup",
      session_end_cta_label: "Make your own",
    });
    render(<SessionEndedView state="session_ended" />);
    const link = screen.getByRole("link", { name: "Make your own" });
    expect(link).toHaveAttribute("href", "https://example.com/signup");
  });

  it("falls back to a default label when only href is set", () => {
    setConfig({ session_end_cta_href: "https://example.com/signup" });
    render(<SessionEndedView state="session_ended" />);
    expect(screen.getByRole("link", { name: "Get started" })).toBeInTheDocument();
  });
});
