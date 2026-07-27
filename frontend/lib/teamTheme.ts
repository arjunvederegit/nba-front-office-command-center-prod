/**
 * Compatibility shim.
 *
 * Team identity now lives in one place — `lib/teamIdentity.ts`. This module
 * re-exports the pieces older pages import, plus the favorite-team store.
 */

import { useSyncExternalStore } from "react";
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

const FAVORITE_KEY = "rosterlab.favoriteTeam";
const listeners = new Set<() => void>();

function subscribe(callback: () => void): () => void {
  listeners.add(callback);
  return () => listeners.delete(callback);
}

function snapshot(): string | null {
  if (typeof window === "undefined") return null;
  return window.localStorage.getItem(FAVORITE_KEY);
}

function parse(raw: string | null): { id: string; abbreviation: string } | null {
  try {
    return raw ? (JSON.parse(raw) as { id: string; abbreviation: string }) : null;
  } catch {
    return null;
  }
}

export function getFavoriteTeam(): { id: string; abbreviation: string } | null {
  return parse(snapshot());
}

export function useFavoriteTeam(): { id: string; abbreviation: string } | null {
  return parse(useSyncExternalStore(subscribe, snapshot, () => null));
}

export function setFavoriteTeam(team: { id: string; abbreviation: string } | null): void {
  if (typeof window === "undefined") return;
  if (team === null) window.localStorage.removeItem(FAVORITE_KEY);
  else window.localStorage.setItem(FAVORITE_KEY, JSON.stringify(team));
  for (const listener of listeners) listener();
}
