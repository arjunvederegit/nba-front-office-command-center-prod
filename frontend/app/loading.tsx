/**
 * Route-level loading boundary.
 *
 * Every page in Pivot opens the same way: a lit rail, a condensed title, a strip
 * of scoreboard numbers, then panels. This draws that shape while the route
 * streams in, so a slow page reads as the page arriving rather than as a spinner
 * that says only "wait".
 *
 * Deliberately inert — no fetching, no providers, no client state. A loading
 * boundary that can itself fail is worse than none.
 */

import { Skeleton } from "@/components/ui";

function PanelSkeleton({ rows = 4, className }: { rows?: number; className?: string }) {
  return (
    <div className={`panel ${className ?? ""}`}>
      <div className="border-b border-hairline px-4 py-3">
        <Skeleton className="h-4 w-40 max-w-full" />
        <Skeleton className="mt-2 h-3 w-64 max-w-full" />
      </div>
      <div className="space-y-2 p-4">
        {Array.from({ length: rows }).map((_, i) => (
          <Skeleton key={i} className="h-11" />
        ))}
      </div>
    </div>
  );
}

export default function Loading() {
  return (
    <div role="status" aria-busy="true" aria-live="polite">
      <span className="sr-only">Loading this view.</span>

      {/* Header rail — the same lit edge and title block PageHeader renders. */}
      <header className="mb-5">
        <div
          className="h-px w-full"
          style={{ background: "linear-gradient(90deg, var(--signal), transparent 60%)" }}
        />
        <div className="flex flex-wrap items-end justify-between gap-x-6 gap-y-3 pt-3">
          <div className="min-w-0 flex-1">
            <Skeleton className="h-2.5 w-24" />
            <Skeleton className="mt-2 h-8 w-72 max-w-full" />
            <Skeleton className="mt-2.5 h-3.5 w-[34rem] max-w-full" />
          </div>
          <div className="eyebrow flex shrink-0 items-center gap-2" aria-hidden>
            <span className="pulse-live h-1.5 w-1.5 rounded-full bg-signal" />
            Loading
          </div>
        </div>
      </header>

      {/* Scoreboard strip. */}
      <div className="mb-5 grid grid-cols-2 gap-3 sm:grid-cols-4">
        {Array.from({ length: 4 }).map((_, i) => (
          <div key={i} className="panel p-4">
            <Skeleton className="h-2.5 w-16" />
            <Skeleton className="mt-2 h-7 w-20 max-w-full" />
            <Skeleton className="mt-2 h-2.5 w-24 max-w-full" />
          </div>
        ))}
      </div>

      {/* Body: one wide column of detail, one narrower rail. */}
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        <PanelSkeleton rows={6} className="lg:col-span-2" />
        <PanelSkeleton rows={4} />
      </div>
    </div>
  );
}
