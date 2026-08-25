import { describe, expect, it } from "vitest";
import {
  ALL_COLUMNS,
  COUNTING_COLUMNS,
  QUALIFY_MIN,
  RATE_COLUMNS,
  formatStat,
  percentileOf,
  qualifies,
  statValue,
} from "@/lib/playerStats";
import type { SeasonTotalsPlayer } from "@/lib/types";

function player(over: Partial<SeasonTotalsPlayer> = {}): SeasonTotalsPlayer {
  return {
    player_id: "p1",
    nba_player_id: 1,
    name: "Fixture Player",
    position: "G",
    team_abbr: "AAA",
    gp: 70,
    totals: { PTS: 1400, FGA: 900, FG3A: 400, FTA: 200, EFF: 1050 },
    per_game: { PTS: 20, EFF: 15 },
    rates: { FG_PCT: 0.48, FG3_PCT: 0.38, FT_PCT: 0.85 },
    ...over,
  };
}

const column = (key: string) => ALL_COLUMNS.find((c) => c.key === key)!;

describe("EFF is a total, not a rate (QA-11)", () => {
  it("is a counting column, so it divides by games like every other total", () => {
    expect(COUNTING_COLUMNS.map((c) => c.key)).toContain("EFF");
    expect(RATE_COLUMNS.map((c) => c.key)).not.toContain("EFF");
  });

  it("reads per_game in per-game mode and the season total in totals mode", () => {
    const p = player();
    expect(statValue(p, column("EFF"), "per_game")).toBe(15);
    expect(statValue(p, column("EFF"), "totals")).toBe(1050);
  });

  it("qualifies on games, because games are what it is summed over", () => {
    expect(qualifies(player({ gp: QUALIFY_MIN - 1 }), column("EFF"))).toBe(false);
    expect(qualifies(player({ gp: QUALIFY_MIN }), column("EFF"))).toBe(true);
  });
});

describe("the percentile population", () => {
  it("qualifies a percentage on its own attempts, not on games", () => {
    // The defect this rule exists for: 67 players sat at exactly 0 % or 100 % from three
    // on a handful of attempts, pinning both ends of the scale everyone was read against.
    const sharpshooter = player({ gp: 60, totals: { FG3A: 2 }, rates: { FG3_PCT: 1.0 } });
    expect(qualifies(sharpshooter, column("FG3_PCT"))).toBe(false);
    expect(qualifies(sharpshooter, column("PTS"))).toBe(true);
  });

  it("uses each rate column's own denominator", () => {
    const p = player({ totals: { FGA: 40, FG3A: 3, FTA: 20 } });
    expect(qualifies(p, column("FG_PCT"))).toBe(true);
    expect(qualifies(p, column("FG3_PCT"))).toBe(false);
    expect(qualifies(p, column("FT_PCT"))).toBe(true);
  });

  it("treats a missing denominator as no evidence rather than as zero games", () => {
    const p = player({ totals: {} });
    expect(qualifies(p, column("FG_PCT"))).toBe(false);
  });

  it("gives every column a denominator, so none can silently skip the rule", () => {
    // A column added without one would qualify nobody or everybody depending on how the
    // missing accessor happened to fail, and either way the bar would keep rendering.
    for (const col of ALL_COLUMNS) {
      expect(typeof col.denominator).toBe("function");
      expect(col.denominator(player())).toBeGreaterThan(0);
    }
  });
});

describe("percentileOf", () => {
  it("is the share at or below the value", () => {
    expect(percentileOf([1, 2, 3, 4], 4)).toBe(100);
    expect(percentileOf([1, 2, 3, 4], 2)).toBe(50);
  });
  it("returns 0 rather than dividing by an empty population", () => {
    expect(percentileOf([], 5)).toBe(0);
  });
});

describe("formatStat", () => {
  it("shows an em dash for a missing value instead of a zero", () => {
    expect(formatStat(null, column("PTS"), "per_game")).toBe("—");
  });
  it("rounds totals to integers and per-game to one decimal", () => {
    expect(formatStat(1400, column("PTS"), "totals")).toBe("1400");
    expect(formatStat(20.04, column("PTS"), "per_game")).toBe("20.0");
  });
  it("renders a percentage as a percentage", () => {
    expect(formatStat(0.482, column("FG_PCT"), "per_game")).toBe("48.2%");
  });
});
