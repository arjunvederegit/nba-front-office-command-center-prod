import type { Metadata } from "next";
import Link from "next/link";
import { PageHeader, Panel } from "@/components/ui";

export const metadata: Metadata = { title: "About — RosterLab" };

const TOOLS: { name: string; href: string; blurb: string }[] = [
  {
    name: "Team Outlook",
    href: "/team-outlook",
    blurb:
      "roster with photos, model-derived strengths and needs, competitive window, payroll status.",
  },
  {
    name: "Trade Evaluator",
    href: "/trade-evaluator",
    blurb:
      "2–3-team construction with live backend rules checks, fan verdicts, and advanced analytics behind progressive disclosure.",
  },
  {
    name: "Strategy Lab",
    href: "/strategy-lab",
    blurb:
      "saved deals side by side with live priority re-weighting, Pareto frontier, and rank-stability analysis.",
  },
  {
    name: "Player Explorer",
    href: "/player-explorer",
    blurb:
      "imported 2025-26 player stat lines with photos, per-game derivations, percentiles and multi-player comparison.",
  },
  {
    name: "Salary-Cap Center",
    href: "/salary-cap-center",
    blurb:
      "payroll by season from imported contract snapshots; fully honest empty state until contracts are imported.",
  },
];

export default function AboutPage() {
  return (
    <div className="mx-auto max-w-3xl space-y-4">
      <PageHeader
        eyebrow="The project"
        title="About RosterLab"
        lede="An NBA front-office simulator built as a portfolio project — structured decision-making under real constraints, with data honesty as the core design value."
      />

      <Panel title="The problem it structures">
        <p className="text-sm leading-relaxed text-muted">
          &quot;Should we make this trade?&quot; is an ambiguous, multi-objective question: on-court
          value, cap law, roster fit, timelines, risk and optionality all pull in different
          directions, and the right answer depends on strategy. RosterLab makes the frame explicit —
          pick a team and a strategy, build against real rosters, get an honest rules check and an
          explainable multi-component evaluation with uncertainty, then stress-test the conclusion.
          It&apos;s a decision-support simulator for exploration, not a replacement for a front
          office.
        </p>
      </Panel>

      <Panel title="The tool suite">
        <ul className="space-y-2.5">
          {TOOLS.map((tool) => (
            <li key={tool.name} className="flex gap-2.5">
              <span aria-hidden className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-signal" />
              <span className="min-w-0 text-sm leading-relaxed text-muted">
                <Link
                  href={tool.href}
                  className="title-md whitespace-nowrap text-foreground underline decoration-hairline underline-offset-4 transition-colors hover:text-signal"
                >
                  {tool.name}
                </Link>{" "}
                — {tool.blurb}
              </span>
            </li>
          ))}
          <li className="flex gap-2.5">
            <span aria-hidden className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-unavail" />
            <span className="min-w-0 text-sm leading-relaxed text-muted">
              <span className="title-md whitespace-nowrap text-foreground">Contract Predictor</span>{" "}
              — deliberately not shipped: it needs historical contract data before a validated model
              can exist, and RosterLab doesn&apos;t ship fake models.
            </span>
          </li>
        </ul>
      </Panel>

      <Panel title="Architecture">
        <pre className="scroll-thin overflow-x-auto rounded-md border border-hairline bg-panel2 p-3 font-mono text-xs leading-relaxed text-foreground">
{`Next.js 16 (this UI) ── /api/v1 ──> FastAPI
                                     ├─ CBA rules engine (four-state honesty standard)
                                     ├─ Evaluation (6 components + Monte Carlo + sensitivity)
                                     ├─ Analytics (TEI, archetypes, needs, projections)
                                     ├─ SQLAlchemy + Alembic (32 tables, full provenance)
                                     ├─ Media asset manifest (photos/logos by NBA id)
                                     └─ Integrations
                                        ├─ nba_api  ←  NBA.com (rate-limited, circuit-broken)
                                        ├─ user CSV totals import (PLAYER_ID-keyed)
                                        ├─ Kaggle basketball DB (NULL-fill enrichment)
                                        └─ Basketball-Reference contracts snapshot parser`}
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
          for what is currently ingested. RosterLab is independent and not affiliated with the NBA;
          team marks and player images are used locally for identification.
        </p>
      </Panel>
    </div>
  );
}
