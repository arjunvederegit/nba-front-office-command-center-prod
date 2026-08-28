"use client";

/**
 * Saved deal report.
 *
 * Verdict first — the rules check, then each team's own read on the deal. Per-team
 * tabs repeat the evaluator's result hierarchy: decision score, what drove it,
 * the projected-wins band, the money, sensitivity, and the rule audit trail.
 */

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { use, useState } from "react";
import { api } from "@/lib/api";
import { tradeDetailSchema } from "@/lib/schemas";
import { COMPONENT_EXPLAIN, COMPONENT_LABEL, LEGALITY_EXPLAIN, LEGALITY_LABEL, VERDICT_LABEL, VERDICT_STATUS, count, fanVerdict, formatDate, money, tei } from "@/lib/format";
import { teamIdentity, teamVars } from "@/lib/teamIdentity";
import type { TeamEvaluation, TradeDetail } from "@/lib/types";
import { ComponentBars, TornadoChart, UncertaintyStrip } from "@/components/charts";
import { KeyFrame } from "@/components/court";
import { TeamLogo } from "@/components/media";
import {
  Badge,
  ButtonLink,
  ErrorState,
  Panel,
  Skeleton,
  SourceRail,
  StatBlock,
  Tabs,
  UnavailableNotice,
} from "@/components/ui";

const LEGALITY_ACCENT: Record<string, string> = {
  verified_legal: "var(--legal)",
  verified_illegal: "var(--illegal)",
  conditionally_valid: "var(--conditional)",
  not_evaluated: "var(--unknown)",
};

