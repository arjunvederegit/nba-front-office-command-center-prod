"use client";

/**
 * Compare Deals — a decision workspace over 2–5 saved trades.
 *
 * The backend computes component scores, Pareto dominance and weight-sampling
 * sensitivity once per comparison. On top of that this page adds an exploratory
 * "Adjust priorities" panel that re-weights the STORED component scores live on
 * the client (same renormalization rule as the backend: missing components drop
 * out and the remaining weights renormalize) — it never re-runs the models, and
 * it is labeled as exploratory next to the saved backend sensitivity.
 */

import { useMutation, useQueries, useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { useMemo, useState } from "react";
import { api } from "@/lib/api";
import {
  COMPONENT_LABEL,
  LEGALITY_LABEL,
  VERDICT_LABEL,
  fanVerdict,
  formatDate,
  money,
  pct,
} from "@/lib/format";
import { teamTheme } from "@/lib/teamTheme";
import type {
  ComparisonAlternative,
  ComparisonResponse,
  Scenario,
  TradeDetail,
  TradeSummary,
} from "@/lib/types";
import { FirstPlaceShareBars, ParetoScatter } from "@/components/charts";
import { TeamLogo } from "@/components/media";
import { useToast } from "@/components/toast";
import { Badge, Card, EmptyState, ErrorState, Td, Th } from "@/components/ui";

const COMPONENT_KEYS = ["performance", "fit", "contract", "timeline", "assets", "risk"] as const;
type ComponentKey = (typeof COMPONENT_KEYS)[number];

const MAX_SELECTED = 5;

const VERDICT_STATUS: Record<string, string> = {
  strong: "pass",
  mixed: "warning",
  upside: "info",
  poor: "fail",
  unknown: "unavailable",
};

/** Signed one-decimal number, e.g. +3.2 / -1.4. */
function signed(value: number | null | undefined): string {
  if (value === null || value === undefined) return "—";
  return `${value >= 0 ? "+" : ""}${value.toFixed(1)}`;
}

/**
 * Client-side decision score under a weight vector: sum(w_k * c_k) / sum(w_k)
 * over NON-NULL components only — the same renormalization rule the backend
 * applies when a component is unavailable.
 */
function decisionScore(
  weights: Record<string, number>,
  components: Record<string, number | null>,
): number | null {
  let numerator = 0;
  let denominator = 0;
  for (const key of COMPONENT_KEYS) {
    const component = components[key];
    const weight = weights[key] ?? 0;
    if (component !== null && component !== undefined && weight > 0) {
      numerator += weight * component;
      denominator += weight;
    }
  }
  return denominator > 0 ? numerator / denominator : null;
}

function leaderUnder(
  weights: Record<string, number>,
  alternatives: ComparisonAlternative[],
): ComparisonAlternative | null {
  let best: ComparisonAlternative | null = null;
  let bestScore = -Infinity;
  for (const alt of alternatives) {
    const score = decisionScore(weights, alt.components);
    if (score !== null && score > bestScore) {
      best = alt;
      bestScore = score;
    }
  }
  return best;
}

/** Backend weights (normalized to ~1) mapped onto 0–100 slider positions. */
function toSliderWeights(weights: Record<string, number>): Record<string, number> {
  const total = COMPONENT_KEYS.reduce((sum, key) => sum + (weights[key] ?? 0), 0);
  const out: Record<string, number> = {};
  for (const key of COMPONENT_KEYS) {
    out[key] =
      total > 0
        ? Math.round(((weights[key] ?? 0) / total) * 100)
        : Math.round(100 / COMPONENT_KEYS.length);
  }
  return out;
}

function missingComponents(alt: ComparisonAlternative): ComponentKey[] {
  return COMPONENT_KEYS.filter(
    (key) => alt.components[key] === null || alt.components[key] === undefined,
  );
}

/** Assets grouped by receiving team, for the selection cards. */
function receivedByTeam(detail: TradeDetail) {
  return detail.teams
    .map((team) => ({
      abbreviation: team.abbreviation,
      items: detail.assets
        .filter((asset) => asset.to_team_id === team.team_id)
        .map((asset) =>
          asset.asset_type === "player"
            ? (asset.player_name ?? "unknown player")
            : `${asset.draft_year ?? "future"} R${asset.round_number ?? "?"} pick${
                asset.protections ? ` (${asset.protections})` : ""
              }`,
        ),
    }))
    .filter((group) => group.items.length > 0);
}

export default function ComparePage() {
  const toast = useToast();
  const {
    data: trades,
    error: tradesError,
  } = useQuery({
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
  /** Slider positions (0–100) for the exploratory re-weighting panel. */
  const [weights, setWeights] = useState<Record<string, number>>({});

  // Details for the selected deals only (max 5), so the cards can show who goes where.
  const detailQueries = useQueries({
    queries: selected.map((id) => ({
      queryKey: ["trade", id],
      queryFn: () => api.get<TradeDetail>(`/trades/${id}`),
      staleTime: 300_000,
    })),
  });
  const detailById: Record<string, TradeDetail> = {};
  for (const q of detailQueries) if (q.data) detailById[q.data.id] = q.data;

  const compare = useMutation({
    mutationFn: () =>
      api.post<ComparisonResponse>("/comparisons", {
        name: `Comparison of ${selected.length}`,
        scenario_id: scenarioId || null,
        trade_ids: selected,
      }),
    onSuccess: (data) => {
      setComparison(data);
      setWeights(toSliderWeights(data.weights));
    },
    onError: (err) => toast("error", `Comparison failed: ${err.message}`),
  });

  function toggle(id: string) {
    if (selected.includes(id)) {
      setSelected(selected.filter((x) => x !== id));
    } else if (selected.length >= MAX_SELECTED) {
      toast("info", "You can compare at most 5 deals — deselect one first.");
    } else {
      setSelected([...selected, id]);
    }
  }

  const names: Record<string, string> = Object.fromEntries(
    (trades ?? []).map((t) => [t.id, t.name]),
  );

  const totalWeight = COMPONENT_KEYS.reduce((sum, key) => sum + (weights[key] ?? 0), 0);

  /** Live re-ranking of the stored component scores under the slider weights. */
  const ranked = useMemo(() => {
    if (!comparison) return [];
    return comparison.alternatives
      .map((alt) => ({ alt, score: decisionScore(weights, alt.components) }))
      .sort((a, b) => (b.score ?? -Infinity) - (a.score ?? -Infinity));
  }, [comparison, weights]);

  const leader = ranked.find((entry) => entry.score !== null) ?? null;

  /** Plain-English explanation for the current leader, derived only from response data. */
  const explanation = useMemo(() => {
    if (!comparison || !leader || comparison.alternatives.length < 2) return null;
    const alternatives = comparison.alternatives;
    const lead = leader.alt;

    // Components where the leader is strictly best among the compared deals.
    const strengths: { key: ComponentKey; margin: number }[] = [];
    for (const key of COMPONENT_KEYS) {
      const own = lead.components[key];
      if (own === null || own === undefined) continue;
      const others = alternatives
        .filter((a) => a.trade_id !== lead.trade_id)
        .map((a) => a.components[key])
        .filter((v): v is number => v !== null && v !== undefined);
      if (others.length === 0) continue;
      const margin = own - Math.max(...others);
      if (margin > 0) strengths.push({ key, margin });
    }
    strengths.sort((a, b) => b.margin - a.margin);
    const topStrengths = strengths.slice(0, 2).map((s) => COMPONENT_LABEL[s.key]);

    // Which single priority, doubled from its current slider position, flips the lead.
    const flips: { key: ComponentKey; newLeader: string }[] = [];
    for (const key of COMPONENT_KEYS) {
      const current = weights[key] ?? 0;
      if (current <= 0) continue;
      const doubled = { ...weights, [key]: current * 2 };
      const newLeader = leaderUnder(doubled, alternatives);
      if (newLeader && newLeader.trade_id !== lead.trade_id) {
        flips.push({ key, newLeader: newLeader.name });
      }
    }

    const nameById = Object.fromEntries(alternatives.map((a) => [a.trade_id, a.name]));
    const dominance = alternatives
      .filter((a) => a.dominated_by)
      .map(
        (a) =>
          `${a.name} is Pareto-dominated by ${
            nameById[a.dominated_by as string] ?? "another deal"
          } (never better on any displayed dimension).`,
      );

    return { lead, topStrengths, flips, dominance };
  }, [comparison, leader, weights]);

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-2xl font-bold">Compare deals</h1>
        <p className="mt-1 text-sm text-muted">
          Line up 2–5 saved trades: component scores, Pareto dominance, rank stability under
          sampled strategy weights — plus live re-weighting to stress-test the ranking yourself.
        </p>
      </div>

      <Card
        title="Pick the deals"
        subtitle="Choose 2–5 saved trades to line up side by side."
        actions={
          <span className="text-xs text-muted" aria-live="polite">
            {selected.length} of {MAX_SELECTED} selected
          </span>
        }
      >
        {tradesError ? (
          <ErrorState message={`Could not load saved trades: ${String(tradesError)}`} />
        ) : !trades ? (
          <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3" aria-hidden>
            {[0, 1, 2, 3, 4, 5].map((i) => (
              <div key={i} className="skeleton h-24" />
            ))}
          </div>
        ) : trades.length === 0 ? (
          <EmptyState
            title="No saved trades yet"
            hint="Construct and save alternatives in the Trade Machine first."
          />
        ) : (
          <div className="space-y-3">
            <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
              {trades.map((t) => {
                const isSelected = selected.includes(t.id);
                const detail = isSelected ? detailById[t.id] : undefined;
                const from = teamTheme(t.teams[0]).bright;
                const to = teamTheme(t.teams[1] ?? t.teams[0]).bright;
                return (
                  <button
                    key={t.id}
                    type="button"
                    role="checkbox"
                    aria-checked={isSelected}
                    aria-label={`${isSelected ? "Deselect" : "Select"} deal: ${t.name}`}
                    onClick={() => toggle(t.id)}
                    className={`relative overflow-hidden rounded-lg border p-3 text-left transition ${
                      isSelected
                        ? "border-brand/70 bg-brand/5"
                        : "border-line bg-panel2 hover:border-muted/60"
                    }`}
                  >
                    <span
                      aria-hidden
                      className="absolute inset-x-0 top-0 h-0.5"
                      style={{ background: `linear-gradient(90deg, ${from}, ${to})` }}
                    />
                    <span className="flex items-center gap-2">
                      <span className="flex items-center gap-1">
                        {t.teams.map((abbr) => (
                          <TeamLogo key={abbr} abbreviation={abbr} name={abbr} size={22} />
                        ))}
                      </span>
                      <span className="min-w-0 flex-1 truncate text-sm font-medium">{t.name}</span>
                      <span
                        aria-hidden
                        className={`flex h-4 w-4 shrink-0 items-center justify-center rounded-full border text-[10px] ${
                          isSelected
                            ? "border-brand bg-brand text-background"
                            : "border-line text-transparent"
                        }`}
                      >
                        ✓
                      </span>
                    </span>
                    <span className="mt-1.5 block text-[11px] text-muted">
                      {t.teams.join(" ↔ ")} · {t.n_players} player{t.n_players === 1 ? "" : "s"}
                      {t.n_picks ? ` · ${t.n_picks} pick${t.n_picks === 1 ? "" : "s"}` : ""} · saved{" "}
                      {formatDate(t.created_at)}
                    </span>
                    {isSelected &&
                      (detail ? (
                        <span className="mt-2 block space-y-0.5">
                          {receivedByTeam(detail).map((group) => (
                            <span
                              key={group.abbreviation}
                              className="block text-[11px] text-muted"
                            >
                              <span className="font-semibold text-foreground">
                                {group.abbreviation}
                              </span>{" "}
                              get {group.items.join(", ")}
                            </span>
                          ))}
                        </span>
                      ) : (
                        <span className="skeleton mt-2 block h-3 w-40" aria-hidden />
                      ))}
                  </button>
                );
              })}
            </div>
            <div className="flex flex-wrap items-center gap-2">
              <select
                value={scenarioId}
                onChange={(e) => setScenarioId(e.target.value)}
                className="rounded-md border border-line bg-panel2 px-2 py-1.5 text-sm"
                aria-label="Scenario providing the starting weights"
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
                className="rounded-md bg-brand px-4 py-2 text-sm font-semibold text-background transition hover:brightness-110 disabled:opacity-40"
              >
                {compare.isPending
                  ? "Comparing…"
                  : selected.length < 2
                    ? "Select at least 2 deals"
                    : `Compare ${selected.length} deals`}
              </button>
            </div>
          </div>
        )}
      </Card>

      {comparison && (
        <>
          <Card title="Comparison matrix" subtitle={comparison.note}>
            <div className="scroll-thin overflow-x-auto">
              <table className="w-full min-w-[980px]">
                <thead>
                  <tr className="border-b border-line">
                    <Th>Deal</Th>
                    <Th>Rules check</Th>
                    <Th className="text-right">Score</Th>
                    <Th className="text-right">Δ wins [p10, p90]</Th>
                    {COMPONENT_KEYS.map((key) => (
                      <Th key={key} className="text-right">
                        {COMPONENT_LABEL[key]}
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
                        <Link href={`/trades/${alt.trade_id}`} className="hover:text-brand">
                          {alt.name}
                        </Link>
                        {(alt.incoming.length > 0 || alt.outgoing.length > 0) && (
                          <span className="block max-w-56 truncate text-[11px] text-muted">
                            in: {alt.incoming.map((p) => p.name).join(", ") || "—"} · out:{" "}
                            {alt.outgoing.map((p) => p.name).join(", ") || "—"}
                          </span>
                        )}
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
                        {signed(alt.uncertainty?.median)}
                        <span className="text-[10px] text-muted">
                          {" "}
                          [{signed(alt.uncertainty?.p10)}, {signed(alt.uncertainty?.p90)}]
                        </span>
                      </Td>
                      {COMPONENT_KEYS.map((key) => (
                        <Td key={key} className="text-right font-mono">
                          {alt.components[key] !== null && alt.components[key] !== undefined ? (
                            Number(alt.components[key]).toFixed(0)
                          ) : (
                            <span className="text-unavail">n/a</span>
                          )}
                        </Td>
                      ))}
                      <Td className="text-right font-mono">
                        {money(alt.payroll_after)}
                        {alt.apron_status_after && (
                          <span className="block text-[10px] text-muted">
                            {alt.apron_status_after.replaceAll("_", " ")}
                          </span>
                        )}
                      </Td>
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
            <p className="mt-2 text-[11px] text-muted">
              Δ wins always shown with its [p10, p90] range — never a bare point estimate. n/a
              components are excluded and the remaining weights renormalized.
            </p>
          </Card>

          <Card
            title="Adjust priorities"
            subtitle="Exploratory re-weighting of the stored component scores — the ranking updates live, but no model is re-run."
            actions={
              <button
                type="button"
                onClick={() => setWeights(toSliderWeights(comparison.weights))}
                className="rounded-md border border-line px-2.5 py-1 text-xs hover:bg-panel2"
              >
                Reset to saved weights
              </button>
            }
          >
            <div className="grid gap-x-8 gap-y-3 md:grid-cols-2">
              {COMPONENT_KEYS.map((key) => {
                const value = weights[key] ?? 0;
                const share = totalWeight > 0 ? value / totalWeight : 0;
                return (
                  <label key={key} className="block text-sm">
                    <span className="flex items-baseline justify-between">
                      <span>{COMPONENT_LABEL[key]}</span>
                      <span className="font-mono text-xs text-muted">{pct(share)} of score</span>
                    </span>
                    <input
                      type="range"
                      min={0}
                      max={100}
                      step={1}
                      value={value}
                      aria-label={`Priority weight for ${COMPONENT_LABEL[key]}`}
                      onChange={(e) =>
                        setWeights({ ...weights, [key]: Number(e.target.value) })
                      }
                      className="mt-1 w-full accent-brand"
                    />
                  </label>
                );
              })}
            </div>
            <p className="mt-3 text-[11px] text-muted">
              Decision score = Σ(weight × component) ÷ Σ(weights), computed over available
              components only — missing components drop out and the remaining weights
              renormalize, the same rule the backend applies. The saved rank-stability analysis
              below is independent of these sliders.
            </p>

            <ol className="mt-4 space-y-2">
              {ranked.map(({ alt, score }, index) => {
                const missing = missingComponents(alt);
                const verdict = fanVerdict(score, missing.length > 0 ? "low" : "high");
                const isLeading = leader !== null && leader.alt.trade_id === alt.trade_id;
                return (
                  <li
                    key={alt.trade_id}
                    className={`flex flex-wrap items-center gap-x-2 gap-y-1 rounded-md border px-3 py-2 ${
                      isLeading ? "border-brand/60 bg-brand/10" : "border-line bg-panel2"
                    }`}
                  >
                    <span className="font-mono text-xs text-muted">#{index + 1}</span>
                    <span className="text-sm font-medium">{alt.name}</span>
                    {isLeading && (
                      <Badge status="info" className="border-brand/40 bg-brand/15 text-brand">
                        leads under current weights
                      </Badge>
                    )}
                    <Badge status={VERDICT_STATUS[verdict]}>{VERDICT_LABEL[verdict]}</Badge>
                    <span className="ml-auto font-mono text-sm font-semibold">
                      {score !== null ? score.toFixed(1) : "n/a"}
                    </span>
                    <span className="w-full text-[11px] text-muted">
                      Δ wins {signed(alt.uncertainty?.median)} [{signed(alt.uncertainty?.p10)},{" "}
                      {signed(alt.uncertainty?.p90)}]
                      {missing.length > 0 &&
                        ` · missing: ${missing.map((k) => COMPONENT_LABEL[k]).join(", ")}`}
                    </span>
                  </li>
                );
              })}
            </ol>
          </Card>

          {explanation && (
            <Card
              title="Why this deal leads"
              subtitle="Generated from the comparison data under your current slider weights."
            >
              <ul className="space-y-2 text-sm leading-relaxed">
                <li>
                  <span className="font-semibold text-brand">{explanation.lead.name}</span> leads{" "}
                  {explanation.topStrengths.length > 0 ? (
                    <>
                      because it scores best on{" "}
                      <span className="font-medium">
                        {explanation.topStrengths.join(" and ")}
                      </span>
                      .
                    </>
                  ) : (
                    <>
                      on the weighted blend — it is not the outright best on any single
                      dimension, but its overall balance comes out on top.
                    </>
                  )}
                </li>
                <li>
                  {explanation.flips.length > 0 ? (
                    <>
                      It loses the top spot when{" "}
                      {explanation.flips
                        .map(
                          (flip) =>
                            `${COMPONENT_LABEL[flip.key]} is doubled (${flip.newLeader} takes over)`,
                        )
                        .join("; or when ")}
                      .
                    </>
                  ) : (
                    <>
                      Doubling any single priority from its current setting does not change the
                      leader — the top spot is stable under these weights.
                    </>
                  )}
                </li>
                {explanation.dominance.map((sentence) => (
                  <li key={sentence} className="text-muted">
                    {sentence}
                  </li>
                ))}
                {missingComponents(explanation.lead).length > 0 && (
                  <li className="text-unavail">
                    Caution: {missingComponents(explanation.lead)
                      .map((k) => COMPONENT_LABEL[k])
                      .join(", ")}{" "}
                    {missingComponents(explanation.lead).length === 1 ? "is" : "are"} unavailable
                    for the leading deal, so this read cannot be a full evaluation.
                  </li>
                )}
              </ul>
            </Card>
          )}

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
              title="Rank stability (saved analysis)"
              subtitle="Share of sampled strategy-weight vectors in which each deal ranks #1 — computed by the backend when the comparison was created, independent of the sliders above."
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
