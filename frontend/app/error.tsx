"use client";

/**
 * Route-level error boundary.
 *
 * The honesty standard applies to failure too: say what happened, say what it
 * does not tell you, and offer the next step. It never prints a stack trace at
 * the reader — `error.message` is shown because it is often specific enough to
 * be useful, and `error.digest` is shown because that is the one string a
 * developer needs to find this exact failure in the server logs.
 *
 * No fetching and no query client here — a boundary that can fail while
 * recovering is worse than none.
 */

import { BallGlyph } from "@/components/court";
import { Button, ButtonLink, Panel } from "@/components/ui";

export default function RouteError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  const detail = error.message?.trim();

  return (
    <div className="mx-auto max-w-2xl py-10">
      <Panel accent="var(--illegal)" padded={false}>
        <div className="px-5 py-6 sm:px-7 sm:py-8">
          <div className="eyebrow flex items-center gap-2 text-illegal">
            <BallGlyph size={13} />
            Error
          </div>

          <h1 className="title-lg mt-2 text-foreground">This view did not load</h1>

          <p className="mt-3 text-sm leading-relaxed text-muted">
            Something failed while this page was being built, so Pivot stopped instead of
            showing a partial view. Nothing was changed by the attempt, and the rest of the
            app is unaffected — the other sections still load normally.
          </p>

          {detail && (
            <div className="mt-4 rounded-lg border border-illegal/35 bg-illegal/8 px-3.5 py-3">
              <div className="eyebrow text-[0.625rem] text-illegal">What failed</div>
              <p className="data mt-1.5 break-words text-[12px] leading-relaxed text-foreground">
                {detail}
              </p>
            </div>
          )}

          <div className="mt-5 flex flex-wrap items-center gap-2">
            <Button variant="primary" onClick={() => reset()}>
              Try again
            </Button>
            <ButtonLink href="/" variant="secondary">
              Back to Command Center
            </ButtonLink>
          </div>

          <p className="mt-4 text-[12px] leading-relaxed text-faint">
            Trying again re-runs the page. If it fails the same way twice, the cause is
            upstream of the browser — usually the API being unreachable or a record the
            page needs not being imported yet. Data Health reports which sources are
            currently loaded.
          </p>

          {error.digest && (
            <div className="mt-4 flex flex-wrap items-center gap-x-2 gap-y-1 border-t border-hairline pt-3 text-[11px] text-faint">
              <span className="font-mono text-[10px] uppercase tracking-wider">digest</span>
              <span className="data text-muted">{error.digest}</span>
              <span aria-hidden>·</span>
              <span>quote this when reporting the failure</span>
            </div>
          )}
        </div>
      </Panel>
    </div>
  );
}
