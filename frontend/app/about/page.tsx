import type { Metadata } from "next";
import { Card } from "@/components/ui";

export const metadata: Metadata = { title: "About — RosterLab" };

export default function AboutPage() {
  return (
    <div className="mx-auto max-w-3xl space-y-4">
      <div>
        <h1 className="text-2xl font-bold">About RosterLab</h1>
        <p className="mt-1 text-sm text-muted">
          An NBA front-office simulator built as a portfolio project — structured decision-making
          under real constraints, with data honesty as the core design value.
        </p>
      </div>

      <Card title="The problem it structures">
        <p className="text-sm leading-relaxed text-muted">
          &quot;Should we make this trade?&quot; is an ambiguous, multi-objective question: on-court
          value, cap law, roster fit, timelines, risk and optionality all pull in different
          directions, and the right answer depends on strategy. RosterLab makes the frame explicit —
          pick a team and a strategy, build against real rosters, get an honest rules check and an
          explainable multi-component evaluation with uncertainty, then stress-test the conclusion.
          It&apos;s a decision-support simulator for exploration, not a replacement for a front office.
        </p>
      </Card>

      <Card title="The tool suite">
        <ul className="list-disc space-y-1 pl-5 text-sm leading-relaxed text-muted">
          <li><strong>Team Hub</strong> — roster with photos, model-derived strengths/needs, competitive window, payroll status.</li>
          <li><strong>Trade Machine</strong> — 2–3-team construction with live backend rules checks, fan verdicts, and advanced analytics behind progressive disclosure.</li>
          <li><strong>Compare Deals</strong> — saved deals side by side with live priority re-weighting, Pareto frontier, and rank-stability analysis.</li>
          <li><strong>Player Lab</strong> — 573 imported 2025-26 player stat lines with photos, per-game derivations, percentiles and multi-player comparison.</li>
          <li><strong>Cap Lab</strong> — payroll by season from imported contract snapshots; fully honest empty state until contracts are imported.</li>
          <li><strong>Salary Predictor</strong> — deliberately &quot;coming soon&quot;: it needs historical contract data before a validated model can exist, and RosterLab doesn&apos;t ship fake models.</li>
        </ul>
      </Card>

      <Card title="Architecture">
        <pre className="scroll-thin overflow-x-auto rounded-md border border-line bg-panel2 p-3 font-mono text-xs leading-relaxed">
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
      </Card>

      <Card title="Data honesty, by design">
        <ul className="list-disc space-y-1 pl-5 text-sm leading-relaxed text-muted">
          <li>No synthetic NBA data in production paths — fixtures live only in test directories.</li>
          <li>Missing data is an explicit state: a trade is never called legal from partial checks, absent salaries are never estimated, unmatched images are kept for review instead of guessed.</li>
          <li>Every provider-derived record stores provider, endpoint/file, timestamps and run id; sources that disagree are logged, not silently overwritten.</li>
          <li>Every screen shows source + freshness; Data Status reports what&apos;s missing in plain language.</li>
        </ul>
      </Card>

      <Card title="Repository">
        <p className="text-sm leading-relaxed text-muted">
          Full source, methodology, model cards, CBA rule coverage, decision log (ADRs), identity
          resolution and deployment guide live in the repository — start with the README, then{" "}
          <code className="text-brand">docs/architecture.md</code> and{" "}
          <code className="text-brand">docs/methodology.md</code>. RosterLab is independent and not
          affiliated with the NBA; team marks and player images are used locally for identification.
        </p>
      </Card>
    </div>
  );
}