export default function TradeReportPage({ params }: { params: Promise<{ tradeId: string }> }) {
  const { tradeId } = use(params);
  const { data: trade, error } = useQuery({
    queryKey: ["trade", tradeId],
    queryFn: () => api.get<TradeDetail>(`/trades/${tradeId}`, tradeDetailSchema),
  });
  const [activeTeam, setActiveTeam] = useState<string | null>(null);

  if (error) return <ErrorState message={`Could not load this deal: ${String(error)}`} />;
  if (!trade) return <TradeSkeleton />;

  const teamId = activeTeam ?? trade.teams[0]?.team_id;
  const evaluation: TeamEvaluation | undefined = trade.evaluations[teamId];
  const activeTeamMeta = trade.teams.find((team) => team.team_id === teamId);
  const identity = teamIdentity(activeTeamMeta?.abbreviation);
  const legalityAccent = LEGALITY_ACCENT[trade.legality.overall_status] ?? "var(--unknown)";

  return (
    <div className="space-y-6">
      <PageTop trade={trade} />

      {/* ------------------------------------------------------------ verdict */}
      <section className="grid gap-3 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.05fr)]">
        <Panel
          accent={legalityAccent}
          padded={false}
          className="flex min-w-0 flex-col justify-center"
        >
          <KeyFrame accent={legalityAccent} className="px-5 pb-5 pt-7 text-center">
            <div className="eyebrow">Rules check</div>
            <h2
              className="title-lg mt-2 whitespace-nowrap"
              style={{ color: legalityAccent }}
            >
              {LEGALITY_LABEL[trade.legality.overall_status] ?? trade.legality.overall_status}
            </h2>
            <p className="mx-auto mt-2 max-w-md text-[13px] leading-relaxed text-muted">
              {LEGALITY_EXPLAIN[trade.legality.overall_status]}
            </p>
            {!trade.legality.contract_provider_configured && (
              <p className="mx-auto mt-3 max-w-md rounded-md border border-unavail/35 bg-unavail/8 px-3 py-2 text-[12px] leading-relaxed text-muted">
                Contract data isn&apos;t configured, so salary-matching and apron rules could not be
                verified. This deal is <strong className="text-foreground">not</strong> being called
                legal.{" "}
                <Link href="/data-health" className="text-signal underline">
                  What&apos;s missing
                </Link>
              </p>
            )}
            <SourceRail
              className="mx-auto mt-4 max-w-md justify-center"
              source={trade.legality.cap_parameters_source}
              retrievedAt={trade.created_at}
              extra={
                <span className="whitespace-nowrap">· league year {trade.legality.league_year}</span>
              }
            />
          </KeyFrame>
        </Panel>

        <Panel title="Each team's read" subtitle="Decision score out of 100 · 50 is neutral">
          <ul className="divide-y divide-hairline">
            {trade.teams.map((team) => {
              const teamEval = trade.evaluations[team.team_id];
              const teamIdentityColors = teamIdentity(team.abbreviation);
              const verdict = fanVerdict(teamEval?.composite_utility, teamEval?.confidence);
              return (
                <li key={team.team_id} className="py-3">
                  <div className="flex items-center gap-3">
                    <TeamLogo abbreviation={team.abbreviation} size={30} decorative />
                    <span className="title-md min-w-0 flex-1 truncate text-foreground">
                      {team.name}
                    </span>
                    <span
                      className="numeral shrink-0 text-right text-[1.75rem] leading-none"
                      style={{ color: teamIdentityColors.bright }}
                    >
                      {teamEval?.composite_utility?.toFixed(1) ?? "—"}
                    </span>
                  </div>
                  <div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1.5 pl-[42px]">
                    <Badge status={VERDICT_STATUS[verdict]}>{VERDICT_LABEL[verdict]}</Badge>
                    <span className="eyebrow whitespace-nowrap text-[0.5625rem]">
                      {LEGALITY_LABEL[
                        trade.legality.teams[team.team_id]?.status ?? "not_evaluated"
                      ] ?? "not checked"}
                    </span>
                  </div>
                </li>
              );
            })}
          </ul>
          <p className="mt-3 text-[11px] leading-relaxed text-faint">
            The score blends six components under this team&apos;s strategy weights; components with
            missing data are dropped and the rest re-scaled, never estimated.{" "}
            <Link href="/methodology#utility" className="text-signal underline">
              How the score works
            </Link>
          </p>
        </Panel>
      </section>

      {/* ------------------------------------------------------------- assets */}
      <section>
        <SectionRail title="What moves" aside={`${count(trade.assets.length, "asset")} across ${count(trade.teams.length, "team")}`} />
        <div
          className={`grid gap-3 ${
            trade.teams.length >= 3 ? "lg:grid-cols-3" : "md:grid-cols-2"
          }`}
        >
          {trade.teams.map((team) => {
            const receives = trade.assets.filter((asset) => asset.to_team_id === team.team_id);
            const sends = trade.assets.filter((asset) => asset.from_team_id === team.team_id);
            const colors = teamIdentity(team.abbreviation);
            return (
              <Panel
                key={team.team_id}
                accent={colors.bright}
                title={
                  <span className="flex items-center gap-2">
                    <TeamLogo abbreviation={team.abbreviation} size={20} decorative />
                    <span className="truncate">{team.name}</span>
                  </span>
                }
                className="min-w-0"
              >
                <div className="space-y-3">
                  <AssetList
                    label="Receives"
                    assets={receives}
                    tone="var(--legal)"
                    emptyText="nothing"
                  />
                  <AssetList
                    label="Sends"
                    assets={sends}
                    tone="var(--illegal)"
                    emptyText="nothing"
                  />
                </div>
              </Panel>
            );
          })}
        </div>
      </section>

      {/* ---------------------------------------------------- team perspective */}
      <section style={teamVars(activeTeamMeta?.abbreviation)}>
        <SectionRail
          title="Team perspective"
          aside="Every number below is scored from the selected team's side"
        />
        <div className="border-b border-hairline">
          <Tabs
            ariaLabel="Team perspective"
            active={teamId}
            onChange={setActiveTeam}
            tabs={trade.teams.map((team) => ({
              id: team.team_id,
              label: `${team.abbreviation} perspective`,
            }))}
          />
        </div>

        {!evaluation ? (
          <div className="mt-3">
            <UnavailableNotice reason="No stored evaluation exists for this team on this deal." />
          </div>
        ) : evaluation.decision_status !== "scored" ? (
          <div className="mt-3">
            <SuppressedDecision
              evaluation={evaluation}
              teamAbbreviations={Object.fromEntries(
                trade.teams.map((t) => [t.team_id, t.abbreviation]),
              )}
            />
          </div>
        ) : (
          <div className="mt-3 space-y-3">
            {/* headline result */}
            <Panel accent={identity.bright} padded={false}>
              <div className="grid grid-cols-2 gap-x-6 gap-y-5 px-5 py-4 lg:grid-cols-4">
                <StatBlock
                  label="Decision score"
                  value={evaluation.composite_utility?.toFixed(1) ?? "—"}
                  note="out of 100 · 50 neutral"
                  accent={identity.bright}
                />
                <StatBlock
                  label="Confidence"
                  value={evaluation.confidence}
                  note={
                    evaluation.excluded_components.length > 0
                      ? `${evaluation.excluded_components.length} component(s) unscored`
                      : "all components scored"
                  }
                  accent={
                    evaluation.confidence === "low" ? "var(--conditional)" : "var(--chalk)"
                  }
                />
                <StatBlock
                  label="Projected wins"
                  value={`${evaluation.uncertainty.median >= 0 ? "+" : ""}${evaluation.uncertainty.median.toFixed(1)}`}
                  note={
                    evaluation.uncertainty.prob_positive === null
                      ? "no outcome distribution"
                      : `${(evaluation.uncertainty.prob_positive * 100).toFixed(0)}% chance it helps`
                  }
                  accent="var(--signal)"
                />
                <StatBlock
                  label="Roster spots"
                  value={`${evaluation.legality.roster_before} → ${evaluation.legality.roster_after}`}
                  note="post-trade roster count"
                />
              </div>
              {evaluation.has_unmodeled_players &&
                (evaluation.unmodeled_players?.length ?? 0) > 0 && (
                  // Named rather than silently averaged: before R1-4 a player with no
                  // impact estimate arrived carrying tei = 0.0, the 63rd percentile.
                  <p className="border-t border-hairline px-5 py-2.5 text-[11px] leading-snug text-unavail">
                    Left out of the projection for want of an impact estimate (they still
                    count against the roster limits):{" "}
                    {evaluation.unmodeled_players?.join(", ")}.
                  </p>
                )}
            </Panel>

            <div className="grid items-start gap-3 xl:grid-cols-2">
              <Panel className="min-w-0">
                <ComponentBars
                  components={evaluation.components}
                  excluded={evaluation.excluded_components}
                />
                <p className="mt-2 text-[11px] leading-relaxed text-faint">
                  Weights:{" "}
                  {Object.entries(evaluation.weights)
                    .map(
                      ([key, value]) =>
                        `${COMPONENT_LABEL[key] ?? key} ${(value * 100).toFixed(0)}%`,
                    )
                    .join(" · ")}
                </p>
                {evaluation.drivers && evaluation.drivers.length > 0 && (
                  <ul className="mt-3 space-y-1 border-t border-hairline pt-3">
                    {evaluation.drivers.slice(0, 3).map((driver) => (
                      <li
                        key={driver.component}
                        className="flex items-baseline gap-2 text-[12px] text-muted"
                        title={COMPONENT_EXPLAIN[driver.component]}
                      >
                        <span
                          className="data shrink-0"
                          style={{
                            color:
                              driver.contribution >= 0 ? "var(--legal)" : "var(--illegal)",
                          }}
                        >
                          {driver.contribution >= 0 ? "+" : ""}
                          {driver.contribution.toFixed(2)}
                        </span>
                        <span className="min-w-0">
                          <span className="text-foreground">
                            {COMPONENT_LABEL[driver.component] ?? driver.component}
                          </span>{" "}
                          at {(driver.weight * 100).toFixed(0)}% weight
                        </span>
                      </li>
                    ))}
                  </ul>
                )}
                <SourceRail
                  source="Pivot evaluation engine"
                  retrievedAt={evaluation.evaluated_at}
                />
              </Panel>

              <Panel className="min-w-0">
                <UncertaintyStrip u={evaluation.uncertainty} />
                <div className="mt-4 grid gap-2 sm:grid-cols-2">
                  <MoveList
                    label="In"
                    players={evaluation.incoming}
                    tone="var(--legal)"
                  />
                  <MoveList
                    label="Out"
                    players={evaluation.outgoing}
                    tone="var(--illegal)"
                  />
                </div>
                <div className="mt-3 grid gap-2 sm:grid-cols-2">
                  <MoneyBlock
                    label="Salary movement"
                    value={`in ${money(evaluation.legality.incoming_salary)} · out ${money(
                      evaluation.legality.outgoing_salary,
                    )}`}
                  />
                  <MoneyBlock
                    label="Payroll / apron after"
                    value={`${money(evaluation.legality.payroll_after)} · ${
                      evaluation.legality.apron_status_after ?? "unavailable"
                    }`}
                  />
                </div>
              </Panel>

              <Panel className="min-w-0">
                {evaluation.sensitivity_tornado.length === 0 ? (
                  <UnavailableNotice reason="No sensitivity bars were stored with this evaluation." />
                ) : (
                  <>
                    <TornadoChart bars={evaluation.sensitivity_tornado} />
                    <p className="mt-2 text-[11px] leading-relaxed text-faint">
                      Each weight swung ±50% while the remaining weights re-scale.
                    </p>
                  </>
                )}
              </Panel>

              <Panel
                className="min-w-0"
                title="Rule audit trail"
                subtitle="Every rule the engine ran for this team, with its source reference"
              >
                <RuleAudit
                  rules={trade.legality.rule_results.filter(
                    (rule) => !rule.team_id || rule.team_id === teamId,
                  )}
                />
                <SourceRail
                  source={trade.legality.cap_parameters_source}
                  retrievedAt={undefined}
                  extra={
                    <Link href="/methodology#rules" className="text-signal underline">
                      rule coverage
                    </Link>
                  }
                />
              </Panel>
            </div>
          </div>
        )}
      </section>
    </div>
  );
}

