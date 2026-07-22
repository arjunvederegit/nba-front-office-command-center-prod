/**
 * Team color themes, keyed by NBA abbreviation.
 * `primary`/`secondary` are the franchise colors; `bright` is the variant chosen for
 * legible accents on the dark UI (never flood a page with these — borders, pills,
 * gradients and chart accents only).
 */
export interface TeamTheme {
  primary: string;
  secondary: string;
  bright: string;
}

export const TEAM_THEMES: Record<string, TeamTheme> = {
  ATL: { primary: "#E03A3E", secondary: "#C1D32F", bright: "#E03A3E" },
  BOS: { primary: "#007A33", secondary: "#BA9653", bright: "#00A94F" },
  BKN: { primary: "#4B5563", secondary: "#FFFFFF", bright: "#9CA3AF" },
  CHA: { primary: "#1D1160", secondary: "#00788C", bright: "#00A9C4" },
  CHI: { primary: "#CE1141", secondary: "#6B7280", bright: "#E0264F" },
  CLE: { primary: "#860038", secondary: "#FDBB30", bright: "#FDBB30" },
  DAL: { primary: "#00538C", secondary: "#B8C4CA", bright: "#2E8FD6" },
  DEN: { primary: "#0E2240", secondary: "#FEC524", bright: "#FEC524" },
  DET: { primary: "#C8102E", secondary: "#1D42BA", bright: "#E23A50" },
  GSW: { primary: "#1D428A", secondary: "#FFC72C", bright: "#FFC72C" },
  HOU: { primary: "#CE1141", secondary: "#9EA2A2", bright: "#E0264F" },
  IND: { primary: "#002D62", secondary: "#FDBB30", bright: "#FDBB30" },
  LAC: { primary: "#C8102E", secondary: "#1D428A", bright: "#E0264F" },
  LAL: { primary: "#552583", secondary: "#FDB927", bright: "#FDB927" },
  MEM: { primary: "#5D76A9", secondary: "#12173F", bright: "#7D96C9" },
  MIA: { primary: "#98002E", secondary: "#F9A01B", bright: "#F9A01B" },
  MIL: { primary: "#00471B", secondary: "#EEE1C6", bright: "#0A8A3E" },
  MIN: { primary: "#0C2340", secondary: "#78BE20", bright: "#78BE20" },
  NOP: { primary: "#0C2340", secondary: "#C8102E", bright: "#D3A44E" },
  NYK: { primary: "#006BB6", secondary: "#F58426", bright: "#F58426" },
  OKC: { primary: "#007AC1", secondary: "#EF3B24", bright: "#2FA3E8" },
  ORL: { primary: "#0077C0", secondary: "#C4CED4", bright: "#2FA0E0" },
  PHI: { primary: "#006BB6", secondary: "#ED174C", bright: "#2E93DE" },
  PHX: { primary: "#1D1160", secondary: "#E56020", bright: "#E56020" },
  POR: { primary: "#E03A3E", secondary: "#8F8F8F", bright: "#E03A3E" },
  SAC: { primary: "#5A2D81", secondary: "#63727A", bright: "#8B5CC0" },
  SAS: { primary: "#6B7280", secondary: "#C4CED4", bright: "#C4CED4" },
  TOR: { primary: "#CE1141", secondary: "#A1A1A4", bright: "#E0264F" },
  UTA: { primary: "#002B5C", secondary: "#F9A01B", bright: "#F9A01B" },
  WAS: { primary: "#002B5C", secondary: "#E31837", bright: "#E85A6B" },
};

const NEUTRAL: TeamTheme = { primary: "#334155", secondary: "#64748b", bright: "#94a3b8" };

export function teamTheme(abbreviation: string | null | undefined): TeamTheme {
  if (!abbreviation) return NEUTRAL;
  return TEAM_THEMES[abbreviation.toUpperCase()] ?? NEUTRAL;
}

/** CSS custom-property bundle for scoping team colors to a subtree. */
export function teamThemeVars(abbreviation: string | null | undefined): React.CSSProperties {
  const theme = teamTheme(abbreviation);
  return {
    "--team-primary": theme.primary,
    "--team-secondary": theme.secondary,
    "--team-bright": theme.bright,
  } as React.CSSProperties;
}

/** Favorite-team persistence (browser only), exposed as an external store so React
 * components can subscribe without setState-in-effect patterns. */
import { useSyncExternalStore } from "react";

const FAVORITE_KEY = "rosterlab.favoriteTeam";
const favoriteListeners = new Set<() => void>();

function subscribeFavorite(callback: () => void): () => void {
  favoriteListeners.add(callback);
  return () => favoriteListeners.delete(callback);
}

function favoriteSnapshot(): string | null {
  if (typeof window === "undefined") return null;
  return window.localStorage.getItem(FAVORITE_KEY);
}

export function getFavoriteTeam(): { id: string; abbreviation: string } | null {
  const raw = favoriteSnapshot();
  try {
    return raw ? (JSON.parse(raw) as { id: string; abbreviation: string }) : null;
  } catch {
    return null;
  }
}

export function useFavoriteTeam(): { id: string; abbreviation: string } | null {
  const raw = useSyncExternalStore(subscribeFavorite, favoriteSnapshot, () => null);
  try {
    return raw ? (JSON.parse(raw) as { id: string; abbreviation: string }) : null;
  } catch {
    return null;
  }
}

export function setFavoriteTeam(team: { id: string; abbreviation: string } | null): void {
  if (typeof window === "undefined") return;
  if (team === null) window.localStorage.removeItem(FAVORITE_KEY);
  else window.localStorage.setItem(FAVORITE_KEY, JSON.stringify(team));
  for (const listener of favoriteListeners) listener();
}
