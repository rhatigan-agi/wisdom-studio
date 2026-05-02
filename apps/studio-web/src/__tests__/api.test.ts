import { afterEach, describe, expect, it, vi } from "vitest";
import { SessionStateError, TierError, api } from "../lib/api";

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

  it("throws SessionStateError on a 410 session_ended body", async () => {
    mockFetch(
      {
        error: "session_ended",
        agent_id: "demo",
        tokens_used: 0,
        token_cap: null,
        started_at: "2026-04-30T10:00:00+00:00",
        expires_at: "2026-04-30T10:30:00+00:00",
      },
      { status: 410 },
    );
    try {
      await api.chat("demo", "anything");
      throw new Error("expected throw");
    } catch (err) {
      expect(err).toBeInstanceOf(SessionStateError);
      const sse = err as SessionStateError;
      expect(sse.body.error).toBe("session_ended");
      expect(sse.body.agent_id).toBe("demo");
    }
  });

  it("throws SessionStateError on a 410 token_cap_reached body", async () => {
    mockFetch(
      {
        error: "token_cap_reached",
        agent_id: "demo",
        tokens_used: 50001,
        token_cap: 50000,
        started_at: "2026-04-30T10:00:00+00:00",
        expires_at: null,
      },
      { status: 410 },
    );
    await expect(api.chat("demo", "x")).rejects.toBeInstanceOf(SessionStateError);
  });

  it("falls back to a generic Error when a 410 body lacks session-ended shape", async () => {
    mockFetch({ detail: "Gone." }, { status: 410 });
    await expect(api.chat("demo", "x")).rejects.not.toBeInstanceOf(SessionStateError);
  });
});

// Insights surface — exercises the new SDK dashboard route wrappers added
// for the Insights tab. Each test pins the request URL so route drift in
// `lib/api.ts` (e.g., a stray slash or wrong base) breaks loudly.
describe("api insights surface", () => {
  function captureFetch(body: unknown): { calls: { url: string; init?: RequestInit }[] } {
    const calls: { url: string; init?: RequestInit }[] = [];
    globalThis.fetch = vi.fn(async (url: string | URL | Request, init?: RequestInit) => {
      calls.push({ url: String(url), init });
      return new Response(JSON.stringify(body), {
        status: 200,
        headers: { "content-type": "application/json" },
      });
    }) as typeof fetch;
    return { calls };
  }

  it("listDirectives hits the per-agent SDK route with include_inactive", async () => {
    const { calls } = captureFetch([]);
    await api.listDirectives("a1", true);
    expect(calls[0].url).toBe("/agents/a1/api/directives?include_inactive=true");
  });

  it("listProposals hits the pending route", async () => {
    const { calls } = captureFetch([]);
    await api.listProposals("a1");
    expect(calls[0].url).toBe("/agents/a1/api/directives/proposals/pending");
  });

  it("approveProposal POSTs to the approve route", async () => {
    const { calls } = captureFetch({ ok: true });
    await api.approveProposal("a1", "p1");
    expect(calls[0].url).toBe("/agents/a1/api/directives/proposals/p1/approve");
    expect(calls[0].init?.method).toBe("POST");
  });

  it("rejectProposal POSTs reason as JSON body", async () => {
    const { calls } = captureFetch({});
    await api.rejectProposal("a1", "p1", "noisy");
    expect(calls[0].url).toBe("/agents/a1/api/directives/proposals/p1/reject");
    expect(calls[0].init?.method).toBe("POST");
    expect(calls[0].init?.body).toBe(JSON.stringify({ reason: "noisy" }));
  });

  it("listJournals threads the limit param", async () => {
    const { calls } = captureFetch([]);
    await api.listJournals("a1", 5);
    expect(calls[0].url).toBe("/agents/a1/api/journals?limit=5");
  });

  it("dreamScheduleStatus / dreamHistory hit the dreams routes", async () => {
    const { calls } = captureFetch({});
    await api.dreamScheduleStatus("a1");
    await api.dreamHistory("a1", 3);
    expect(calls[0].url).toBe("/agents/a1/api/dreams/schedule/status");
    expect(calls[1].url).toBe("/agents/a1/api/dreams/history?limit=3");
  });

  it("runCriticAudit / criticEntropy hit the critic routes", async () => {
    const { calls } = captureFetch({});
    await api.runCriticAudit("a1");
    await api.criticEntropy("a1");
    expect(calls[0].url).toBe("/agents/a1/api/critic/audits");
    expect(calls[1].url).toBe("/agents/a1/api/critic/entropy");
  });
});