/* ------------------------------------------------------------------ header */

function PageTop({ trade }: { trade: TradeDetail }) {
  const legalityAccent = LEGALITY_ACCENT[trade.legality.overall_status] ?? "var(--unknown)";
  return (
    <header className="mb-1">
      <div
        className="h-px w-full"
        style={{ background: `linear-gradient(90deg, ${legalityAccent}, transparent 60%)` }}
      />
      <div className="flex flex-wrap items-end justify-between gap-x-6 gap-y-3 pt-3">
        <div className="min-w-0">
          <div className="eyebrow mb-1.5 flex flex-wrap items-center gap-x-2 gap-y-1">
            <span>Saved deal</span>
            <span aria-hidden className="text-faint">
              /
            </span>
            <span>created {formatDate(trade.created_at)}</span>
          </div>
          <h1 className="title-lg whitespace-nowrap text-foreground">{trade.name}</h1>
          <div className="mt-2 flex flex-wrap items-center gap-2">
            {trade.teams.map((team, index) => (
              <span key={team.team_id} className="flex items-center gap-2">
                {index > 0 && (
                  <span aria-hidden className="text-faint">
                    ↔
                  </span>
                )}
                <span className="inline-flex items-center gap-1.5 whitespace-nowrap rounded-full border border-hairline px-2 py-0.5 text-[12px]">
                  <TeamLogo abbreviation={team.abbreviation} size={16} decorative />
                  <span className="numeral text-[13px] leading-none">{team.abbreviation}</span>
                </span>
              </span>
            ))}
            <Badge status={trade.legality.overall_status}>
              {LEGALITY_LABEL[trade.legality.overall_status] ?? trade.legality.overall_status}
            </Badge>
          </div>
        </div>
        <div className="flex min-w-0 flex-wrap items-center gap-2 sm:shrink-0">
          <ButtonLink href={`/trade-evaluator?load=${trade.id}`} variant="primary" size="sm">
            Clone &amp; modify
          </ButtonLink>
          <a
            href={`/api/v1/trades/${trade.id}/report`}
            target="_blank"
            rel="noreferrer"
            className="inline-flex items-center justify-center gap-1.5 whitespace-nowrap rounded-md border border-line bg-panel2 px-3 py-1.5 text-[13px] text-foreground transition-colors hover:border-signal/50"
          >
            Report (Markdown)
          </a>
          <a
            href={`/api/v1/trades/${trade.id}/report?format=html`}
            target="_blank"
            rel="noreferrer"
            className="inline-flex items-center justify-center gap-1.5 whitespace-nowrap rounded-md border border-transparent bg-signal px-3 py-1.5 text-[13px] font-semibold text-court transition-[filter] hover:brightness-110"
          >
            Report (print)
          </a>
        </div>
      </div>
      {trade.notes && (
        <p className="mt-3 max-w-3xl border-l-2 border-hairline pl-3 text-sm leading-relaxed text-muted">
          {trade.notes}
        </p>
      )}
    </header>
  );
}

