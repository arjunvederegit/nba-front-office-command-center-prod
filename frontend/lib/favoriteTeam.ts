/**
 * The one team a user has chosen, shared across pages and across browser tabs.
 *
 * It is a `useSyncExternalStore` over `localStorage` rather than React state because the
 * value outlives a route change and is read by four unrelated pages. Three things about
 * this module are deliberate.
 *
 * **It listens for `storage`.** That event fires in *other* tabs when one tab writes, and
 * without it two open tabs disagreed until one of them was reloaded — the home page in a
 * background tab kept showing the previous team's colours, its shortcuts kept deep-linking
 * to that team, and nothing on screen said which tab was right. In-tab writes do not fire
 * `storage`, so both paths are needed: the local notify below, and the cross-tab listener.
 *
 * **The parsed value is cached against the raw string.** `getSnapshot` runs on every
 * render, and returning a freshly parsed object each time would hand consumers a new
 * identity every render — an effect or memo keyed on it would never settle. Parsing once
 * per distinct raw string makes the identity as stable as the value.
 *
 * **Every `localStorage` access is guarded.** It throws rather than returning null when
 * storage is unavailable — Safari's private mode, a disabled-cookies profile, some
 * embedded webviews — and an uncaught throw inside `getSnapshot` takes the whole page
 * down. A user who cannot persist a favourite should lose the favourite, not the app.
 */

import { useSyncExternalStore } from "react";

export interface FavoriteTeam {
  id: string;
  abbreviation: string;
}

const FAVORITE_KEY = "rosterlab.favoriteTeam";
const listeners = new Set<() => void>();

/** Cache of the last raw string and what it parsed to, for snapshot identity stability. */
let cachedRaw: string | null = null;
let cachedValue: FavoriteTeam | null = null;

function readRaw(): string | null {
  if (typeof window === "undefined") return null;
  try {
    return window.localStorage.getItem(FAVORITE_KEY);
  } catch {
    return null;
  }
}

function notify(): void {
  for (const listener of listeners) listener();
}

function subscribe(callback: () => void): () => void {
  listeners.add(callback);
  if (listeners.size === 1 && typeof window !== "undefined") {
    window.addEventListener("storage", onStorage);
  }
  return () => {
    listeners.delete(callback);
    if (listeners.size === 0 && typeof window !== "undefined") {
      window.removeEventListener("storage", onStorage);
    }
  };
}

function onStorage(event: StorageEvent): void {
  // `key === null` is a whole-storage clear, which is also a change to this key.
  if (event.key !== null && event.key !== FAVORITE_KEY) return;
  notify();
}

function snapshot(): FavoriteTeam | null {
  const raw = readRaw();
  if (raw === cachedRaw) return cachedValue;
  cachedRaw = raw;
  try {
    const parsed = raw ? (JSON.parse(raw) as Partial<FavoriteTeam>) : null;
    cachedValue =
      parsed && typeof parsed.id === "string" && typeof parsed.abbreviation === "string"
        ? { id: parsed.id, abbreviation: parsed.abbreviation }
        : null;
  } catch {
    // A malformed entry — hand-edited, or written by an older shape — is treated as no
    // favourite rather than crashing the page that reads it.
    cachedValue = null;
  }
  return cachedValue;
}

/** The server render, and any render before hydration, has no favourite. */
function serverSnapshot(): FavoriteTeam | null {
  return null;
}

export function getFavoriteTeam(): FavoriteTeam | null {
  return snapshot();
}

export function useFavoriteTeam(): FavoriteTeam | null {
  return useSyncExternalStore(subscribe, snapshot, serverSnapshot);
}

export function setFavoriteTeam(team: FavoriteTeam | null): void {
  if (typeof window === "undefined") return;
  try {
    if (team === null) window.localStorage.removeItem(FAVORITE_KEY);
    else window.localStorage.setItem(FAVORITE_KEY, JSON.stringify(team));
  } catch {
    // Storage is unavailable. The choice does not persist; the rest of the session still
    // works, and notifying keeps this tab consistent with what the user just clicked.
  }
  // `storage` does not fire in the tab that wrote, so this tab is told directly.
  notify();
}
