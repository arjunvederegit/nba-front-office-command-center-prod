import { describe, expect, it } from "vitest";
import { selectStrengths, selectWeaknesses } from "@/lib/needs";
import type { TeamNeedItem } from "@/lib/types";

const need = (key: string, severity: number, percentile: number | null): TeamNeedItem => ({
  need_key: key,
  severity,
  percentile,
  explanation: `${key} fixture`,
});

/** Atlanta's shape: one strong category at zero severity, two more at zero, none pressing. */
const ATLANTA: TeamNeedItem[] = [
  need("defensive_rebounding", 0, 67),
  need("ball_security", 0, 23),
  need("defense_overall", 0, 27),
  need("three_point_volume", 0, 81),
];

const PRESSING: TeamNeedItem[] = [
  need("three_point_volume", 0.62, 19),
  need("point_of_attack_defense", 0.41, 29),
  need("rim_protection", 0.18, 41),
  need("defensive_rebounding", 0, 67),
];

describe("QA-9 — Strengths and Needs must be disjoint", () => {
  it("never lists the same category on both sides", () => {
    for (const rows of [ATLANTA, PRESSING]) {
      const strengths = new Set(selectStrengths(rows).map((n) => n.need_key));
      const weaknesses = new Set(selectWeaknesses(rows).map((n) => n.need_key));
      for (const key of weaknesses) expect(strengths.has(key)).toBe(false);
    }
  });

  it("returns no needs for a team with nothing pressing", () => {
    // The old fallback rendered the first four rows regardless of severity here.
    expect(selectWeaknesses(ATLANTA)).toHaveLength(0);
    expect(selectStrengths(ATLANTA).map((n) => n.need_key)).toEqual([
      "defensive_rebounding",
      "three_point_volume",
    ]);
  });

  it("never surfaces a zero-severity row as a need", () => {
    expect(selectWeaknesses(PRESSING).every((n) => n.severity > 0)).toBe(true);
  });

  it("caps both lists at four rows", () => {
    const many = Array.from({ length: 9 }, (_, i) => need(`k${i}`, 0.5, 10));
    expect(selectWeaknesses(many)).toHaveLength(4);
  });
});
