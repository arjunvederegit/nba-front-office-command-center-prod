/**
 * Compatibility shim.
 *
 * Team identity now lives in `lib/teamIdentity.ts` and the favourite-team store in
 * `lib/favoriteTeam.ts`. This module only re-exports what older pages still import from
 * here; nothing is defined in it. Import from the two modules above in new code.
 */

import { TEAMS, teamIdentity, teamVars } from "@/lib/teamIdentity";
import type { TeamIdentity } from "@/lib/teamIdentity";

export type TeamTheme = Pick<TeamIdentity, "primary" | "secondary" | "bright" | "contrast">;

export const TEAM_THEMES = TEAMS;

export function teamTheme(abbreviation: string | null | undefined): TeamTheme {
  const { primary, secondary, bright, contrast } = teamIdentity(abbreviation);
  return { primary, secondary, bright, contrast };
}

export const teamThemeVars = teamVars;

/* ------------------------------------------------------- favorite team store */

// R7: the store moved to its own module. It was never part of the shim — it has its own
// storage key, its own cross-tab listener and its own lifecycle — and leaving it here
// meant every page that wanted a favourite imported a file whose docstring says it only
// exists for backwards compatibility.
export {
  getFavoriteTeam,
  setFavoriteTeam,
  useFavoriteTeam,
} from "@/lib/favoriteTeam";
export type { FavoriteTeam } from "@/lib/favoriteTeam";
