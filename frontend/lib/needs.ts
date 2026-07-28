import type { TeamNeedItem } from "@/lib/types";

/**
 * Partition a team's need rows into Strengths and Needs for Team Outlook.
 *
 * Extracted from the page so the property that matters can be asserted directly: the
 * two lists are **disjoint**. Atlanta previously showed "Defensive rebounding 67th"
 * under Strengths *and* under Needs, with a zero-length bar beneath the caption
 * "Longer bar under Needs = larger shortfall" (QA-9). The cause was a fallback that
 * rendered the first four rows in severity order regardless of severity whenever no row
 * cleared the threshold — and 135 of 279 stored rows have severity 0.
 *
 * Thresholds are unchanged from the original page; R4 re-checks them against the new
 * need distribution, since both were tuned to the current one.
 */
export const NEED_SEVERITY_THRESHOLD = 0.35;
export const STRENGTH_PERCENTILE_THRESHOLD = 65;
const MAX_ROWS = 4;

export function selectWeaknesses(needs: TeamNeedItem[]): TeamNeedItem[] {
  return needs.filter((n) => n.severity >= NEED_SEVERITY_THRESHOLD).slice(0, MAX_ROWS);
}

export function selectStrengths(needs: TeamNeedItem[]): TeamNeedItem[] {
  return needs
    .filter(
      (n) =>
        n.severity === 0 &&
        n.percentile !== null &&
        (n.percentile ?? 0) >= STRENGTH_PERCENTILE_THRESHOLD,
    )
    .slice(0, MAX_ROWS);
}
