"use client";

import { useMutation, useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { useState } from "react";
import { api } from "@/lib/api";
import { COMPONENT_LABEL, LEGALITY_LABEL, money } from "@/lib/format";
import type { ComparisonResponse, Scenario, TradeSummary } from "@/lib/types";
import { FirstPlaceShareBars, ParetoScatter } from "@/components/charts";
import { Badge, Card, EmptyState, ErrorState, Spinner, Td, Th } from "@/components/ui";

const COMPONENT_KEYS = ["performance", "fit", "contract", "timeline", "assets", "risk"];

export default function ComparePage() {
  const { data: trades } = useQuery({
    queryKey: ["trades"],
    queryFn: () => api.get<TradeSummary[]>("/trades"),
  });
  const { data: scenarios } = useQuery({
    queryKey: ["scenarios"],
    queryFn: () => api.get<Scenario[]>("/scenarios"),
  });
  const [selected, setSelected] = useState<string[]>([]);
  const [scenarioId, setScenarioId] = useState<string>("");
  const [comparison, setComparison] = useState<ComparisonResponse | null>(null);

  const compare = useMutation({
    mutationFn: () =>
      api.post<ComparisonResponse>("/comparisons", {
        name: `Comparison of ${selected.length}`,
        scenario_id: scenarioId || null,
        trade_ids: selected,
      }),
    onSuccess: setComparison,
  });

  function toggle(id: string) {
    setSelected((s) =>
      s.includes(id) ? s.filter((x) => x !== id) : s.length < 5 ? [...s, id] : s,
    );
  }

  const names: Record<string, string> = Object.fromEntries(
    (trades ?? []).map((t) => [t.id, t.name]),
  );

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-2xl font-bold">Compare alternatives</h1>
        <p className="mt-1 text-sm text-muted">
          Select 2–5 saved trades. The comparison shows component scores, Pareto dominance, and how
          often each alternative ranks first under sampled strategy weights.
        </p>
      </div>

      <Card title="Select alternatives">
        {!trades ? (
          <Spinner />
        ) : trades.length === 0 ? (
          <EmptyState
            title="No saved trades yet"
            hint="Construct and save alternatives in the Trade Builder first."
          />
        ) : (
          <div className="space-y-3">
            <div className="grid gap-2 md:grid-cols-2">
              {trades.map((t) => (
                <label
                  key={t.id}
                  className={`flex cursor-pointer items-center gap-3 rounded-md border p-2 text-sm ${
                    selected.includes(t.id) ? "border-accent bg-accent/10" : "border-line bg-panel2"
                  }`}
                >
                  <input
                    type="checkbox"
                    checked={selected.includes(t.id)}
                    onChange={() => toggle(t.id)}
                    className="accent-sky-400"
                  />
                  <span className="flex-1">{t.name}</span>
                  <span className="text-xs text-muted">
                    {t.teams.join("↔")} · {t.n_players}p{t.n_picks ? ` +${t.n_picks}pk` : ""}
                  </span>
                </label>
              ))}
            </div>
            <div className="flex items-center gap-2">
              <select
                value={scenarioId}
                onChange={(e) => setScenarioId(e.target.value)}
                className="rounded-md border border-line bg-panel2 px-2 py-1.5 text-sm"
                aria-label="Scenario for weights"
              >
                <option value="">Default weights (no scenario)</option>
                {scenarios?.map((s) => (
                  <option key={s.id} value={s.id}>
                    weights from: {s.name}
                  </option>
                ))}
              </select>
              <button
                type="button"
                disabled={selected.length < 2 || compare.isPending}
                onClick={() => compare.mutate()}
                className="rounded-md bg-accent px-4 py-2 text-sm font-semibold text-background hover:brightness-110 disabled:opacity-40"
              >
                {compare.isPending ? "Comparing…" : `Compare ${selected.length} alternatives`}
              </button>
            </div>
            {compare.isError && <ErrorState message={String(compare.error)} />}
          </div>
        )}
      </Card>

      {comparison && (
        <>
          <Card title="Comparison table" subtitle={comparison.note}>
            <div className="scroll-thin overflow-x-auto">
              <table className="w-full min-w-[820px]">
                <thead>
                  <tr className="border-b border-line">
                    <Th>Alternative</Th>
                    <Th>Legality</Th>
                    <Th className="text-right">Utility</Th>
                    <Th className="text-right">Δ wins (med)</Th>
                    {COMPONENT_KEYS.map((k) => (
                      <Th key={k} className="text-right">
                        {COMPONENT_LABEL[k]?.split(" ")[0]}
                      </Th>
                    ))}
                    <Th className="text-right">Payroll after</Th>
                    <Th>Pareto</Th>
                  </tr>
                </thead>
                <tbody>
                  {comparison.alternatives.map((alt) => (
                    <tr key={alt.trade_id} className="border-b border-line/50 hover:bg-panel2">
                      <Td>
                        <Link href={`/trades/${alt.trade_id}`} className="hover:text-accent">
                          {alt.name}
                        </Link>
                      </Td>
                      <Td>
                        <Badge status={alt.legality_status}>
                          {LEGALITY_LABEL[alt.legality_status]}
                        </Badge>
                      </Td>
                      <Td className="text-right font-mono font-semibold">
                        {alt.composite_utility?.toFixed(1)}
                      </Td>
                      <Td className="text-right font-mono">
                        {alt.uncertainty?.median >= 0 ? "+" : ""}
                        {alt.uncertainty?.median?.toFixed(1)}
                        <span className="text-[10px] text-muted">
                          {" "}
                          [{alt.uncertainty?.p10?.toFixed(1)}, {alt.uncertainty?.p90?.toFixed(1)}]
                        </span>
                      </Td>
                      {COMPONENT_KEYS.map((k) => (
                        <Td key={k} className="text-right font-mono">
                          {alt.components[k] !== null && alt.components[k] !== undefined ? (
                            Number(alt.components[k]).toFixed(0)
                          ) : (
                            <span className="text-unavail">n/a</span>
                          )}
                        </Td>
                      ))}
                      <Td className="text-right font-mono">{money(alt.payroll_after)}</Td>
                      <Td>
                        {alt.dominated_by ? (
                          <Badge status="unavailable">dominated</Badge>
                        ) : (
                          <Badge status="pass">frontier</Badge>
                        )}
                      </Td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Card>

          <div className="grid gap-4 lg:grid-cols-2">
            <Card
              title="Pareto view"
              subtitle="performance vs risk-adjusted score · grey points are dominated"
            >
              <ParetoScatter
                points={comparison.alternatives.map((a) => ({
                  name: a.name,
                  x: a.components.performance ?? 0,
                  y: a.components.risk ?? 0,
                  dominated: !!a.dominated_by,
                }))}
              />
            </Card>
            <Card
              title="Rank stability"
              subtitle={`share of ${comparison.sensitivity ? 500 : 0} sampled weight vectors in which each alternative ranks #1`}
            >
              <FirstPlaceShareBars
                share={comparison.sensitivity.first_place_share}
                names={names}
              />
              <p className="mt-2 text-[11px] text-muted">
                Rank volatility (std of rank):{" "}
                {Object.entries(comparison.sensitivity.rank_volatility)
                  .map(([id, v]) => `${names[id] ?? id.slice(0, 6)}: ${v.toFixed(2)}`)
                  .join(" · ")}
              </p>
            </Card>
          </div>
        </>
      )}
    </div>
  );
}
