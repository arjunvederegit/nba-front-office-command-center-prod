"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { use, useState } from "react";
import { api } from "@/lib/api";
import { COMPONENT_LABEL, LEGALITY_LABEL, formatDate, money } from "@/lib/format";
import type { TradeDetail } from "@/lib/types";
import { ComponentBars, TornadoChart, UncertaintyStrip } from "@/components/charts";
import { Badge, Card, ErrorState, Spinner } from "@/components/ui";

export default function TradePage({ params }: { params: Promise<{ tradeId: string }> }) {
  const { tradeId } = use(params);
  const { data: trade, error } = useQuery({
    queryKey: ["trade", tradeId],
    queryFn: () => api.get<TradeDetail>(`/trades/${tradeId}`),
  });
  const [activeTeam, setActiveTeam] = useState<string | null>(null);

  if (error) return <ErrorState message={`Could not load trade: ${String(error)}`} />;
  if (!trade) return <Spinner label="Evaluating trade…" />;

  const teamId = activeTeam ?? trade.teams[0]?.team_id;
  const evaluation = trade.evaluations[teamId];

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold">{trade.name}</h1>
          <p className="text-sm text-muted">
            {trade.teams.map((t) => t.abbreviation).join(" ↔ ")} · created{" "}
            {formatDate(trade.created_at)}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Badge status={trade.legality.overall_status} className="text-sm">
            {LEGALITY_LABEL[trade.legality.overall_status]}
          </Badge>
          <Link
            href={`/trade-builder?load=${trade.id}`}
            className="rounded-md border border-line px-3 py-1.5 text-sm hover:bg-panel"
          >
            Clone & modify
          </Link>
          <a
            href={`/api/v1/trades/${trade.id}/report`}
            target="_blank"
            className="rounded-md border border-line px-3 py-1.5 text-sm hover:bg-panel"
          >
            Report (MD)
          </a>
          <a
            href={`/api/v1/trades/${trade.id}/report?format=html`}
            target="_blank"
            className="rounded-md bg-accent px-3 py-1.5 text-sm font-semibold text-background hover:brightness-110"
          >
            Report (print)
          </a>
        </div>
      </div>

      <Card title="Assets">
        <div className="grid gap-3 md:grid-cols-2">
          {trade.teams.map((team) => {
            const receives = trade.assets.filter((a) => a.to_team_id === team.team_id);
            return (
              <div key={team.team_id} className="rounded-md border border-line bg-panel2 p-3">
                <div className="text-sm font-semibold">{team.name} receives</div>
                <ul className="mt-1 space-y-0.5 text-sm">
                  {receives.length === 0 && <li className="text-muted">nothing</li>}
                  {receives.map((a, i) => (
                    <li key={i} className="flex items-center gap-2">
                      {a.asset_type === "player" ? (
                        <Link href={`/players/${a.player_id}`} className="hover:text-accent">
                          {a.player_name}
                        </Link>
                      ) : (
                        <span>
                          {a.draft_year} round {a.round_number} pick
                        </span>
                      )}
                      {a.is_hypothetical && a.asset_type === "pick" && (
                        <Badge status="unavailable">hypothetical</Badge>
                      )}
                    </li>
                  ))}
                </ul>
              </div>
            );
          })}
        </div>
      </Card>

      <div className="flex gap-1 border-b border-line" role="tablist" aria-label="Team perspective">
        {trade.teams.map((team) => (
          <button
            key={team.team_id}
            role="tab"
            aria-selected={team.team_id === teamId}
            onClick={() => setActiveTeam(team.team_id)}
            className={`rounded-t-md px-4 py-2 text-sm ${
              team.team_id === teamId
                ? "border border-b-0 border-line bg-panel font-semibold"
                : "text-muted hover:text-foreground"
            }`}
          >
            {team.abbreviation} perspective
          </button>
        ))}
      </div>

      {evaluation && (
        <div className="grid gap-4 lg:grid-cols-2">
          <Card
            title={`Composite utility: ${evaluation.composite_utility?.toFixed(1)} / 100`}
            subtitle={`confidence: ${evaluation.confidence} · weights ${Object.entries(evaluation.weights)
              .map(([k, v]) => `${COMPONENT_LABEL[k]?.split(" ")[0] ?? k} ${(v * 100).toFixed(0)}%`)
              .join(" · ")}`}
          >
            <ComponentBars
              components={evaluation.components}
              excluded={evaluation.excluded_components}
            />
          </Card>

          <Card title="Projected wins impact (Monte Carlo)" subtitle={`${evaluation.uncertainty.n_draws} draws over impact, availability, minutes and conversion`}>
            <UncertaintyStrip u={evaluation.uncertainty} />
            <div className="mt-4 grid grid-cols-2 gap-2 text-sm">
              <div className="rounded-md border border-line bg-panel2 p-2">
                <div className="text-[11px] text-muted">Salary movement</div>
                <div className="font-mono text-sm">
                  in {money(evaluation.legality.incoming_salary)} · out{" "}
                  {money(evaluation.legality.outgoing_salary)}
                </div>
              </div>
              <div className="rounded-md border border-line bg-panel2 p-2">
                <div className="text-[11px] text-muted">Post-trade payroll / apron</div>
                <div className="font-mono text-sm">
                  {money(evaluation.legality.payroll_after)} ·{" "}
                  {evaluation.legality.apron_status_after ?? "unavailable"}
                </div>
              </div>
            </div>
          </Card>

          <Card title="Sensitivity to strategy weights" subtitle="utility range when each weight swings ±50%">
            <TornadoChart bars={evaluation.sensitivity_tornado} />
          </Card>

          <Card title="Rule-by-rule legality">
            <ul className="scroll-thin max-h-72 space-y-1.5 overflow-y-auto pr-1">
              {trade.legality.rule_results
                .filter((r) => !r.team_id || r.team_id === teamId)
                .map((r, i) => (
                  <li key={i} className="flex items-start gap-2 text-sm">
                    <Badge status={r.status} className="mt-0.5 shrink-0">
                      {r.status}
                    </Badge>
                    <div>
                      <span className="font-mono text-[11px] text-muted">{r.rule_code}</span>
                      <p className="text-xs leading-relaxed">{r.message}</p>
                      {r.source_reference && (
                        <p className="text-[10px] text-muted">ref: {r.source_reference} · confidence {r.confidence}</p>
                      )}
                    </div>
                  </li>
                ))}
            </ul>
          </Card>
        </div>
      )}
    </div>
  );
}
