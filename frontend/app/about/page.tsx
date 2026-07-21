import type { Metadata } from "next";
import { Card } from "@/components/ui";

export const metadata: Metadata = { title: "About — TradeLab" };

export default function AboutPage() {
  return (
    <div className="mx-auto max-w-3xl space-y-4">
      <div>
        <h1 className="text-2xl font-bold">About TradeLab</h1>
        <p className="mt-1 text-sm text-muted">
          A portfolio project demonstrating structured decision-making under complex constraints.
        </p>
      </div>

      <Card title="The problem it structures">
        <p className="text-sm leading-relaxed text-muted">
          &quot;Should we make this trade?&quot; is an ambiguous, multi-objective question: current
          performance, roster fit, salary-cap law, timelines, risk and optionality all pull in
          different directions. TradeLab turns it into an explicit framework — a scenario with
          strategic weights, a legality engine with an honesty standard, component scores with
          uncertainty, and sensitivity analysis that asks whether the answer survives changed
          assumptions. It is a decision-support system for exploration, not a replacement for an
          NBA front office.
        </p>
      </Card>

      <Card title="Architecture">
        <pre className="scroll-thin overflow-x-auto rounded-md border border-line bg-panel2 p-3 font-mono text-xs leading-relaxed">
{`Next.js (this UI) ── /api/v1 ──> FastAPI
                                  ├─ CBA rules engine (modular TradeRule classes)
                                  ├─ Evaluation service (6 components + MC + sensitivity)
                                  ├─ Analytics (TEI, archetypes, needs, projection)
                                  ├─ SQLAlchemy + Alembic (31 tables, full provenance)
                                  ├─ Ingestion jobs (idempotent, quality-checked)
                                  └─ integrations/nba_api  ←  NBA.com via swar/nba_api
                                     (rate limit · retry · circuit breaker · cache · schema tests)`}
        </pre>
      </Card>

      <Card title="Data honesty, by design">
        <ul className="list-disc space-y-1 pl-5 text-sm leading-relaxed text-muted">
          <li>All basketball data comes from NBA.com via <code>nba_api</code>, with provider, endpoint, timestamps and ingestion-run ID stored on every record.</li>
          <li>No synthetic NBA data exists in production paths; fixtures live only in test directories.</li>
          <li>Missing data becomes an explicit &quot;unavailable&quot; state — a trade is never labeled legal from partial validation, and absent salaries are never estimated.</li>
          <li>Every screen shows source and last-updated; stale data is badged.</li>
        </ul>
      </Card>

      <Card title="Repository">
        <p className="text-sm leading-relaxed text-muted">
          The full source, methodology, model cards, CBA rule coverage, decision log (ADRs) and
          deployment guide live in the project repository. Start with the README, then{" "}
          <code className="text-accent">docs/architecture.md</code> and{" "}
          <code className="text-accent">docs/methodology.md</code>.
        </p>
      </Card>
    </div>
  );
}
