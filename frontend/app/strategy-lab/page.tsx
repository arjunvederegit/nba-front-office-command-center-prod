"use client";

/**
 * Strategy Lab — the decision board over 2–5 saved deals.
 *
 * The backend computes component scores, Pareto dominance and weight-sampling
 * sensitivity once per comparison. On top of that this page adds an exploratory
 * "Adjust priorities" control surface that re-weights the STORED component
 * scores live on the client (same renormalization rule as the backend: missing
 * components drop out and the remaining weights renormalize) — it never re-runs
 * a model, and it is labeled as exploratory next to the saved backend analysis.
 *
 * DATA HONESTY: a null component is rendered as "n/a" everywhere and excluded
 * from the score; nothing on this page is estimated to fill a gap.
 */

import { useMutation, useQueries, useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { useMemo, useState } from "react";
import { api } from "@/lib/api";
import { dataHealthSchema, tradeDetailSchema } from "@/lib/schemas";
import { COMPONENT_EXPLAIN, COMPONENT_LABEL, LEGALITY_EXPLAIN, LEGALITY_LABEL, VERDICT_LABEL, VERDICT_STATUS, count, fanVerdict, formatDate, money, pct } from "@/lib/format";
import { scenarioOptionLabels } from "@/lib/scenarioLabels";
import { teamIdentity } from "@/lib/teamIdentity";
import type {
  ComparisonAlternative,
  ComparisonResponse,
  DataHealth,
  RosterResponse,
  Scenario,
  TradeDetail,
  TradeSummary,
  Uncertainty,
} from "@/lib/types";
import { FirstPlaceShareBars, ParetoScatter, UncertaintyStrip } from "@/components/charts";
import { TransactionLane } from "@/components/court";
import { PlayerPhoto, TeamLogo } from "@/components/media";
import { useToast } from "@/components/toast";
import {
  Badge,
  Button,
  ButtonLink,
  EmptyState,
  ErrorState,
  MeterBar,
  PageHeader,
  Panel,
  Skeleton,
  SourceRail,
  Tabs,
  Td,
  Th,
  UnavailableNotice,
} from "@/components/ui";

const COMPONENT_KEYS = ["performance", "fit", "contract", "timeline", "assets", "risk"] as const;
type ComponentKey = (typeof COMPONENT_KEYS)[number];

const MAX_SELECTED = 5;
const MIN_SELECTED = 2;

const TABS = [
  { id: "summary", label: "Summary" },
  { id: "impact", label: "Team impact" },
  { id: "fit", label: "Basketball fit" },
  { id: "financial", label: "Financial" },
  { id: "timeline", label: "Timeline" },
  { id: "risk", label: "Risk" },
  { id: "sensitivity", label: "Sensitivity" },
] as const;

type TabId = (typeof TABS)[number]["id"];

const ENGINE_SOURCE = "Pivot evaluation engine · NBA.com via nba_api";

/* ---------------------------------------------------------------- scoring */

/** Signed one-decimal number, e.g. +3.2 / -1.4. */
function signed(value: number | null | undefined): string {
  if (value === null || value === undefined) return "—";
  return `${value >= 0 ? "+" : ""}${value.toFixed(1)}`;
}

function componentColor(value: number): string {
  return value >= 50 ? "var(--signal)" : "var(--illegal)";
}

/**
 * Client-side decision score under a weight vector: Σ(w·c) ÷ Σ(w) over NON-NULL
 * components only — the same renormalization rule the backend applies when a
 * component is unavailable.
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

/* --------------------------------------------------------------- deal shape */

interface DealAsset {
  key: string;
  label: string;
  playerName: string | null;
  playerId: string | null;
}

/** Assets grouped by receiving team — "who gets what", for the selection cards. */
function receivedByTeam(detail: TradeDetail): { abbreviation: string; items: DealAsset[] }[] {
  return detail.teams
    .map((team) => ({
      abbreviation: team.abbreviation,
      items: detail.assets
        .filter((asset) => asset.to_team_id === team.team_id)
        .map((asset, index): DealAsset => {
          const isPlayer = asset.asset_type === "player";
          return {
            key: `${team.team_id}-${index}`,
            label: isPlayer
              ? (asset.player_name ?? "Unknown player")
              : `${asset.draft_year ?? "Future"} R${asset.round_number ?? "?"} pick${
                  asset.protections ? ` · ${asset.protections}` : ""
                }`,
            playerName: isPlayer ? (asset.player_name ?? "Unknown player") : null,
            playerId: isPlayer ? asset.player_id : null,
          };
        }),
    }))
    .filter((group) => group.items.length > 0);
}

/* -------------------------------------------------------------------- page */

export default function StrategyLabPage() {
  const toast = useToast();

  const { data: trades, error: tradesError } = useQuery({
    queryKey: ["trades"],
    queryFn: () => api.get<TradeSummary[]>("/trades"),
  });
  const { data: scenarios } = useQuery({
    queryKey: ["scenarios"],
    queryFn: () => api.get<Scenario[]>("/scenarios"),
  });
  // Built for the whole list at once — see `lib/scenarioLabels.ts`.
  const scenarioLabels = useMemo(
    () => scenarioOptionLabels(scenarios ?? []),
    [scenarios],
  );
  const { data: health } = useQuery({
    queryKey: ["data-health"],
    queryFn: () => api.get<DataHealth>("/data-health", dataHealthSchema),
    staleTime: 120_000,
  });

  const [selected, setSelected] = useState<string[]>([]);
  const [scenarioId, setScenarioId] = useState<string>("");
  const [comparison, setComparison] = useState<ComparisonResponse | null>(null);
  const [tab, setTab] = useState<TabId>("summary");
  /** Slider positions (0–100) for the exploratory re-weighting surface. */
  const [weights, setWeights] = useState<Record<string, number>>({});

  // Deal contents for every saved deal, so the selection cards can show who moves.
  const detailQueries = useQueries({
    queries: (trades ?? []).map((trade) => ({
      queryKey: ["trade", trade.id],
      queryFn: () => api.get<TradeDetail>(`/trades/${trade.id}`, tradeDetailSchema),
      staleTime: 300_000,
    })),
  });
  const detailById: Record<string, TradeDetail> = {};
  for (const query of detailQueries) if (query.data) detailById[query.data.id] = query.data;

  // Rosters of the involved teams resolve player_id -> nba_player_id for headshots.
  const involvedTeamIds = Array.from(
    new Set(Object.values(detailById).flatMap((detail) => detail.teams.map((t) => t.team_id))),
  ).sort();
  const rosterQueries = useQueries({
    queries: involvedTeamIds.map((teamId) => ({
      queryKey: ["roster", teamId],
      queryFn: () => api.get<RosterResponse>(`/teams/${teamId}/roster`),
      staleTime: 300_000,
    })),
  });
  const nbaIdByPlayerId: Record<string, number> = {};
  const nbaIdByName: Record<string, number> = {};
  for (const query of rosterQueries) {
    for (const player of query.data?.roster ?? []) {
      nbaIdByPlayerId[player.player_id] = player.nba_player_id;
      nbaIdByName[player.name] = player.nba_player_id;
    }
  }

  /** Resolve a headshot id for a name inside a specific deal (exact, no guessing). */
  function photoIdFor(tradeId: string, playerName: string): number | null {
    const detail = detailById[tradeId];
    const asset = detail?.assets.find((a) => a.player_name === playerName);
    if (asset?.player_id && nbaIdByPlayerId[asset.player_id]) return nbaIdByPlayerId[asset.player_id];
    return nbaIdByName[playerName] ?? null;
  }

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
      setTab("summary");
    },
    onError: (err) => toast("error", `Comparison failed: ${err.message}`),
  });

  function toggle(id: string) {
    if (selected.includes(id)) {
      setSelected(selected.filter((x) => x !== id));
    } else if (selected.length >= MAX_SELECTED) {
      toast("info", `You can compare at most ${MAX_SELECTED} deals — deselect one first.`);
    } else {
      setSelected([...selected, id]);
    }
  }

  const names: Record<string, string> = Object.fromEntries(
    (trades ?? []).map((trade) => [trade.id, trade.name]),
  );

  const totalWeight = COMPONENT_KEYS.reduce((sum, key) => sum + (weights[key] ?? 0), 0);

  /** Live re-ranking of the stored component scores under the slider weights. */
  // A deal that fails a verified rule, or that no component could score, is listed but
  // never ranked — putting it on the board invites choosing the one that cannot happen.
  const { ranked, unrankable } = useMemo(() => {
    if (!comparison) return { ranked: [], unrankable: [] as ComparisonAlternative[] };
    const scored: { alt: ComparisonAlternative; score: number }[] = [];
    const excluded: ComparisonAlternative[] = [];
    for (const alt of comparison.alternatives) {
      const score = alt.decision_status === "scored" ? decisionScore(weights, alt.components) : null;
      if (score === null) excluded.push(alt);
      else scored.push({ alt, score });
    }
    scored.sort((a, b) => b.score - a.score);
    return { ranked: scored, unrankable: excluded };
  }, [comparison, weights]);

  const leader = ranked[0] ?? null;

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
          } — it is never better on any displayed dimension.`,
      );

    return { lead, topStrengths, flips, dominance };
  }, [comparison, leader, weights]);

  const retrievedAt = health?.last_successful_sync ?? null;
  const contractsNote = health?.providers?.contracts?.note ?? null;
  const contractsConfigured = health?.providers?.contracts?.configured ?? false;

  const notEnoughDeals = !!trades && trades.length < MIN_SELECTED;

  return (
    <div className="space-y-8">
      <PageHeader
        eyebrow="Strategy Lab"
        title="Decision board"
        lede="Line up two to five saved deals, weight them by what your front office actually cares about, and see which one survives the priorities you set."
        meta={
          <>
            <Badge status="info">
              {trades ? count(trades.length, "saved deal") : "loading deals"}
            </Badge>
            <Badge status={contractsConfigured ? "pass" : "unavailable"}>
              contracts {contractsConfigured ? "imported" : "not imported"}
            </Badge>
            {comparison && <Badge status="running">{comparison.alternatives.length} on the board</Badge>}
          </>
        }
        actions={
          <ButtonLink href="/trade-evaluator" variant="secondary" size="sm">
            Build a new deal
          </ButtonLink>
        }
      />

      {/* ------------------------------------------------------------ select */}
      <section aria-labelledby="select-heading">
        <SectionHead
          eyebrow="Step one"
          title="Choose the deals"
          aside={`Pick ${MIN_SELECTED}–${MAX_SELECTED} saved deals`}
          id="select-heading"
        />

        {tradesError ? (
          <ErrorState
            message={`Could not load saved deals: ${(tradesError as Error).message}`}
            action={
              <ButtonLink href="/data-health" size="sm">
                Check Data Health
              </ButtonLink>
            }
          />
        ) : !trades ? (
          <div className="grid gap-3 xl:grid-cols-[minmax(0,1fr)_300px] xl:items-start">
            <div className="grid gap-3 sm:grid-cols-2" role="status" aria-label="Loading saved deals">
              {Array.from({ length: 4 }).map((_, i) => (
                <Skeleton key={i} className="h-[236px]" />
              ))}
            </div>
            <Skeleton className="h-[420px]" />
          </div>
        ) : notEnoughDeals ? (
          <div className="grid gap-3 xl:grid-cols-[minmax(0,1fr)_300px] xl:items-start">
            <EmptyState
              className="px-6 py-16"
              title={trades.length === 0 ? "No saved deals yet" : "One deal isn't a comparison"}
              hint={
                trades.length === 0
                  ? "The Strategy Lab ranks deals against each other, so it needs at least two saved deals. Build one in the Trade Evaluator, save it, and come back — every deal you save shows up here automatically."
                  : `You have one saved deal. Save at least ${MIN_SELECTED} to put them side by side; nothing here is ever compared against an invented alternative.`
              }
              action={
                <>
                  <ButtonLink href="/trade-evaluator" variant="primary">
                    Open the Trade Evaluator
                  </ButtonLink>
                  <ButtonLink href="/team-outlook" variant="secondary">
                    Set a team strategy first
                  </ButtonLink>
                </>
              }
            />
            <MethodRail selectedCount={null} />
          </div>
        ) : (
          <div className="grid gap-3 xl:grid-cols-[minmax(0,1fr)_300px] xl:items-start">
            <div className="min-w-0">
            <div className="grid gap-3 sm:grid-cols-2">
              {trades.map((trade) => (
                <DealCard
                  key={trade.id}
                  trade={trade}
                  detail={detailById[trade.id]}
                  selected={selected.includes(trade.id)}
                  onToggle={() => toggle(trade.id)}
                  nbaIdByPlayerId={nbaIdByPlayerId}
                />
              ))}
            </div>

            {/* sticky action bar */}
            <div className="sticky bottom-3 z-30 mt-3">
              <div className="panel flex flex-col gap-3 bg-panel/95 px-4 py-3 backdrop-blur-md sm:flex-row sm:flex-wrap sm:items-center sm:gap-x-4">
                <p className="flex items-baseline gap-2" aria-live="polite">
                  <span className="numeral text-[1.75rem] leading-none text-signal">
                    {selected.length}
                  </span>
                  <span className="eyebrow whitespace-nowrap">of {MAX_SELECTED} selected</span>
                </p>

                <div className="flex min-w-0 flex-1 items-center gap-2 sm:justify-end">
                  <label
                    htmlFor="scenario-weights"
                    className="eyebrow hidden shrink-0 whitespace-nowrap md:block"
                  >
                    Starting weights
                  </label>
                  <select
                    id="scenario-weights"
                    aria-label="Scenario providing the starting weights"
                    value={scenarioId}
                    onChange={(event) => setScenarioId(event.target.value)}
                    className="min-w-0 flex-1 rounded-md border border-line bg-panel2 px-2.5 py-1.5 text-[13px] text-foreground sm:max-w-64"
                  >
                    <option value="">League default weights</option>
                    {/* Name alone is not an identity: Team Outlook generates
                        "BOS — Contend now" every time the button is pressed. Labels are
                        built for the whole list at once so uniqueness is a property of
                        the output rather than a hope about the timestamps. */}
                    {(scenarios ?? []).map((scenario, index) => (
                      <option key={scenario.id} value={scenario.id}>
                        {scenarioLabels[index]}
                      </option>
                    ))}
                  </select>
                  <Button
                    variant="primary"
                    className="shrink-0"
                    disabled={selected.length < MIN_SELECTED || compare.isPending}
                    onClick={() => compare.mutate()}
                  >
                    {compare.isPending
                      ? "Comparing…"
                      : selected.length < MIN_SELECTED
                        ? `Select ${MIN_SELECTED - selected.length} more`
                        : `Compare ${selected.length} deals`}
                  </Button>
                  </div>
                </div>
              </div>
            </div>

            <MethodRail selectedCount={selected.length} />
          </div>
        )}
      </section>

      {/* ----------------------------------------------------------- results */}
      {compare.isPending && !comparison && (
        <section aria-label="Building the comparison">
          <SectionHead eyebrow="Step two" title="The board" aside="Scoring your deals" />
          <div className="grid gap-3 xl:grid-cols-[minmax(0,1fr)_320px]">
            <Skeleton className="h-[320px]" />
            <Skeleton className="h-[320px]" />
          </div>
        </section>
      )}

      {comparison && ranked.length + unrankable.length > 0 && (
        <>
          <section aria-labelledby="board-heading">
            <SectionHead
              eyebrow="Step two"
              title="The board"
              aside="Ranked live under your priorities"
              id="board-heading"
            />
            <div className="grid gap-3 xl:grid-cols-[minmax(0,1fr)_320px] xl:items-start">
              <div className="min-w-0 space-y-3">
                {ranked.length === 0 && (
                  <UnavailableNotice reason="None of the selected deals can be ranked — see the list below for why each one was excluded." />
                )}
                {ranked.map(({ alt, score }, index) =>
                  index === 0 ? (
                    <LeaderPanel
                      key={alt.trade_id}
                      alt={alt}
                      score={score}
                      retrievedAt={retrievedAt}
                      photoIdFor={photoIdFor}
                    />
                  ) : (
                    <ChallengerRow key={alt.trade_id} alt={alt} score={score} rank={index + 1} />
                  ),
                )}
                {unrankable.length > 0 && (
                  <div className="rounded-lg border border-hairline bg-panel2/40 p-3.5">
                    <div className="eyebrow text-[0.5625rem] text-unavail">
                      Not ranked ({unrankable.length})
                    </div>
                    <p className="mt-1 text-[12px] leading-snug text-muted">
                      These deals are on the board but never compete: a deal that fails a
                      verified rule cannot be executed, and one with no scorable component has
                      nothing to compare.
                    </p>
                    <ul className="mt-2 space-y-1.5">
                      {unrankable.map((alt) => (
                        <li
                          key={alt.trade_id}
                          className="flex flex-wrap items-center gap-x-2.5 gap-y-1 text-[13px]"
                        >
                          <Link
                            href={`/trades/${alt.trade_id}`}
                            className="min-w-0 flex-1 truncate text-foreground hover:text-signal"
                          >
                            {alt.name}
                          </Link>
                          <Badge status={alt.legality_status}>
                            {LEGALITY_LABEL[alt.legality_status]}
                          </Badge>
                          <span className="text-[11px] text-unavail">
                            {alt.decision_status === "suppressed_illegal"
                              ? "no score — fails a verified rule"
                              : "no score — nothing could be scored"}
                          </span>
                        </li>
                      ))}
                    </ul>
                  </div>
                )}
              </div>

              {/* sticky lives on the wrapper: `.panel` already sets position:relative */}
              <div className="xl:sticky xl:top-20">
                <Panel
                title="Adjust priorities"
                subtitle="Exploratory re-weighting of stored component scores. The board re-ranks live; no model is re-run."
                actions={
                  <Button
                    size="sm"
                    variant="ghost"
                    onClick={() => setWeights(toSliderWeights(comparison.weights))}
                  >
                    Reset
                  </Button>
                }
              >
                <div className="space-y-3.5">
                  {COMPONENT_KEYS.map((key) => {
                    const value = weights[key] ?? 0;
                    const share = totalWeight > 0 ? value / totalWeight : 0;
                    return (
                      <div key={key}>
                        <div className="flex items-baseline justify-between gap-2">
                          <label
                            htmlFor={`weight-${key}`}
                            className="eyebrow min-w-0 truncate"
                            title={COMPONENT_EXPLAIN[key]}
                          >
                            {COMPONENT_LABEL[key]}
                          </label>
                          <span className="numeral shrink-0 text-base leading-none text-signal">
                            {pct(share)}
                          </span>
                        </div>
                        <input
                          id={`weight-${key}`}
                          type="range"
                          min={0}
                          max={100}
                          step={1}
                          value={value}
                          aria-label={`Priority weight for ${COMPONENT_LABEL[key]}`}
                          aria-valuetext={`${pct(share)} of the decision score`}
                          onChange={(event) =>
                            setWeights({ ...weights, [key]: Number(event.target.value) })
                          }
                          className="mt-1.5 w-full accent-[var(--signal)]"
                        />
                      </div>
                    );
                  })}
                </div>
                <p className="mt-4 border-t border-hairline pt-3 text-[11px] leading-relaxed text-muted">
                  Decision score = Σ(weight × component) ÷ Σ(weights), over available components
                  only. A component marked n/a drops out and the remaining weights renormalize —
                  the same rule the backend applies. The saved rank-stability analysis in{" "}
                  <span className="text-foreground">Sensitivity</span> is independent of these
                  sliders.
                </p>
                </Panel>
              </div>
            </div>
          </section>

          {explanation && (
            <Panel
              title="Why this deal leads"
              subtitle="Written from the comparison response under your current slider weights — no new model run."
              accent="var(--leather)"
            >
              <ul className="space-y-2.5 text-sm leading-relaxed">
                <li className="flex gap-2.5">
                  <span aria-hidden className="numeral mt-px shrink-0 text-brand">
                    01
                  </span>
                  <span className="min-w-0">
                    <Link
                      href={`/trades/${explanation.lead.trade_id}`}
                      className="font-semibold text-foreground underline decoration-brand/50 underline-offset-2 hover:text-brand"
                    >
                      {explanation.lead.name}
                    </Link>{" "}
                    {explanation.topStrengths.length > 0 ? (
                      <>
                        leads because it scores best on{" "}
                        <span className="font-medium text-foreground">
                          {explanation.topStrengths.join(" and ")}
                        </span>
                        .
                      </>
                    ) : (
                      <>
                        leads on the weighted blend — it is not the outright best on any single
                        dimension, but its overall balance comes out on top.
                      </>
                    )}
                  </span>
                </li>
                <li className="flex gap-2.5">
                  <span aria-hidden className="numeral mt-px shrink-0 text-brand">
                    02
                  </span>
                  <span className="min-w-0">
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
                  </span>
                </li>
                {explanation.dominance.map((sentence, index) => (
                  <li key={sentence} className="flex gap-2.5 text-muted">
                    <span aria-hidden className="numeral mt-px shrink-0 text-faint">
                      {String(index + 3).padStart(2, "0")}
                    </span>
                    <span className="min-w-0">{sentence}</span>
                  </li>
                ))}
                {missingComponents(explanation.lead).length > 0 && (
                  <li className="flex gap-2.5 rounded-md border border-unavail/35 bg-unavail/8 px-3 py-2 text-muted">
                    <span aria-hidden className="mt-px shrink-0 font-mono text-unavail">
                      —
                    </span>
                    <span className="min-w-0">
                      <span className="font-semibold text-foreground">Caution. </span>
                      {missingComponents(explanation.lead)
                        .map((key) => COMPONENT_LABEL[key])
                        .join(", ")}{" "}
                      {missingComponents(explanation.lead).length === 1 ? "is" : "are"} unavailable
                      for the leading deal, so this read cannot be a full evaluation.
                    </span>
                  </li>
                )}
              </ul>
              <SourceRail source={ENGINE_SOURCE} retrievedAt={retrievedAt} />
            </Panel>
          )}

          {/* ------------------------------------------------------ tabbed views */}
          <section aria-labelledby="views-heading">
            <SectionHead
              eyebrow="Step three"
              title="Read the difference"
              aside="Same comparison, seven angles"
              id="views-heading"
            />
            <Panel padded={false}>
              <div className="border-b border-hairline px-3 pt-2">
                <Tabs
                  tabs={TABS.map((t) => ({ id: t.id, label: t.label }))}
                  active={tab}
                  onChange={(id) => setTab(id as TabId)}
                  ariaLabel="Comparison views"
                />
              </div>
              <div
                role="tabpanel"
                aria-label={`${TABS.find((t) => t.id === tab)?.label} view`}
                className="p-4"
              >
                {tab === "summary" && (
                  <SummaryView comparison={comparison} ranked={ranked} weights={weights} />
                )}
                {tab === "impact" && (
                  <ImpactView ranked={ranked} photoIdFor={photoIdFor} />
                )}
                {tab === "fit" && <FitView ranked={ranked} photoIdFor={photoIdFor} />}
                {tab === "financial" && (
                  <FinancialView
                    ranked={ranked}
                    contractsConfigured={contractsConfigured}
                    contractsNote={contractsNote}
                  />
                )}
                {tab === "timeline" && <TimelineView ranked={ranked} />}
                {tab === "risk" && <RiskView ranked={ranked} />}
                {tab === "sensitivity" && (
                  <SensitivityView comparison={comparison} names={names} />
                )}
                <SourceRail source={ENGINE_SOURCE} retrievedAt={retrievedAt} />
              </div>
            </Panel>
          </section>
        </>
      )}
    </div>
  );
}

/* ------------------------------------------------------------------ pieces */

function SectionHead({
  eyebrow,
  title,
  aside,
  id,
}: {
  eyebrow: string;
  title: string;
  aside?: string;
  id?: string;
}) {
  return (
    <div className="mb-3">
      <div className="h-px w-full bg-gradient-to-r from-signal/60 to-transparent" />
      <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1 pt-2.5">
        <div>
          <div className="eyebrow">{eyebrow}</div>
          <h2 id={id} className="title-lg mt-1 whitespace-nowrap text-foreground">
            {title}
          </h2>
        </div>
        {aside && <p className="text-[11px] text-faint">{aside}</p>}
      </div>
    </div>
  );
}

const METHOD_STEPS = [
  {
    title: "Put deals on the board",
    body: `Select ${MIN_SELECTED}–${MAX_SELECTED} saved deals. Each one keeps the component scores the backend computed when it was evaluated.`,
  },
  {
    title: "Weight what you care about",
    body: "Drag the priority sliders. The ranking recomputes instantly from the stored scores — no model is re-run, so the numbers never drift.",
  },
  {
    title: "Read it seven ways",
    body: "Summary, team impact, basketball fit, financial, timeline, risk and sensitivity — the same comparison, sliced by the question you are actually asking.",
  },
];

/** Explains the board while the user is still choosing — and fills the column. */
function MethodRail({ selectedCount }: { selectedCount: number | null }) {
  return (
    <Panel title="How the board works" accent="var(--leather)">
      <ol className="space-y-3.5">
        {METHOD_STEPS.map((step, index) => (
          <li key={step.title} className="flex gap-2.5">
            <span
              aria-hidden
              className="numeral shrink-0 text-base leading-tight text-brand"
            >
              {String(index + 1).padStart(2, "0")}
            </span>
            <span className="min-w-0">
              <span className="block text-sm font-semibold text-foreground">{step.title}</span>
              <span className="mt-0.5 block text-[12px] leading-snug text-muted">{step.body}</span>
            </span>
          </li>
        ))}
      </ol>
      <p className="mt-4 border-t border-hairline pt-3 text-[11px] leading-relaxed text-muted">
        A component the backend could not score shows as{" "}
        <span className="data text-unavail">n/a</span> and is dropped from the maths rather than
        filled in with a guess. That is why a deal missing contract data can still rank — it is
        simply being judged on less.
      </p>
      {selectedCount !== null && (
        <p className="mt-3 text-[11px] text-faint" aria-live="polite">
          {selectedCount === 0
            ? `Nothing selected yet — pick ${MIN_SELECTED} deals to start.`
            : selectedCount < MIN_SELECTED
              ? `${selectedCount} selected — ${MIN_SELECTED - selectedCount} more to compare.`
              : `${selectedCount} selected and ready to compare.`}
        </p>
      )}
    </Panel>
  );
}

/** One selectable saved deal. Everything inside stays phrasing-level (button content). */
function DealCard({
  trade,
  detail,
  selected,
  onToggle,
  nbaIdByPlayerId,
}: {
  trade: TradeSummary;
  detail: TradeDetail | undefined;
  selected: boolean;
  onToggle: () => void;
  nbaIdByPlayerId: Record<string, number>;
}) {
  const identity = teamIdentity(trade.teams[0]);
  const groups = detail ? receivedByTeam(detail) : [];

  return (
    <button
      type="button"
      role="checkbox"
      aria-checked={selected}
      aria-label={`${selected ? "Deselect" : "Select"} deal ${trade.name}, ${trade.teams.join(
        " and ",
      )}`}
      onClick={onToggle}
      className={`panel flex min-w-0 flex-col p-3.5 text-left transition-[border-color,box-shadow] ${
        selected
          ? "border-signal/70 shadow-[var(--glow-signal)]"
          : "hover:border-signal/35"
      }`}
      style={{ "--edge": selected ? "var(--signal)" : identity.bright } as React.CSSProperties}
    >
      <span className="flex w-full items-center gap-2">
        <span className="flex shrink-0 items-center gap-1">
          {trade.teams.map((abbr) => (
            <TeamLogo key={abbr} abbreviation={abbr} size={22} decorative />
          ))}
        </span>
        <span className="title-md min-w-0 flex-1 truncate text-foreground">{trade.name}</span>
        <span
          aria-hidden
          className={`flex h-5 w-5 shrink-0 items-center justify-center rounded-full border text-[11px] font-bold ${
            selected
              ? "border-signal bg-signal text-court"
              : "border-line text-transparent"
          }`}
        >
          ✓
        </span>
      </span>

      <span className="eyebrow mt-2 block truncate text-[0.5625rem]">
        {trade.teams.join(" ↔ ")} · {trade.n_players} player{trade.n_players === 1 ? "" : "s"}
        {trade.n_picks ? ` · ${trade.n_picks} pick${trade.n_picks === 1 ? "" : "s"}` : ""}
      </span>

      <span className="mt-3 block flex-1 border-t border-hairline pt-3">
        {!detail ? (
          <span className="block space-y-1.5">
            <Skeleton className="h-4 w-24" />
            <Skeleton className="h-5 w-full" />
            <Skeleton className="h-5 w-3/4" />
          </span>
        ) : groups.length === 0 ? (
          <span className="block text-[12px] text-faint">
            No assets recorded on this deal.
          </span>
        ) : (
          <span className="block">
            {groups.map((group, groupIndex) => {
              const teamColors = teamIdentity(group.abbreviation);
              return (
                <span key={group.abbreviation} className="block">
                  {groupIndex > 0 && (
                    <span aria-hidden className="my-2.5 flex items-center gap-2">
                      <span className="h-px flex-1 bg-hairline" />
                      <TransactionLane
                        className="h-5 w-14 shrink-0"
                        active={selected}
                        leftColor={teamIdentity(groups[groupIndex - 1].abbreviation).bright}
                        rightColor={teamColors.bright}
                      />
                      <span className="h-px flex-1 bg-hairline" />
                    </span>
                  )}
                  <span className="flex items-center gap-1.5">
                    <TeamLogo abbreviation={group.abbreviation} size={15} decorative />
                    <span
                      className="numeral text-[13px] leading-none"
                      style={{ color: teamColors.bright }}
                    >
                      {group.abbreviation}
                    </span>
                    <span className="eyebrow text-[0.5rem]">gets</span>
                  </span>
                  <span className="mt-1.5 block space-y-1.5">
                    {group.items.slice(0, 3).map((item) => (
                      <span key={item.key} className="flex min-w-0 items-center gap-2">
                        {item.playerName ? (
                          <PlayerPhoto
                            nbaPlayerId={
                              item.playerId ? (nbaIdByPlayerId[item.playerId] ?? null) : null
                            }
                            name={item.playerName}
                            size={24}
                          />
                        ) : (
                          <span
                            aria-hidden
                            className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full border border-line text-[10px] text-faint"
                          >
                            ◈
                          </span>
                        )}
                        <span className="min-w-0 truncate text-[13px] text-foreground">
                          {item.label}
                        </span>
                      </span>
                    ))}
                    {group.items.length > 3 && (
                      <span className="block text-[11px] text-faint">
                        +{group.items.length - 3} more
                      </span>
                    )}
                  </span>
                </span>
              );
            })}
          </span>
        )}
      </span>

      <span className="mt-3 block border-t border-hairline pt-2 text-[11px] text-faint">
        Saved {formatDate(trade.created_at)}
      </span>
    </button>
  );
}

/** Per-component mini bars with honest n/a tracks. */
function ComponentMiniBars({
  components,
  columns = 3,
}: {
  components: Record<string, number | null>;
  columns?: 2 | 3;
}) {
  return (
    <ul
      className={`grid gap-x-4 gap-y-2 ${
        // the two-column variant sits in a narrow half-panel: it only splits once
        // the cell is wide enough for the longest component label to fit unclipped
        columns === 3 ? "sm:grid-cols-2 lg:grid-cols-3" : "min-[1400px]:grid-cols-2"
      }`}
    >
      {COMPONENT_KEYS.map((key) => {
        const value = components[key];
        const available = value !== null && value !== undefined;
        return (
          <li key={key} className="min-w-0" title={COMPONENT_EXPLAIN[key]}>
            <div className="flex items-baseline justify-between gap-2">
              <span className="eyebrow min-w-0 truncate text-[0.5625rem]">
                {COMPONENT_LABEL[key]}
              </span>
              <span
                className={`data shrink-0 text-[11px] ${
                  available ? "text-foreground" : "text-unavail"
                }`}
              >
                {available ? (value as number).toFixed(0) : "n/a"}
              </span>
            </div>
            {available ? (
              <MeterBar
                value={value as number}
                max={100}
                color={componentColor(value as number)}
                className="mt-1"
                label={`${COMPONENT_LABEL[key]}: ${(value as number).toFixed(0)} of 100`}
              />
            ) : (
              <div
                className="mt-1 h-1.5 w-full rounded-full border border-dashed border-line"
                role="img"
                aria-label={`${COMPONENT_LABEL[key]}: not scored, data unavailable`}
              />
            )}
          </li>
        );
      })}
    </ul>
  );
}

function WinsRange({ u }: { u: Uncertainty | null | undefined }) {
  if (!u) return <span className="text-unavail">n/a</span>;
  return (
    <span className="whitespace-nowrap">
      <span className="data text-foreground">{signed(u.median)}</span>{" "}
      <span className="data text-[11px] text-muted">
        [{signed(u.p10)}, {signed(u.p90)}]
      </span>
    </span>
  );
}

function LeaderPanel({
  alt,
  score,
  retrievedAt,
  photoIdFor,
}: {
  alt: ComparisonAlternative;
  score: number | null;
  retrievedAt: string | null;
  photoIdFor: (tradeId: string, playerName: string) => number | null;
}) {
  const missing = missingComponents(alt);
  // C13: this page used to synthesize its own confidence from whether any component
  // was missing, so the same saved deal could read "Cannot fully evaluate" here and
  // "Strong fit" in the Trade Evaluator. The backend's confidence is the only one.
  const verdict = fanVerdict(score, alt.confidence);

  return (
    <Panel accent="var(--signal)" padded={false}>
      <div className="flex flex-wrap items-start gap-x-5 gap-y-3 px-4 pb-3 pt-4">
        <div className="shrink-0 text-center">
          <span
            aria-hidden
            className="numeral block text-[3.25rem] leading-[0.8] text-signal"
            style={{ textShadow: "0 0 32px rgb(34 211 238 / 0.35)" }}
          >
            1
          </span>
          <span className="eyebrow mt-1.5 block whitespace-nowrap text-signal">Leader</span>
          <span className="sr-only">Ranked first under your current weights.</span>
        </div>
        <div className="min-w-0 flex-1">
          <h3 className="title-lg truncate text-foreground">{alt.name}</h3>
          <div className="mt-1.5 flex flex-wrap items-center gap-1.5">
            <Badge status="running">leads under your weights</Badge>
            <Badge status={VERDICT_STATUS[verdict]}>{VERDICT_LABEL[verdict]}</Badge>
            <Badge status={alt.legality_status}>{LEGALITY_LABEL[alt.legality_status]}</Badge>
            {alt.dominated_by ? (
              <Badge status="unavailable">dominated</Badge>
            ) : (
              <Badge status="pass">on the frontier</Badge>
            )}
          </div>
        </div>
        <div className="text-right">
          <div className="eyebrow text-[0.5625rem]">Decision score</div>
          <div className="numeral text-[2.75rem] leading-none text-foreground">
            {score !== null ? score.toFixed(1) : "n/a"}
          </div>
        </div>
      </div>

      <div className="grid gap-x-6 gap-y-4 border-t border-hairline px-4 py-4 lg:grid-cols-[minmax(0,1.15fr)_minmax(0,1fr)]">
        <div className="min-w-0">
          <div className="eyebrow mb-1.5">Projected wins impact</div>
          <UncertaintyStrip u={alt.uncertainty} compact />
          <dl className="mt-3 flex flex-wrap gap-x-6 gap-y-2 border-t border-hairline pt-3">
            <div>
              <dt className="eyebrow text-[0.5625rem]">Δ wins [p10, p90]</dt>
              <dd className="mt-1">
                <WinsRange u={alt.uncertainty} />
              </dd>
            </div>
            <div>
              <dt className="eyebrow text-[0.5625rem]">Payroll after</dt>
              <dd className="data mt-1 whitespace-nowrap text-sm">
                {alt.payroll_after === null ? (
                  <span className="text-unavail">n/a</span>
                ) : (
                  money(alt.payroll_after)
                )}
              </dd>
            </div>
            {alt.apron_status_after && (
              <div>
                <dt className="eyebrow text-[0.5625rem]">Apron</dt>
                <dd className="mt-1 whitespace-nowrap text-sm">
                  {alt.apron_status_after.replaceAll("_", " ")}
                </dd>
              </div>
            )}
          </dl>
          <MoveList alt={alt} photoIdFor={photoIdFor} className="mt-3 border-t border-hairline pt-3" />
        </div>

        <div className="min-w-0">
          <div className="eyebrow mb-2">Component profile</div>
          <ComponentMiniBars components={alt.components} columns={2} />
          {missing.length > 0 && (
            <p className="mt-2.5 text-[11px] leading-snug text-unavail">
              Not scored — data unavailable:{" "}
              {missing.map((key) => COMPONENT_LABEL[key]).join(", ")}. The remaining weights were
              renormalized.
            </p>
          )}
        </div>
      </div>

      <div className="flex flex-wrap items-center justify-between gap-3 border-t border-hairline px-4 py-3">
        <p className="text-[11px] leading-snug text-muted">
          {LEGALITY_EXPLAIN[alt.legality_status]}
        </p>
        <ButtonLink href={`/trades/${alt.trade_id}`} size="sm" variant="secondary">
          Open the full report
        </ButtonLink>
      </div>
      <div className="px-4 pb-3">
        <SourceRail source={ENGINE_SOURCE} retrievedAt={retrievedAt} className="mt-0" />
      </div>
    </Panel>
  );
}

function ChallengerRow({
  alt,
  score,
  rank,
}: {
  alt: ComparisonAlternative;
  score: number | null;
  rank: number;
}) {
  // C13: this page used to synthesize its own confidence from whether any component
  // was missing, so the same saved deal could read "Cannot fully evaluate" here and
  // "Strong fit" in the Trade Evaluator. The backend's confidence is the only one.
  const verdict = fanVerdict(score, alt.confidence);

  return (
    <article className="rounded-lg border border-hairline bg-panel2/50 p-3.5">
      <div className="flex flex-wrap items-center gap-x-3 gap-y-2">
        <span aria-hidden className="numeral shrink-0 text-2xl leading-none text-faint">
          {rank}
        </span>
        <span className="sr-only">Rank {rank}.</span>
        <h3 className="title-md min-w-0 flex-1 truncate text-foreground">{alt.name}</h3>
        <Badge status={VERDICT_STATUS[verdict]}>{VERDICT_LABEL[verdict]}</Badge>
        {alt.dominated_by && <Badge status="unavailable">dominated</Badge>}
        <span className="numeral shrink-0 text-2xl leading-none text-foreground">
          {score !== null ? score.toFixed(1) : "n/a"}
        </span>
      </div>
      <div className="mt-2.5 flex flex-wrap items-center gap-x-5 gap-y-1 text-[12px] text-muted">
        <span className="whitespace-nowrap">
          <span className="eyebrow mr-1.5 text-[0.5625rem]">Δ wins</span>
          <WinsRange u={alt.uncertainty} />
        </span>
        <span className="whitespace-nowrap">
          <span className="eyebrow mr-1.5 text-[0.5625rem]">Payroll after</span>
          <span className="data">
            {alt.payroll_after === null ? (
              <span className="text-unavail">n/a</span>
            ) : (
              money(alt.payroll_after)
            )}
          </span>
        </span>
        <Link
          href={`/trades/${alt.trade_id}`}
          className="eyebrow ml-auto whitespace-nowrap text-signal hover:underline"
        >
          Report →
        </Link>
      </div>
      <div className="mt-3 border-t border-hairline pt-3">
        <ComponentMiniBars components={alt.components} />
      </div>
    </article>
  );
}

function MoveList({
  alt,
  photoIdFor,
  className,
}: {
  alt: ComparisonAlternative;
  photoIdFor: (tradeId: string, playerName: string) => number | null;
  className?: string;
}) {
  const sides = [
    { key: "in", label: "Coming in", players: alt.incoming },
    { key: "out", label: "Going out", players: alt.outgoing },
  ];
  return (
    <div className={`grid gap-x-5 gap-y-3 sm:grid-cols-2 ${className ?? ""}`}>
      {sides.map((side) => (
        <div key={side.key} className="min-w-0">
          <div className="eyebrow text-[0.5625rem]">{side.label}</div>
          {side.players.length === 0 ? (
            <p className="mt-1.5 text-[12px] text-faint">No players on this side.</p>
          ) : (
            <ul className="mt-1.5 space-y-1.5">
              {side.players.map((player) => (
                <li key={player.name} className="flex min-w-0 items-center gap-2">
                  <PlayerPhoto
                    nbaPlayerId={photoIdFor(alt.trade_id, player.name)}
                    name={player.name}
                    size={24}
                  />
                  <span className="min-w-0 flex-1 truncate text-[13px] text-foreground">
                    {player.name}
                  </span>
                  <span
                    className="data shrink-0 text-[11px] text-muted"
                    title="Team Efficiency Impact — projected on-court value"
                  >
                    TEI {signed(player.tei)}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </div>
      ))}
    </div>
  );
}

/* ------------------------------------------------------------------ views */

type Ranked = { alt: ComparisonAlternative; score: number | null }[];

function ViewIntro({ children }: { children: React.ReactNode }) {
  return <p className="mb-3 max-w-3xl text-[13px] leading-relaxed text-muted">{children}</p>;
}

function DealSliceCard({
  alt,
  rank,
  children,
}: {
  alt: ComparisonAlternative;
  rank: number;
  children: React.ReactNode;
}) {
  return (
    <article className="min-w-0 rounded-lg border border-hairline bg-panel2/50 p-3.5">
      <header className="flex items-center gap-2">
        <span aria-hidden className="numeral shrink-0 text-lg leading-none text-faint">
          {rank}
        </span>
        <h3 className="title-md min-w-0 flex-1 truncate text-foreground">{alt.name}</h3>
      </header>
      <div className="mt-3">{children}</div>
    </article>
  );
}

/** A single labelled component read-out with an honest n/a state. */
function ComponentReadout({
  componentKey,
  value,
}: {
  componentKey: ComponentKey;
  value: number | null | undefined;
}) {
  const available = value !== null && value !== undefined;
  return (
    <div className="min-w-0">
      <div className="flex items-baseline justify-between gap-2">
        <span className="eyebrow min-w-0 truncate">{COMPONENT_LABEL[componentKey]}</span>
        <span
          className={`numeral shrink-0 text-xl leading-none ${
            available ? "text-foreground" : "text-unavail"
          }`}
        >
          {available ? (value as number).toFixed(0) : "n/a"}
        </span>
      </div>
      {available ? (
        <MeterBar
          value={value as number}
          max={100}
          color={componentColor(value as number)}
          className="mt-1.5"
          label={`${COMPONENT_LABEL[componentKey]}: ${(value as number).toFixed(0)} of 100`}
        />
      ) : (
        <div
          className="mt-1.5 h-1.5 w-full rounded-full border border-dashed border-line"
          role="img"
          aria-label={`${COMPONENT_LABEL[componentKey]}: not scored, data unavailable`}
        />
      )}
      <p className="mt-1.5 text-[11px] leading-snug text-muted">
        {COMPONENT_EXPLAIN[componentKey]}
      </p>
    </div>
  );
}

function SummaryView({
  comparison,
  ranked,
  weights,
}: {
  comparison: ComparisonResponse;
  ranked: Ranked;
  weights: Record<string, number>;
}) {
  const order = new Map(ranked.map((entry, index) => [entry.alt.trade_id, index + 1]));
  return (
    <div>
      <div className="mb-3 flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
        <p className="max-w-3xl text-[13px] leading-relaxed text-muted">
          Every stored number for the deals on the board. Rank reflects your current sliders; the
          component columns are the saved backend scores, unchanged.
        </p>
        <p className="eyebrow shrink-0 text-[0.5625rem] text-faint">Scroll for all columns →</p>
      </div>
      <div className="scroll-thin overflow-x-auto">
        <table className="w-full min-w-[1080px] border-collapse">
          <caption className="sr-only">
            Comparison matrix across all six decision components for the selected deals
          </caption>
          <thead>
            <tr className="border-b border-line">
              <Th>Rank</Th>
              <Th>Deal</Th>
              <Th>Rules check</Th>
              <Th numeric>Score</Th>
              <Th numeric>Δ wins [p10, p90]</Th>
              {COMPONENT_KEYS.map((key) => (
                <Th key={key} numeric>
                  {COMPONENT_LABEL[key]}
                </Th>
              ))}
              <Th numeric>Payroll after</Th>
              <Th>Pareto</Th>
            </tr>
          </thead>
          <tbody>
            {ranked.map(({ alt, score }) => (
              <tr key={alt.trade_id} className="border-b border-hairline hover:bg-panel2/60">
                <Td numeric className="text-faint">
                  {order.get(alt.trade_id)}
                </Td>
                <Td>
                  <Link
                    href={`/trades/${alt.trade_id}`}
                    className="whitespace-nowrap font-medium text-foreground hover:text-signal"
                  >
                    {alt.name}
                  </Link>
                  <span className="block max-w-64 truncate text-[11px] text-muted">
                    in: {alt.incoming.map((p) => p.name).join(", ") || "—"} · out:{" "}
                    {alt.outgoing.map((p) => p.name).join(", ") || "—"}
                  </span>
                </Td>
                <Td>
                  <Badge status={alt.legality_status}>{LEGALITY_LABEL[alt.legality_status]}</Badge>
                </Td>
                <Td numeric className="font-semibold text-foreground">
                  {score !== null ? score.toFixed(1) : "n/a"}
                </Td>
                <Td numeric>
                  <WinsRange u={alt.uncertainty} />
                </Td>
                {COMPONENT_KEYS.map((key) => {
                  const value = alt.components[key];
                  return (
                    <Td key={key} numeric>
                      {value !== null && value !== undefined ? (
                        value.toFixed(0)
                      ) : (
                        <span className="text-unavail">n/a</span>
                      )}
                    </Td>
                  );
                })}
                <Td numeric>
                  {alt.payroll_after === null ? (
                    <span className="text-unavail">n/a</span>
                  ) : (
                    money(alt.payroll_after)
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
      <p className="mt-3 text-[11px] leading-relaxed text-muted">
        Δ wins is always shown with its [p10, p90] range — never a bare point estimate. Components
        marked n/a are excluded from the score and the remaining weights renormalize. {comparison.note}
      </p>
      <p className="mt-1.5 text-[11px] text-faint">
        Current weights:{" "}
        {COMPONENT_KEYS.map((key) => `${COMPONENT_LABEL[key]} ${weights[key] ?? 0}`).join(" · ")}
      </p>
    </div>
  );
}

function ImpactView({
  ranked,
  photoIdFor,
}: {
  ranked: Ranked;
  photoIdFor: (tradeId: string, playerName: string) => number | null;
}) {
  return (
    <div>
      <ViewIntro>
        On-court impact is the projected change in team performance after the rotation&apos;s
        minutes are reallocated. The wins band is the honest answer — the midpoint alone would
        overstate what the model knows.
      </ViewIntro>
      <div className="grid gap-3 lg:grid-cols-2">
        {ranked.map(({ alt }, index) => (
          <DealSliceCard key={alt.trade_id} alt={alt} rank={index + 1}>
            <ComponentReadout componentKey="performance" value={alt.components.performance} />
            <div className="mt-3.5 border-t border-hairline pt-3">
              <div className="eyebrow mb-1.5">
                Projected wins vs today · {alt.uncertainty.n_draws.toLocaleString()} simulations
              </div>
              <UncertaintyStrip u={alt.uncertainty} compact />
            </div>
            <MoveList
              alt={alt}
              photoIdFor={photoIdFor}
              className="mt-3.5 border-t border-hairline pt-3"
            />
          </DealSliceCard>
        ))}
      </div>
    </div>
  );
}

function FitView({
  ranked,
  photoIdFor,
}: {
  ranked: Ranked;
  photoIdFor: (tradeId: string, playerName: string) => number | null;
}) {
  return (
    <div>
      <ViewIntro>
        Roster fit asks whether the incoming players address this roster&apos;s measured needs
        without duplicating what it already has. The comparison stores one fit score per deal —
        the need-by-need breakdown lives on each deal&apos;s own report.
      </ViewIntro>
      <div className="grid gap-3 lg:grid-cols-2">
        {ranked.map(({ alt }, index) => (
          <DealSliceCard key={alt.trade_id} alt={alt} rank={index + 1}>
            <ComponentReadout componentKey="fit" value={alt.components.fit} />
            <MoveList
              alt={alt}
              photoIdFor={photoIdFor}
              className="mt-3.5 border-t border-hairline pt-3"
            />
            <p className="mt-3 border-t border-hairline pt-2.5 text-[11px] text-faint">
              TEI is each player&apos;s projected on-court value; it is an input to fit, not the
              fit score itself.
            </p>
          </DealSliceCard>
        ))}
      </div>
    </div>
  );
}

function FinancialView({
  ranked,
  contractsConfigured,
  contractsNote,
}: {
  ranked: Ranked;
  contractsConfigured: boolean;
  contractsNote: string | null;
}) {
  const anyFinancials = ranked.some(
    ({ alt }) => alt.components.contract !== null || alt.payroll_after !== null,
  );

  return (
    <div>
      <ViewIntro>
        Contract value weighs salary paid against estimated on-court value, and payroll-after is
        the team&apos;s book once the deal lands. Both come from imported contract data — Pivot
        never estimates a salary.
      </ViewIntro>

      {!anyFinancials && (
        <div className="mb-3">
          <UnavailableNotice
            reason={
              contractsNote ??
              "No contract provider is configured, so contract value and payroll are not scored for these deals."
            }
            steps={
              <div className="flex flex-wrap items-center gap-x-3 gap-y-2">
                <p className="text-[12px] text-muted">
                  A deal can still pass every other rule — it just cannot be called salary-legal
                  until contracts exist.
                </p>
                <ButtonLink href="/salary-cap-center" size="sm" className="ml-auto">
                  Import steps
                </ButtonLink>
              </div>
            }
          />
        </div>
      )}
      {!anyFinancials && contractsConfigured && (
        <p className="mb-3 text-[12px] text-conditional">
          A contract provider is configured but these deals still returned no contract scores —
          check coverage in Data Health.
        </p>
      )}

      <div className="grid gap-3 lg:grid-cols-2">
        {ranked.map(({ alt }, index) => (
          <DealSliceCard key={alt.trade_id} alt={alt} rank={index + 1}>
            <ComponentReadout componentKey="contract" value={alt.components.contract} />
            <dl className="mt-3.5 flex flex-wrap gap-x-8 gap-y-2 border-t border-hairline pt-3">
              <div>
                <dt className="eyebrow text-[0.5625rem]">Payroll after</dt>
                <dd className="data mt-1 whitespace-nowrap text-sm">
                  {alt.payroll_after === null ? (
                    <span className="text-unavail">n/a</span>
                  ) : (
                    money(alt.payroll_after)
                  )}
                </dd>
              </div>
              <div>
                <dt className="eyebrow text-[0.5625rem]">Apron status after</dt>
                <dd className="mt-1 whitespace-nowrap text-sm">
                  {alt.apron_status_after ? (
                    alt.apron_status_after.replaceAll("_", " ")
                  ) : (
                    <span className="text-unavail">n/a</span>
                  )}
                </dd>
              </div>
              <div className="min-w-0">
                <dt className="eyebrow text-[0.5625rem]">Rules check</dt>
                <dd className="mt-1">
                  <Badge status={alt.legality_status}>{LEGALITY_LABEL[alt.legality_status]}</Badge>
                </dd>
              </div>
            </dl>
          </DealSliceCard>
        ))}
      </div>
    </div>
  );
}

function TimelineView({ ranked }: { ranked: Ranked }) {
  return (
    <div>
      <ViewIntro>
        Two questions about time: does the age profile of this deal match the window the team is
        building for, and what does it do to future optionality — picks, flexibility and roster
        slots.
      </ViewIntro>
      <div className="grid gap-3 lg:grid-cols-2">
        {ranked.map(({ alt }, index) => {
          const bothMissing =
            alt.components.timeline === null && alt.components.assets === null;
          return (
            <DealSliceCard key={alt.trade_id} alt={alt} rank={index + 1}>
              <div className="grid gap-4 sm:grid-cols-2">
                <ComponentReadout componentKey="timeline" value={alt.components.timeline} />
                <ComponentReadout componentKey="assets" value={alt.components.assets} />
              </div>
              {bothMissing && (
                <p className="mt-3 border-t border-hairline pt-2.5 text-[11px] text-unavail">
                  Neither window nor flexibility could be scored for this deal — both are excluded
                  from the decision score rather than filled in.
                </p>
              )}
            </DealSliceCard>
          );
        })}
      </div>
    </div>
  );
}

function RiskView({ ranked }: { ranked: Ranked }) {
  return (
    <div>
      <ViewIntro>
        Risk is <em>availability exposure</em> and nothing else — the minutes-weighted change in
        historical games played between the players arriving and the players leaving. It used to
        blend in the share of simulations in which the deal helps, which is the on-court
        projection restated as a probability; the two components were 0.86 correlated, so the
        composite counted the same thing twice. The simulation is still shown below, and is
        deliberately not scored.
      </ViewIntro>
      <div className="grid gap-3 lg:grid-cols-2">
        {ranked.map(({ alt }, index) => (
          <DealSliceCard key={alt.trade_id} alt={alt} rank={index + 1}>
            <ComponentReadout componentKey="risk" value={alt.components.risk} />
            <dl className="mt-3.5 flex flex-wrap gap-x-8 gap-y-2 border-t border-hairline pt-3">
              <div>
                <dt className="eyebrow text-[0.5625rem]">Chance it helps</dt>
                <dd className="numeral mt-1 text-xl leading-none text-signal">
                  {pct(alt.uncertainty.prob_positive)}
                </dd>
              </div>
              <div>
                <dt className="eyebrow text-[0.5625rem]">Δ wins [p10, p90]</dt>
                <dd className="mt-1 text-sm">
                  <WinsRange u={alt.uncertainty} />
                </dd>
              </div>
              <div>
                <dt className="eyebrow text-[0.5625rem]">Simulations</dt>
                <dd className="data mt-1 whitespace-nowrap text-sm">
                  {alt.uncertainty.n_draws.toLocaleString()}
                </dd>
              </div>
            </dl>
            {alt.uncertainty.top_uncertainty_drivers.length > 0 && (
              <div className="mt-3 border-t border-hairline pt-3">
                <div className="eyebrow mb-1.5">Where the spread comes from</div>
                <ul className="space-y-1">
                  {alt.uncertainty.top_uncertainty_drivers.map((driver, driverIndex) => (
                    <li
                      key={`${driver.side}-${driverIndex}`}
                      className="flex items-baseline justify-between gap-3 text-[12px]"
                    >
                      <span className="min-w-0 truncate text-muted">
                        {driver.side === "incoming" ? "Incoming player" : "Outgoing player"}
                      </span>
                      <span className="data shrink-0 text-foreground">
                        ±{driver.spread_wins.toFixed(2)} wins
                      </span>
                    </li>
                  ))}
                </ul>
              </div>
            )}
            <p className="mt-3 border-t border-hairline pt-2.5 text-[11px] leading-snug text-muted">
              {LEGALITY_EXPLAIN[alt.legality_status]}
            </p>
          </DealSliceCard>
        ))}
      </div>
    </div>
  );
}

function SensitivityView({
  comparison,
  names,
}: {
  comparison: ComparisonResponse;
  names: Record<string, string>;
}) {
  const share = comparison.sensitivity.first_place_share;
  const volatility = comparison.sensitivity.rank_volatility;
  const medianRank = comparison.sensitivity.median_rank;
  const ids = Object.keys(share);

  return (
    <div>
      <ViewIntro>
        The saved backend analysis: the board is re-ranked under hundreds of sampled weight
        vectors. A deal that only leads under one exact set of priorities is not a robust
        recommendation. This section is independent of the sliders.
      </ViewIntro>
      <div className="grid gap-5 lg:grid-cols-2">
        <div className="min-w-0">
          <FirstPlaceShareBars share={share} names={names} />

          <div className="scroll-thin mt-4 overflow-x-auto border-t border-hairline pt-3">
            <table className="w-full min-w-[440px] border-collapse">
              <caption className="sr-only">Rank stability under sampled strategy weights</caption>
              <thead>
                <tr className="border-b border-line">
                  <Th>Deal</Th>
                  <Th numeric>Ranks #1</Th>
                  <Th numeric>Median rank</Th>
                  <Th numeric>Volatility</Th>
                </tr>
              </thead>
              <tbody>
                {ids.map((id) => (
                  <tr key={id} className="border-b border-hairline">
                    <Td>
                      <span className="whitespace-nowrap">{names[id] ?? id.slice(0, 8)}</span>
                    </Td>
                    <Td numeric>{pct(share[id])}</Td>
                    <Td numeric>{medianRank[id]?.toFixed(1) ?? "n/a"}</Td>
                    <Td numeric>{volatility[id]?.toFixed(2) ?? "n/a"}</Td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="mt-2 text-[11px] leading-snug text-muted">
            Rank volatility is the standard deviation of a deal&apos;s rank across the sampled
            weightings — lower means the answer barely moves when priorities change.
          </p>
        </div>
        <div className="min-w-0">
          <ParetoScatter
            points={comparison.alternatives
              .filter(
                (alt) => alt.components.performance !== null && alt.components.risk !== null,
              )
              .map((alt) => ({
                name: alt.name,
                x: alt.components.performance as number,
                y: alt.components.risk as number,
                dominated: !!alt.dominated_by,
              }))}
          />
          {(() => {
            const omitted = comparison.alternatives.filter(
              (alt) => alt.components.performance === null || alt.components.risk === null,
            );
            return omitted.length > 0 ? (
              <p className="mt-1.5 text-[11px] text-unavail">
                {omitted.length} deal{omitted.length === 1 ? " is" : "s are"} not plotted: on-court
                impact or availability exposure could not be scored. They used to be drawn at 0,
                which reads as the worst deal on the board rather than as an unknown.
              </p>
            ) : null;
          })()}
          <p className="mt-1.5 text-[11px] leading-snug text-faint">
            The two axes are now genuinely different questions — projected wins against
            games-missed exposure. Before R5 they were 0.86 correlated and this chart was close to
            a diagonal line.
          </p>
        </div>
      </div>
    </div>
  );
}
