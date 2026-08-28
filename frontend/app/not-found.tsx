/**
 * Route-level not-found boundary.
 *
 * A 404 is a real answer, not a failure, so it is designed like one: the ball on
 * an empty court, a plain statement of what happened, and the four destinations a
 * reader actually wants next. It states the two ordinary causes — a mistyped
 * address, or an id that matches nothing in the imported data — rather than
 * implying the app is broken.
 *
 * Server component by design: no fetching, no client state, nothing that can
 * fail a second time.
 */

import Link from "next/link";
import { BallGlyph, HalfCourt } from "@/components/court";
import { ButtonLink } from "@/components/ui";

const DESTINATIONS: { href: string; label: string; hint: string }[] = [
  { href: "/", label: "Command Center", hint: "League state, your team, and what changed" },
  { href: "/player-explorer", label: "Players", hint: "Stat lines, percentiles and comparison" },
  { href: "/team-outlook", label: "Teams", hint: "Roster, strengths, needs and payroll" },
  { href: "/trade-evaluator", label: "Trade Evaluator", hint: "Build a deal and test it" },
];

export default function NotFound() {
  return (
    <div className="mx-auto max-w-3xl py-8">
      {/* Hero: the ball, alone on an empty half-court. */}
      <section className="court-grid relative overflow-hidden rounded-xl border border-hairline px-6 py-10 text-center">
        <HalfCourt className="pointer-events-none absolute inset-x-0 bottom-0 mx-auto h-40 w-[26rem] max-w-full text-signal/15" />
        <div className="relative">
          <BallGlyph size={30} className="mx-auto text-brand" />
          <div className="numeral mt-3 text-[3.25rem] leading-none text-foreground">404</div>
          <div className="eyebrow mt-2">Page not found</div>

          <p className="mx-auto mt-4 max-w-xl text-sm leading-relaxed text-muted">
            There is no page at this address. Two things usually cause it: the address was
            mistyped or truncated, or it points at a player, team or trade id that does not
            exist in the data Pivot has imported. Either way nothing failed — the app has
            simply been asked for something it does not have.
          </p>

          <div className="mt-5 flex flex-wrap justify-center gap-2">
            <ButtonLink href="/" variant="primary">
              Back to Command Center
            </ButtonLink>
            <ButtonLink href="/data-health" variant="secondary">
              Check what data is loaded
            </ButtonLink>
          </div>
        </div>
      </section>

      {/* The real destinations, in workflow order. */}
      <nav aria-label="Main destinations" className="mt-6">
        <h2 className="eyebrow mb-2.5">Where to go instead</h2>
        <ul className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          {DESTINATIONS.map((destination) => (
            <li key={destination.href}>
              <Link
                href={destination.href}
                className="panel block px-4 py-3.5 transition-colors duration-150 hover:border-signal/40"
              >
                <span className="title-md text-foreground">{destination.label}</span>
                <span className="mt-1 block text-[13px] leading-relaxed text-muted">
                  {destination.hint}
                </span>
              </Link>
            </li>
          ))}
        </ul>
      </nav>

      <p className="mt-5 text-[12px] leading-relaxed text-faint">
        If you followed a link from inside Pivot to get here, the record it pointed at is no
        longer in the database. Data Health lists which sources are currently imported and
        when each was last refreshed.
      </p>
    </div>
  );
}
