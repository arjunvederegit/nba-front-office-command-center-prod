/**
 * Frontend QA pins (R0-1).
 *
 * `it.fails` is vitest's equivalent of `pytest.mark.xfail(strict=True)`: the suite is
 * green while the defect is present and turns red the moment it is fixed, so the fix
 * lands together with the removal of this marker.
 */
import { describe, expect, it } from "vitest";
import { VERDICT_LABEL, fanVerdict, tei } from "@/lib/format";

// Bucket order, best → worst. The *thresholds* are correct (C12 — do not move them);
// only the label text is inverted.
const BUCKETS: Array<keyof typeof VERDICT_LABEL> = ["strong", "mixed", "upside", "poor"];

// Words that read as an endorsement to a non-technical reader. None may appear on a
// bucket that sits below a bucket labelled with a merely-neutral word.
const POSITIVE_WORDS = ["upside", "opportunity", "promising", "win", "gain"];

describe("QA-12 — verdict labels must be monotone in the score", () => {
  it("the bucket order itself is correct: a higher score never ranks lower", () => {
    const rank = (u: number) => BUCKETS.indexOf(fanVerdict(u, "high"));
    expect(rank(72)).toBeLessThan(rank(52));
    expect(rank(52)).toBeLessThan(rank(46));
    expect(rank(46)).toBeLessThan(rank(20));
  });

  it.fails("the second-worst bucket is not labelled with a positive word", () => {
    // score 46 → "High-risk upside"; score 52 → "Mixed outcome". The worse score gets
    // the more optimistic label.
    const label = VERDICT_LABEL[fanVerdict(46, "high")].toLowerCase();
    expect(POSITIVE_WORDS.some((w) => label.includes(w))).toBe(false);
  });

  it("regression-protect: low confidence always reports 'unknown'", () => {
    expect(fanVerdict(72, "low")).toBe("unknown");
    expect(fanVerdict(null)).toBe("unknown");
  });
});

describe("§9 #9 — sign must be derived from the rounded value", () => {
  it.fails("a value that rounds to zero renders as +0.0, not -0.0", () => {
    // Draymond Green's real value: −0.0173 → rounds to 0.0 but keeps the raw sign.
    expect(tei(-0.0173)).toBe("+0.0");
  });

  it("regression-protect: genuinely negative values keep their sign", () => {
    expect(tei(-1.24)).toBe("-1.2");
    expect(tei(2.34)).toBe("+2.3");
  });
});
