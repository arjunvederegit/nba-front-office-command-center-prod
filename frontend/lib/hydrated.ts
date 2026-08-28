import { useSyncExternalStore } from "react";

const subscribe = () => () => {};

/**
 * `false` during the hydration render, `true` on every render after it.
 *
 * The Command Center is a client component inside a Suspense boundary, so the shell above
 * it hydrates first and its React Query cache is already warm by the time the page
 * hydrates. A `{data && …}` branch therefore rendered *more* elements on the client than
 * the server had emitted, and React threw "Hydration failed because the server rendered
 * HTML didn't match the client" on every load of `/`.
 *
 * `useSyncExternalStore` is the supported way to say "this differs between server and
 * client": React uses the server snapshot for the hydration render, so the first client
 * render matches the HTML exactly and the real value arrives in the commit after it. Same
 * mechanism `lib/favoriteTeam.ts` uses for localStorage.
 */
export function useHydrated(): boolean {
  return useSyncExternalStore(
    subscribe,
    () => true,
    () => false,
  );
}
