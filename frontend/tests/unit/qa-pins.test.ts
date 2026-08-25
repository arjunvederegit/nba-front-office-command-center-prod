/**
 * Frontend QA pins.
 *
 * Added in R0 as `it.fails` (vitest's strict-xfail), so the suite was green while each
 * defect was present and turned red the moment it was fixed. Both were fixed in R1-9, so
 * the markers are gone and these are now ordinary regression tests.
 */
import { describe, expect, it } from "vitest";
import { VERDICT_LABEL, VERDICT_ORDER, fanVerdict, tei } from "@/lib/format";

// Bucket order, best → worst — imported rather than restated, so the test and the
// product cannot disagree about it. The *thresholds* are correct (C12 — do not move
// them); only the label text was inverted.
const BUCKETS = VERDICT_ORDER;

// Words that read as an endorsement to a non-technical reader. None may appear on a
// bucket below one labelled with a merely-neutral word.
const POSITIVE_WORDS = ["upside", "opportunity", "promising", "win", "gain"];

describe("QA-12 — verdict labels must be monotone in the score", () => {
  it("the bucket order itself is correct: a higher score never ranks lower", () => {
    const rank = (u: number) =>
      BUCKETS.indexOf(fanVerdict(u, "high") as (typeof BUCKETS)[number]);
    expect(rank(72)).toBeLessThan(rank(52));
    expect(rank(52)).toBeLessThan(rank(46));
    expect(rank(46)).toBeLessThan(rank(20));
  });

  it("the second-worst bucket is not labelled with a positive word", () => {
    // Before R1-9: score 46 → "High-risk upside" while score 52 → "Mixed outcome",
    // so the worse score carried the more optimistic label.
    const label = VERDICT_LABEL[fanVerdict(46, "high")].toLowerCase();
    expect(POSITIVE_WORDS.some((w) => label.includes(w))).toBe(false);
  });

  it("every scored bucket has a distinct label", () => {
    const labels = BUCKETS.map((b) => VERDICT_LABEL[b]);
    expect(new Set(labels).size).toBe(labels.length);
  });

  it("regression-protect: low confidence always reports 'unknown'", () => {
    expect(fanVerdict(72, "low")).toBe("unknown");
    expect(fanVerdict(null)).toBe("unknown");
  });
});

describe("§9 #9 — sign must be derived from the rounded value", () => {
  it("a value that rounds to zero renders as +0.0, not -0.0", () => {
    // Draymond Green's real value: −0.0173 rounds to 0.0 but used to keep the raw
    // sign. 27 players rendered "-0.0". A negative-zero guard would not have helped:
    // in JS `-0 >= 0` is true, so a literal -0 already rendered "+0.0".
    expect(tei(-0.0173)).toBe("+0.0");
    expect(tei(-0)).toBe("+0.0");
    expect(tei(-0.04)).toBe("+0.0");
    expect(tei(-0.06)).toBe("-0.1");
  });

  it("regression-protect: genuinely negative values keep their sign", () => {
    expect(tei(-1.24)).toBe("-1.2");
    expect(tei(2.34)).toBe("+2.3");
  });
});
