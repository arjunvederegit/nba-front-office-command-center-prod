/**
 * The Trade Evaluator's builder state, as it travels in a URL.
 *
 * One definition, because two would diverge: the acquisition panel links straight into a
 * prefilled deal, and a link built to a slightly different shape opens an empty builder
 * with no error to explain why.
 */

import type { PickMove } from "@/lib/types";

export interface ShareState {
  teamIds: string[];
  moves: Record<string, string>;
  picks: PickMove[];
  name?: string;
}

export function encodeShareState(state: ShareState): string {
  return btoa(unescape(encodeURIComponent(JSON.stringify(state))))
    .replaceAll("+", "-")
    .replaceAll("/", "_")
    .replace(/=+$/, "");
}

export function decodeShareState(raw: string): ShareState | null {
  try {
    const b64 = raw.replaceAll("-", "+").replaceAll("_", "/");
    return JSON.parse(decodeURIComponent(escape(atob(b64)))) as ShareState;
  } catch {
    return null;
  }
}

/** A link that opens the evaluator with this deal already built. */
export function evaluatorLink(state: ShareState): string {
  return `/trade-evaluator?state=${encodeShareState(state)}`;
}
