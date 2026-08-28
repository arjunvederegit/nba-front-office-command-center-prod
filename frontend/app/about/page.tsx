import type { Metadata } from "next";
import Link from "next/link";
import { PageHeader, Panel } from "@/components/ui";

export const metadata: Metadata = { title: "About — Pivot" };

// R5 and R6 shipped three surfaces an earlier version of this page never mentioned —
// comparable trades, need-driven acquisition and the decision memo. Each one now sits at
// the stage of the decision it actually serves, rather than at the end of a flat list.
const WORKFLOW: { stage: string; blurb: string; surfaces: { name: string; href: string }[] }[] = [
  {
    stage: "Observe",
    blurb:
      "what the roster is right now: players with photos, imported 2025-26 stat lines with per-game derivations, and payroll by season from imported contract snapshots — league percentiles taken only over players whose sample can support one.",
    surfaces: [
      { name: "Team Outlook", href: "/team-outlook" },
      { name: "Player Explorer", href: "/player-explorer" },
      { name: "Salary-Cap Center", href: "/salary-cap-center" },
    ],
  },
  {
    stage: "Diagnose",
    blurb:
      "what that roster is short of and what it already does well — model-derived strengths and needs, competitive window, and payroll status that stays fully empty until contracts are imported.",
    surfaces: [{ name: "Team Outlook", href: "/team-outlook" }],
  },
  {
    stage: "Compare",
    blurb:
      "the completed trades a proposal most resembles, retrieved from ten seasons of Basketball-Reference transaction pages — evidence rather than model output — alongside multi-player comparison.",
    surfaces: [
      { name: "Comparable trades", href: "/trade-evaluator" },
      { name: "Player Explorer", href: "/player-explorer" },
    ],
  },
  {
    stage: "Simulate",
    blurb:
      "2–3-team construction with live backend rules checks, fan verdicts, and advanced analytics behind progressive disclosure.",
    surfaces: [{ name: "Trade Evaluator", href: "/trade-evaluator" }],
  },
  {
    stage: "Recommend",
    blurb:
      "saved deals side by side with live priority re-weighting, Pareto frontier and rank-stability analysis; and acquisition candidates that start from the diagnosed shortfall, keep only players who actually improve the roster, and rank by projected wins — each one run through the trade evaluator before it is shown.",
    surfaces: [
      { name: "Strategy Lab", href: "/strategy-lab" },
      { name: "Team Outlook", href: "/team-outlook" },
    ],
  },
  {
    stage: "Explain",
    blurb:
      "the evaluation as a reviewable artifact, including an explicit list of what is not known about the deal. Exportable from a saved trade.",
    surfaces: [{ name: "Decision memo", href: "/trade-evaluator" }],
  },
];

