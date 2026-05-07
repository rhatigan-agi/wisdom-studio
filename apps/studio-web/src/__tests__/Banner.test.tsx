import { afterEach, describe, expect, it } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import { Banner } from "../components/kiosk/Banner";
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

describe("Banner", () => {
  it("renders nothing when banner_html is null", () => {
    setConfig({ banner_html: null });
    const { container } = render(<Banner />);
    expect(container.firstChild).toBeNull();
  });

  it("renders nothing when banner_html is empty string", () => {
    setConfig({ banner_html: "" });
    const { container } = render(<Banner />);
    expect(container.firstChild).toBeNull();
  });

  it("renders sanitized inline HTML from the server", () => {
    // The server has already passed banner_html through bleach; the
    // component just hands it to React. We exercise the dangerouslySetInnerHTML
    // path here.
    setConfig({ banner_html: "<strong>Demo</strong> mode" });
    render(<Banner />);
    const banner = screen.getByRole("status");
    expect(banner).toBeInTheDocument();
    expect(banner.querySelector("strong")?.textContent).toBe("Demo");
    expect(banner.textContent).toContain("Demo mode");
  });
});
