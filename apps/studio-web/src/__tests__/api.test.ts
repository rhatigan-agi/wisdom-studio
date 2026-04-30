import { afterEach, describe, expect, it, vi } from "vitest";
import { TierError, api } from "../lib/api";

const originalFetch = globalThis.fetch;

afterEach(() => {
  globalThis.fetch = originalFetch;
  vi.restoreAllMocks();
});

function mockFetch(body: unknown, init: { status: number }): void {
  globalThis.fetch = vi.fn(async () =>
    new Response(JSON.stringify(body), {
      status: init.status,
      statusText: "Test",
      headers: { "content-type": "application/json" },
    }),
  ) as typeof fetch;
}

describe("api request wrapper", () => {
  it("throws TierError on a 402 cap_reached body", async () => {
    mockFetch(
      {
        error: "cap_reached",
        cap_kind: "memories",
        current: 10,
        limit: 10,
        reset_at: null,
        upgrade_url: "https://example.com/upgrade",
        message: "Memory cap reached.",
      },
      { status: 402 },
    );

    await expect(api.health()).rejects.toBeInstanceOf(TierError);
    try {
      await api.health();
    } catch (err) {
      expect(err).toBeInstanceOf(TierError);
      const tier = err as TierError;
      expect(tier.status).toBe(402);
      expect(tier.body.error).toBe("cap_reached");
      if (tier.body.error === "cap_reached") {
        expect(tier.body.cap_kind).toBe("memories");
        expect(tier.body.current).toBe(10);
      }
    }
  });

  it("throws TierError on a 403 feature_gated body", async () => {
    mockFetch(
      {
        error: "feature_gated",
        feature: "dreams",
        required_tier: "Pro",
        upgrade_url: "https://example.com/upgrade",
        message: "Pro tier required.",
      },
      { status: 403 },
    );

    try {
      await api.health();
      throw new Error("expected throw");
    } catch (err) {
      expect(err).toBeInstanceOf(TierError);
      const tier = err as TierError;
      expect(tier.status).toBe(403);
      if (tier.body.error === "feature_gated") {
        expect(tier.body.feature).toBe("dreams");
        expect(tier.body.required_tier).toBe("Pro");
      }
    }
  });

  it("falls back to a generic Error for non-tier 4xx responses", async () => {
    mockFetch({ detail: "not found" }, { status: 404 });
    await expect(api.health()).rejects.toBeInstanceOf(Error);
    await expect(api.health()).rejects.not.toBeInstanceOf(TierError);
  });

  it("falls back to a generic Error when a 403 body lacks tier shape", async () => {
    // Hide-settings 403 from PUT /api/config does not match the tier
    // structure — it must surface as a plain error so the caller doesn't
    // mistakenly render an upgrade modal.
    mockFetch({ detail: "Settings are read-only in this deployment." }, { status: 403 });
    await expect(api.health()).rejects.not.toBeInstanceOf(TierError);
  });
});