/* ------------------------------------------------------------------ pieces */

function SectionRail({ title, aside }: { title: string; aside?: string }) {
  return (
    <div className="mb-3">
      <div className="h-px w-full bg-gradient-to-r from-signal/60 to-transparent" />
      <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1 pt-2.5">
        <h2 className="title-lg whitespace-nowrap text-foreground">{title}</h2>
        {aside && <p className="text-[11px] text-faint">{aside}</p>}
      </div>
    </div>
  );
}

function AssetList({
  label,
  assets,
  tone,
  emptyText,
}: {
  label: string;
  assets: TradeDetail["assets"];
  tone: string;
  emptyText: string;
}) {
  return (
    <div>
      <div className="eyebrow text-[0.5625rem]" style={{ color: tone }}>
        {label}
      </div>
      {assets.length === 0 ? (
        <p className="mt-1 text-sm text-faint">{emptyText}</p>
      ) : (
        <ul className="mt-1.5 space-y-1">
          {assets.map((asset, index) => (
            <li key={index} className="flex flex-wrap items-center gap-2 text-sm">
              <span
                aria-hidden
                className="h-1.5 w-1.5 shrink-0 rounded-full"
                style={{ background: tone }}
              />
              {asset.asset_type === "player" && asset.player_id ? (
                <Link
                  href={`/players/${asset.player_id}`}
                  className="min-w-0 truncate transition-colors hover:text-signal"
                >
                  {asset.player_name}
                </Link>
              ) : (
                <span className="min-w-0 truncate">
                  {asset.draft_year} round {asset.round_number} pick
                  {asset.protections ? ` (${asset.protections})` : ""}
                </span>
              )}
              {asset.is_hypothetical && <Badge status="unavailable">hypothetical</Badge>}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

/**
 * A deal that fails a verified rule cannot happen, so it gets no decision score. The
 * refusal is shown with the rules that caused it — an unexplained "—" would read as a
 * bug rather than as an answer.
 */
function SuppressedDecision({
  evaluation,
  teamAbbreviations,
}: {
  evaluation: TeamEvaluation;
  teamAbbreviations: Record<string, string>;
}) {
  const suppressed = evaluation.decision_status === "suppressed_illegal";
  const rules = evaluation.suppression?.failing_rules ?? [];
  return (
    <Panel accent={suppressed ? "var(--illegal)" : "var(--unavail)"}>
      <div className="flex flex-wrap items-center gap-2">
        <Badge status={suppressed ? "verified_illegal" : "unavailable"}>
          {suppressed ? "No decision score — deal is illegal" : "No decision score"}
        </Badge>
      </div>
      <p className="mt-2 max-w-prose text-sm text-muted">
        {evaluation.suppression?.message ??
          "No component could be scored for this team with the data available."}
      </p>
      {rules.length > 0 && (
        <ul className="mt-3 space-y-2">
          {rules.map((rule, index) => (
            <li
              key={`${rule.rule_code}-${rule.team_id ?? "all"}-${index}`}
              className="rounded-lg border border-hairline bg-panel2 px-3 py-2"
            >
              <div className="eyebrow flex flex-wrap items-center gap-2 text-[0.5625rem] text-illegal">
                <span>{rule.rule_code}</span>
                {/* The failing side matters: a deal can be illegal because of the
                    counterparty, and hiding that reads as an error on this team. */}
                {rule.team_id && teamAbbreviations[rule.team_id] && (
                  <span className="text-unavail">
                    fails for {teamAbbreviations[rule.team_id]}
                  </span>
                )}
              </div>
              <p className="mt-0.5 text-sm text-foreground">{rule.message}</p>
              {rule.source_reference && (
                <p className="mt-1 text-[11px] text-faint">ref {rule.source_reference}</p>
              )}
            </li>
          ))}
        </ul>
      )}
      <div className="mt-3 grid gap-2 sm:grid-cols-2">
        <MoveList label="In" players={evaluation.incoming} tone="var(--legal)" />
        <MoveList label="Out" players={evaluation.outgoing} tone="var(--illegal)" />
      </div>
      <div className="mt-3 grid gap-2 sm:grid-cols-2">
        <MoneyBlock
          label="Salary movement"
          value={`in ${money(evaluation.legality.incoming_salary)} · out ${money(
            evaluation.legality.outgoing_salary,
          )}`}
        />
        <MoneyBlock
          label="Roster spots"
          value={`${evaluation.legality.roster_before} → ${evaluation.legality.roster_after}`}
        />
      </div>
    </Panel>
  );
}

function MoveList({
  label,
  players,
  tone,
}: {
  label: string;
  players: { player_id: string; name: string; tei: number | null }[];
  tone: string;
}) {
  return (
    <div className="rounded-lg border border-hairline bg-panel2 px-3 py-2.5">
      <div className="eyebrow text-[0.5625rem]" style={{ color: tone }}>
        {label}
      </div>
      {players.length === 0 ? (
        <p className="mt-1 text-sm text-faint">nobody</p>
      ) : (
        <ul className="mt-1.5 space-y-1">
          {players.map((player) => (
            <li key={player.player_id} className="flex items-baseline gap-2 text-sm">
              <Link
                href={`/players/${player.player_id}`}
                className="min-w-0 flex-1 truncate transition-colors hover:text-signal"
              >
                {player.name}
              </Link>
              <span className="data shrink-0 text-[13px] text-muted">{tei(player.tei)}</span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function MoneyBlock({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-lg border border-hairline bg-panel2 px-3 py-2.5">
      <div className="eyebrow text-[0.5625rem]">{label}</div>
      <div className="data mt-1 text-[13px] leading-snug text-foreground">{value}</div>
    </div>
  );
}

function RuleAudit({ rules }: { rules: TradeDetail["legality"]["rule_results"] }) {
  if (rules.length === 0) {
    return <UnavailableNotice reason="No rules were run for this team." />;
  }
  return (
    <ul className="scroll-thin max-h-80 space-y-2 overflow-y-auto pr-1">
      {rules.map((rule, index) => (
        <li key={`${rule.rule_code}-${index}`} className="flex items-start gap-2.5">
          <Badge status={rule.status} className="mt-0.5 shrink-0">
            {rule.status}
          </Badge>
          <div className="min-w-0">
            <div className="data text-[11px] uppercase tracking-wider text-muted">
              {rule.rule_code}
            </div>
            <p className="text-[13px] leading-relaxed text-foreground">{rule.message}</p>
            {rule.source_reference && (
              <p className="mt-0.5 text-[10px] text-faint">
                ref {rule.source_reference} · confidence {rule.confidence}
              </p>
            )}
          </div>
        </li>
      ))}
    </ul>
  );
}

function TradeSkeleton() {
  return (
    <div className="space-y-6" role="status" aria-label="Loading deal">
      <div className="space-y-3">
        <Skeleton className="h-4 w-40" />
        <Skeleton className="h-9 w-80 max-w-full" />
        <Skeleton className="h-6 w-56" />
      </div>
      <div className="grid gap-3 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.05fr)]">
        <Skeleton className="h-56" />
        <Skeleton className="h-56" />
      </div>
      <div className="grid gap-3 md:grid-cols-2">
        <Skeleton className="h-40" />
        <Skeleton className="h-40" />
      </div>
      <div className="grid gap-3 xl:grid-cols-2">
        <Skeleton className="h-72" />
        <Skeleton className="h-72" />
      </div>
    </div>
  );
}
