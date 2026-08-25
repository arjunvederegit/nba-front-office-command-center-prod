/**
 * The Player Explorer's stat model: which columns exist, which bag each reads from, and
 * how big a sample a value needs before it becomes a percentile.
 *
 * Extracted from the page in R7 so the qualification rule is testable on its own. It is
 * the one rule in this surface that is easy to get quietly wrong and impossible to see
 * wrong from a screenshot — a percentile computed over the wrong population still renders
 * a perfectly convincing bar.
 */

import { pct } from "@/lib/format";
import type { SeasonTotalsPlayer } from "@/lib/types";

/** Which scale the directory is showing. Totals and per-game are never mixed in a view. */
export type Mode = "per_game" | "totals";

/**
 * Columns shown in the directory.
 *
 * `kind` decides which stat bag a value reads from. `denominator` decides whether a
 * player's sample is big enough for the value to be a measurement — see `QUALIFY_MIN`.
 */
export interface StatColumn {
  key: string;
  label: string;
  kind: "counting" | "rate";
  digits?: number;
  /** The count this column's value is an average over. Games for a per-game stat,
   *  attempts for a percentage. It is what a small sample is small *in*. */
  denominator: (p: SeasonTotalsPlayer) => number;
}

const byGames = (p: SeasonTotalsPlayer) => p.gp ?? 0;
const attempts = (key: string) => (p: SeasonTotalsPlayer) => numOrNull(p.totals?.[key]) ?? 0;

export const COUNTING_COLUMNS: StatColumn[] = [
  { key: "PTS", label: "PTS", kind: "counting", denominator: byGames },
  { key: "REB", label: "REB", kind: "counting", denominator: byGames },
  { key: "AST", label: "AST", kind: "counting", denominator: byGames },
  { key: "STL", label: "STL", kind: "counting", denominator: byGames },
  { key: "BLK", label: "BLK", kind: "counting", denominator: byGames },
  // R7 (QA-11): EFF is NBA.com's efficiency composite summed over the season — a total,
  // not a rate. It used to sit beside FG% and 3P%, so a 4-game player was compared with
  // an 82-game player on a number that grows with games played, and the per-game view
  // showed the season total unchanged. It divides by GP like every other total now.
  { key: "EFF", label: "EFF", kind: "counting", digits: 1, denominator: byGames },
];

export const RATE_COLUMNS: StatColumn[] = [
  { key: "FG_PCT", label: "FG%", kind: "rate", denominator: attempts("FGA") },
  { key: "FG3_PCT", label: "3P%", kind: "rate", denominator: attempts("FG3A") },
  { key: "FT_PCT", label: "FT%", kind: "rate", denominator: attempts("FTA") },
];

export const ALL_COLUMNS = [...COUNTING_COLUMNS, ...RATE_COLUMNS];

/**
 * How much of a column's own denominator a player needs before his value enters the
 * percentile population — and before he is shown a percentile of his own.
 *
 * One number, one sentence: **fifteen of whatever the column divides by.** Games for a
 * per-game stat, attempts for a percentage.
 *
 * It is measured on the imported season rather than chosen. Fifteen is the smallest
 * common threshold at which no rate column has a player sitting at exactly 0.000 or
 * 1.000 — the values a percentile scale is most distorted by, because they pin the top
 * and bottom of it:
 *
 * | column | players at exactly 0.000 or 1.000 | ...at >= 10 | ...at >= 15 |
 * | --- | --- | --- | --- |
 * | FG%  |  4 |  0 |  0 |
 * | 3P%  | 67 |  1 |  0 |
 * | FT%  | 52 |  0 |  0 |
 *
 * Sixty-seven players shooting exactly 0 % or 100 % from three is 11.7 % of the league
 * occupying the two ends of the scale on a handful of attempts, and every qualified
 * player's percentile was being read against them.
 *
 * A player below the line is still listed, still sortable and still comparable. What he
 * is not given is a percentile, because there is no population his sample belongs to.
 */
export const QUALIFY_MIN = 15;

export function qualifies(player: SeasonTotalsPlayer, column: StatColumn): boolean {
  return column.denominator(player) >= QUALIFY_MIN;
}

export function statValue(player: SeasonTotalsPlayer, column: StatColumn, mode: Mode): number | null {
  const bag =
    column.kind === "rate" ? player.rates : mode === "per_game" ? player.per_game : player.totals;
  const value = bag?.[column.key];
  return typeof value === "number" ? value : null;
}

export function formatStat(value: number | null, column: StatColumn, mode: Mode): string {
  if (value === null) return "—";
  if (column.kind === "rate") {
    if (column.key.endsWith("_PCT")) return pct(value, 1);
    return value.toFixed(column.digits ?? 1);
  }
  return mode === "per_game" ? value.toFixed(1) : String(Math.round(value));
}

/** Share of loaded players at or below this value (0-100). */
export function percentileOf(sortedValues: number[], value: number): number {
  if (sortedValues.length === 0) return 0;
  let lo = 0;
  let hi = sortedValues.length;
  while (lo < hi) {
    const mid = (lo + hi) >> 1;
    if (sortedValues[mid] <= value) lo = mid + 1;
    else hi = mid;
  }
  return (lo / sortedValues.length) * 100;
}

/** A stat bag holds `number | null`; anything else is absent, never zero. */
export function numOrNull(value: number | null | undefined): number | null {
  return typeof value === "number" ? value : null;
}
