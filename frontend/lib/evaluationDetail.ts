/**
 * Reading a typed section out of an evaluation's `detail` bag.
 *
 * The backend returns `detail` as an open map of section name to payload — performance,
 * fit, risk, assets, timeline, roster_shape — because the set of sections is a property of
 * what could be computed for that trade rather than a fixed shape. An absent section is
 * absent, never null-filled, so every reader needs the same "what is there, as the type I
 * expect" accessor and none of them should reimplement it.
 *
 * The empty-object fallback is deliberate: a panel for a section the backend did not
 * compute renders its own unavailable state from the fields it finds missing, which is
 * what every one of them already does for a partially-computed section.
 */
export function sectionOf<T>(
  detail: Record<string, Record<string, unknown>> | undefined,
  key: string,
): T {
  return (detail?.[key] ?? {}) as T;
}