export default function AboutPage() {
  return (
    <div className="mx-auto max-w-3xl space-y-4">
      <PageHeader
        eyebrow="The project"
        title="About Pivot"
        lede="A basketball decision-intelligence system built as a portfolio project — structured decision-making under real constraints, with data honesty as the core design value."
      />

      <Panel title="The problem it structures">
        <p className="text-sm leading-relaxed text-muted">
          &quot;Should we make this trade?&quot; is an ambiguous, multi-objective question: on-court
          value, cap law, roster fit, timelines, risk and optionality all pull in different
          directions, and the right answer depends on strategy. Pivot makes the frame explicit —
          pick a team and a strategy, build against real rosters, get an honest rules check and an
          explainable multi-component evaluation with uncertainty, then stress-test the conclusion.
          It&apos;s a decision-support system for exploration, not a replacement for a front office.
        </p>
      </Panel>

      <Panel title="The decision workflow">
        <p className="mb-3 text-sm leading-relaxed text-muted">
          Pivot is one system rather than a suite of separate tools. The same evaluation runs
          underneath every screen, and the screens are stages of a single decision:
        </p>
        <ul className="space-y-2.5">
          {WORKFLOW.map((step) => (
            <li key={step.stage} className="flex gap-2.5">
              <span aria-hidden className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-signal" />
              <span className="min-w-0 text-sm leading-relaxed text-muted">
                <span className="title-md whitespace-nowrap text-foreground">{step.stage}</span> —{" "}
                {step.blurb}
                <span className="mt-0.5 block text-xs text-faint">
                  In{" "}
                  {step.surfaces.map((surface, i) => (
                    <span key={surface.name}>
                      {i > 0 ? ", " : ""}
                      <Link
                        href={surface.href}
                        className="whitespace-nowrap text-muted underline decoration-hairline underline-offset-4 transition-colors hover:text-signal"
                      >
                        {surface.name}
                      </Link>
                    </span>
                  ))}
                </span>
              </span>
            </li>
          ))}
          <li className="flex gap-2.5">
            <span aria-hidden className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-unavail" />
            <span className="min-w-0 text-sm leading-relaxed text-muted">
              <span className="title-md whitespace-nowrap text-foreground">Contract Predictor</span>{" "}
              — deliberately not shipped: it needs historical contract data before a validated model
              can exist, and Pivot doesn&apos;t ship fake models.
            </span>
          </li>
        </ul>
      </Panel>

      <Panel title="Architecture">
        <pre className="scroll-thin overflow-x-auto rounded-md border border-hairline bg-panel2 p-3 font-mono text-xs leading-relaxed text-foreground">
{`Next.js 16 (this UI) ── /api/v1 ──> FastAPI
                                     ├─ CBA rules engine (four-state honesty standard)
                                     ├─ Evaluation (6 components + Monte Carlo + sensitivity)
                                     ├─ Analytics (TEI, archetypes, needs, projections,
                                     │             rotation allocator, pick valuation)
                                     ├─ Comparable-trade retrieval (10 seasons, side-level)
                                     ├─ SQLAlchemy + Alembic (35 tables, full provenance)
                                     ├─ Media asset manifest (photos/logos by NBA id)
                                     └─ Integrations
                                        ├─ nba_api  ←  NBA.com (rate-limited, circuit-broken)
                                        ├─ user CSV totals import (PLAYER_ID-keyed)
                                        ├─ Kaggle basketball DB (NULL-fill enrichment)
                                        ├─ Basketball-Reference contracts snapshot parser
                                        ├─ Basketball-Reference transaction pages (trades)
                                        └─ RealGM future-drafts snapshot (pick ownership)`}
        </pre>
      </Panel>

      <Panel title="Data honesty, by design" accent="var(--legal)">
        <ul className="space-y-2">
          {[
            "No synthetic NBA data in production paths — fixtures live only in test directories.",
            "Missing data is an explicit state: a trade is never called legal from partial checks, absent salaries are never estimated, unmatched images are kept for review instead of guessed.",
            "Every provider-derived record stores provider, endpoint/file, timestamps and run id; sources that disagree are logged, not silently overwritten.",
            "Every screen shows source and freshness; Data Health reports what's missing in plain language.",
          ].map((line) => (
            <li key={line} className="flex gap-2.5 text-sm leading-relaxed text-muted">
              <span aria-hidden className="mt-0.5 shrink-0 font-mono text-legal">
                ✓
              </span>
              <span className="min-w-0">{line}</span>
            </li>
          ))}
        </ul>
      </Panel>

      <Panel title="Repository">
        <p className="text-sm leading-relaxed text-muted">
          Full source, methodology, model cards, CBA rule coverage, decision log (ADRs), identity
          resolution and deployment guide live in the repository — start with the README, then{" "}
          <code className="data text-brand">docs/architecture.md</code> and{" "}
          <code className="data text-brand">docs/methodology.md</code>. See{" "}
          <Link href="/methodology" className="text-signal underline">
            Methodology
          </Link>{" "}
          for how each number is produced, and{" "}
          <Link href="/data-health" className="text-signal underline">
            Data Health
          </Link>{" "}
          for what is currently ingested. Pivot is independent and not affiliated with the NBA;
          team marks and player images are used locally for identification.
        </p>
      </Panel>
    </div>
  );
}
