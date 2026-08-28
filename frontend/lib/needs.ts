import type { TeamNeedItem } from "@/lib/types";

/**
 * Strength/weakness classification — **client-side fallback only. The server decides.**
 *
 * This rule is a basketball judgement, and a basketball judgement does not belong in a
 * browser: while it lived here, no backend test could reach it and every other client
 * would have had to reimplement it. It now lives in `backend/app/domain/needs.py`, is
 * applied by `IntelligenceService.team_profile` (`classify_needs` in
 * `app/services/intelligence.py`), and is served pre-applied as the `weaknesses` and
 * `strengths` arrays of `GET /api/v1/intelligence/teams/{teamId}/profile`, alongside a
 * `classification_note` that states the rule in words.
 *
 * Team Outlook reads that response and no longer calls anything in this module. What
 * remains here is a fallback for the legacy `/teams/{id}/needs` shape (`TeamNeedItem`,
 * with `need_key`/`explanation`), which the profile endpoint does not replace for callers
 * still on it.
 *
 * **The two copies of the thresholds must not drift.** `NEED_SEVERITY_THRESHOLD` and
 * `STRENGTH_PERCENTILE_THRESHOLD` below are duplicates of `NEED_SEVERITY_THRESHOLD` and
 * `STRENGTH_PERCENTILE_THRESHOLD` in `app/domain/needs.py`, and `MAX_ROWS` duplicates its
 * `HEADLINE_ROWS`. The server publishes all three at `GET /api/v1/intelligence/vocabulary`
 * under `thresholds`. If one side moves, move the other in the same change or delete this
 * module — a fallback that classifies differently from the server is worse than none.
 *
 * ---
 *
 * Partition a team's need rows into Strengths and Needs.
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
