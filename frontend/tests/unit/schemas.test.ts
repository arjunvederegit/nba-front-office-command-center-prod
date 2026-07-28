import { describe, expect, it } from "vitest";
import { dataHealthSchema, evaluateResponseSchema, tradeDetailSchema } from "@/lib/schemas";

/**
 * The zod decision (R1-9): `lib/api.ts` returned `res.json() as Promise<T>` — a bare
 * cast — while the project carried an unused `zod` dependency. These schemas guard the
 * two contracts that carry decision numbers, and these tests guard the schemas.
 */

const scored = {
  team_id: "t1",
  decision_status: "scored",
  composite_utility: 51.3,
  confidence: "medium",
  components: { performance: 52.1, fit: null },
  excluded_components: ["fit"],
  incoming: [{ player_id: "p1", name: "A", tei: 1.2 }],
  outgoing: [{ player_id: "p2", name: "B", tei: null }],
  uncertainty: { prob_positive: 0.55 },
};

// The real shape: a suppressed evaluation carries no uncertainty block at all, because
// there is no outcome distribution for a deal that cannot happen.
const suppressed = {
  ...scored,
  decision_status: "suppressed_illegal",
  composite_utility: null,
  components: { performance: null },
  uncertainty: {},
};

describe("evaluate response", () => {
  it("accepts a scored evaluation", () => {
    expect(
      evaluateResponseSchema.safeParse({
        legality: { overall_status: "conditionally_valid" },
        evaluations: { t1: scored },
      }).success,
    ).toBe(true);
  });

  it("accepts a suppressed evaluation with no score", () => {
    expect(
      evaluateResponseSchema.safeParse({
        legality: { overall_status: "verified_illegal" },
        evaluations: { t1: suppressed },
      }).success,
    ).toBe(true);
  });

  it("rejects a scored evaluation with no score", () => {
    const bad = { ...scored, composite_utility: null };
    expect(
      evaluateResponseSchema.safeParse({
        legality: { overall_status: "x" },
        evaluations: { t1: bad },
      }).success,
    ).toBe(false);
  });

  it("rejects a suppressed evaluation that still carries a score", () => {
    // This is the shape the product must never render: an affirmative number on a
    // deal that cannot be executed.
    const bad = { ...suppressed, composite_utility: 72.85 };
    expect(
      evaluateResponseSchema.safeParse({
        legality: { overall_status: "verified_illegal" },
        evaluations: { t1: bad },
      }).success,
    ).toBe(false);
  });

  it("tolerates unknown keys, so an additive backend change never breaks the client", () => {
    expect(
      evaluateResponseSchema.safeParse({
        legality: { overall_status: "x", something_new: 1 },
        evaluations: { t1: { ...scored, brand_new_field: true } },
      }).success,
    ).toBe(true);
  });

  it("requires a scored evaluation to report prob_positive, even as null", () => {
    const bad = { ...scored, uncertainty: {} };
    expect(
      evaluateResponseSchema.safeParse({ legality: { overall_status: "x" }, evaluations: { t1: bad } })
        .success,
    ).toBe(false);
  });

  it("rejects a TEI that arrived as a string", () => {
    const bad = { ...scored, incoming: [{ player_id: "p", name: "n", tei: "1.2" }] };
    expect(
      evaluateResponseSchema.safeParse({ legality: { overall_status: "x" }, evaluations: { t1: bad } })
        .success,
    ).toBe(false);
  });
});

describe("trade detail", () => {
  it("requires an id, a name and evaluations", () => {
    expect(
      tradeDetailSchema.safeParse({
        id: "x",
        name: "Deal",
        legality: { overall_status: "verified_legal" },
        evaluations: { t1: scored },
      }).success,
    ).toBe(true);
    expect(tradeDetailSchema.safeParse({ id: "x", name: "Deal" }).success).toBe(false);
  });
});

describe("data health", () => {
  const health = {
    source_cards: [{ key: "current_nba_data", title: "Current NBA data", status: "stale" }],
    last_successful_sync: "2026-07-21T02:04:24+00:00",
    open_quality_issue_total: 562,
    tables: { rosters: { rows: 530, stale: true } },
  };

  it("accepts the live shape", () => {
    expect(dataHealthSchema.safeParse(health).success).toBe(true);
  });

  it("rejects an unknown source-card status", () => {
    const bad = { ...health, source_cards: [{ key: "k", title: "t", status: "probably_fine" }] };
    expect(dataHealthSchema.safeParse(bad).success).toBe(false);
  });

  it("rejects a missing issue total, which is how a capped list hid 512 rows", () => {
    const bad: Record<string, unknown> = { ...health };
    delete bad.open_quality_issue_total;
    expect(dataHealthSchema.safeParse(bad).success).toBe(false);
  });
});
