import { z } from "zod";

/**
 * Runtime validation at the API boundary — the zod decision (R1-9).
 *
 * `lib/api.ts` returned `res.json() as Promise<T>`: a bare cast with no runtime check,
 * so a backend shape change rendered `undefined` on screen instead of failing. The
 * project already depended on `zod` without importing it once. The plan's instruction
 * was to *decide*: use it or delete it. It is used, deliberately narrowly.
 *
 * Scope: the responses that carry decision numbers, and only the fields a wrong shape
 * would silently corrupt. R1 changed both of these contracts and R3/R5 change them
 * again, which is exactly when an unchecked cast bites. R7 adds the comparable-trade
 * coverage block for the same reason: it changed shape in this release, and the panel
 * arithmetics on it, so a stale backend renders `undefined of undefined trades` or
 * throws inside the render rather than failing at the boundary.
 *
 * Deliberately **not** validated: everything else. A schema per endpoint would be a
 * second copy of the contract to keep in sync, and drift there would reject valid
 * responses — a worse failure than the one being prevented.
 *
 * `.passthrough()` throughout: unknown keys are additive and must never fail a client.
 */

const decisionStatus = z.enum(["scored", "suppressed_illegal", "insufficient_data"]);

const evaluatedPlayer = z
  .object({
    player_id: z.string(),
    name: z.string(),
    // Nullable on purpose: a player with no impact estimate reports null, never 0.
    tei: z.number().nullable(),
  })
  .passthrough();

const teamEvaluation = z
  .object({
    team_id: z.string(),
    decision_status: decisionStatus,
    composite_utility: z.number().nullable(),
    confidence: z.string(),
    components: z.record(z.string(), z.number().nullable()),
    excluded_components: z.array(z.string()),
    incoming: z.array(evaluatedPlayer),
    outgoing: z.array(evaluatedPlayer),
    // A suppressed evaluation carries `uncertainty: {}` — there is no distribution
    // for a deal that cannot happen — so the key is optional here and required by the
    // refinement below only when the evaluation is scored.
    uncertainty: z
      .object({ prob_positive: z.number().nullable().optional() })
      .passthrough(),
  })
  .passthrough()
  .refine(
    (e) => e.decision_status !== "scored" || e.composite_utility !== null,
    { message: "a scored evaluation must carry a composite utility" },
  )
  .refine(
    (e) => e.decision_status === "scored" || e.composite_utility === null,
    { message: "a suppressed evaluation must not carry a composite utility" },
  )
  .refine(
    (e) => e.decision_status !== "scored" || "prob_positive" in e.uncertainty,
    { message: "a scored evaluation must report prob_positive, even as null" },
  );

export const evaluateResponseSchema = z
  .object({
    legality: z.object({ overall_status: z.string() }).passthrough(),
    evaluations: z.record(z.string(), teamEvaluation),
  })
  .passthrough();

export const tradeDetailSchema = z
  .object({
    id: z.string(),
    name: z.string(),
    legality: z.object({ overall_status: z.string() }).passthrough(),
    evaluations: z.record(z.string(), teamEvaluation),
  })
  .passthrough();

const sourceCard = z
  .object({
    key: z.string(),
    title: z.string(),
    status: z.enum(["fresh", "stale", "derived", "incomplete", "unavailable", "failed"]),
  })
  .passthrough();

export const dataHealthSchema = z
  .object({
    // The product's core claim. A shape change here is how "fresh" came to be rendered
    // over six-day-old data in the first place.
    source_cards: z.array(sourceCard),
    last_successful_sync: z.string().nullable(),
    open_quality_issue_total: z.number(),
    tables: z.record(
      z.string(),
      z.object({ rows: z.number(), stale: z.boolean().nullable() }).passthrough(),
    ),
  })
  .passthrough();

/**
 * Comparable-trade coverage. **Only the coverage block**, because it is the part the
 * panel does arithmetic on — it subtracts `trades_rankable` from `trades_ingested` and
 * formats both — while the neighbours themselves are rendered field by field and a
 * missing one shows as absent rather than as a wrong number.
 *
 * `available: false` responses carry a coverage block too, so nothing here is optional
 * on the unavailable path.
 */
export const comparablesResponseSchema = z
  .object({
    available: z.boolean(),
    coverage: z
      .object({
        trades_ingested: z.number(),
        sides_rankable: z.number(),
        trades_rankable: z.number(),
        sides_blocked_by_unmodelled_players: z.number(),
        seasons_ingested: z.array(z.string()).min(1),
        calendar_backed: z.boolean(),
        note: z.string(),
      })
      .passthrough()
      // R7's own invariant. Sides come from trades, so a corpus reporting more rankable
      // trades than it ingested is a join that has gone wrong, not a bigger corpus.
      .refine((c) => c.trades_rankable <= c.trades_ingested, {
        message: "more trades are rankable than were ingested",
      })
      .refine((c) => c.sides_rankable >= c.trades_rankable, {
        message: "fewer rankable sides than rankable trades",
      }),
  })
  .passthrough();
