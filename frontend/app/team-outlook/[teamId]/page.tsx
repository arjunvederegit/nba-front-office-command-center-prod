"use client";

/**
 * Team Outlook — one franchise, read the way a broadcast opens: banner, record,
 * then the roster and the model's read on what this team is good at, what it
 * needs, and where its money stands.
 */

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { use, useState } from "react";
import { api } from "@/lib/api";
import { NEED_LABEL, height, money, ordinal, pct, tei } from "@/lib/format";
import { selectStrengths, selectWeaknesses } from "@/lib/needs";
import { teamIdentity, teamVars } from "@/lib/teamIdentity";
import type {
  PayrollResponse,
  RosterPlayer,
  RosterResponse,
  Scenario,
  Team,
  TeamNeedItem,
} from "@/lib/types";
import { HalfCourt } from "@/components/court";
import { PlayerPhoto, TeamCrest } from "@/components/media";
import { useToast } from "@/components/toast";
import {
  Badge,
  Button,
  ButtonLink,
  EmptyState,
  ErrorState,
  MeterBar,
  Panel,
  Skeleton,
  SkeletonRows,
  SourceRail,
  StatBlock,
  UnavailableNotice,
} from "@/components/ui";

interface TeamDetail {
  team: Team;
  season: string;
  standing: {
    wins: number;
    losses: number;
    win_pct: number;
    conference: string | null;
    playoff_rank: number | null;
    details: Record<string, unknown>;
    source_retrieved_at: string | null;
  } | null;
  stats: Record<string, Record<string, number>>;
  stats_retrieved_at: string | null;
}

const STRATEGIES = [
  ["contend", "Contend now", "Win this season; future flexibility is secondary."],
  ["improve", "Improve, keep flexibility", "Get better without mortgaging the books."],
  ["retool", "Re-tool around the core", "Change the supporting cast, keep the stars."],
  ["rebuild", "Rebuild", "Trade present value for future value."],
  ["youth", "Chase young upside", "Prioritize age and development curves."],
  ["cap_relief", "Cut salary / tax", "Get under a line, accept on-court cost."],
] as const;

const GROUPS = ["Guards", "Wings", "Bigs"] as const;
type Group = (typeof GROUPS)[number];

function positionGroup(position: string | null): Group {
  // Official position strings (G, G-F, F, F-C, C, …) grouped for scanning; the
  // exact designation stays visible on each row.
  const p = (position ?? "").toUpperCase();
  if (p.includes("C")) return "Bigs";
  if (p.includes("G") && !p.includes("F")) return "Guards";
  return "Wings";
}

function windowLabel(avgAge: number | null): {
  label: string;
  hint: string;
  status: string;
  color: string;
} {
  if (avgAge === null)
    return {
      label: "Unknown",
      hint: "Roster ages are unavailable, so the window can't be inferred.",
      status: "unavailable",
      color: "var(--unknown)",
    };
  if (avgAge < 25.5)
    return {
      label: "Ascending",
      hint: "Young rotation — the window is opening.",
      status: "info",
      color: "var(--signal)",
    };
  if (avgAge < 28.5)
    return {
      label: "Open now",
      hint: "Prime-age rotation — win-now moves fit.",
      status: "pass",
      color: "var(--legal)",
    };
  return {
    label: "Closing",
    hint: "Veteran rotation — weigh future flexibility carefully.",
    status: "warning",
    color: "var(--conditional)",
  };
}

export default function TeamOutlookPage({ params }: { params: Promise<{ teamId: string }> }) {
  const { teamId } = use(params);
  const toast = useToast();
  const queryClient = useQueryClient();

  const { data: detail, error } = useQuery({
    queryKey: ["team", teamId],
    queryFn: () => api.get<TeamDetail>(`/teams/${teamId}`),
  });
  const { data: roster } = useQuery({
    queryKey: ["roster", teamId],
    queryFn: () => api.get<RosterResponse>(`/teams/${teamId}/roster`),
  });
  const { data: needs } = useQuery({
    queryKey: ["needs", teamId],
    queryFn: () => api.get<{ needs: TeamNeedItem[]; note: string | null }>(`/teams/${teamId}/needs`),
  });
  const { data: payroll } = useQuery({
    queryKey: ["payroll", teamId],
    queryFn: () => api.get<PayrollResponse>(`/teams/${teamId}/payroll`),
  });

  const [strategy, setStrategy] = useState<string>("contend");
  const saveStrategy = useMutation({
    mutationFn: () =>
      api.post<Scenario>("/scenarios", {
        name: `${detail?.team.abbreviation} — ${STRATEGIES.find(([value]) => value === strategy)?.[1]}`,
        focal_team_id: teamId,
        strategy,
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["scenarios"] });
      toast("success", "Strategy saved — it now drives trade evaluations for this team.");
    },
    onError: (e) => toast("error", `Could not save strategy: ${String(e)}`),
  });

  if (error) return <ErrorState message={`Could not load team: ${String(error)}`} />;
  if (!detail) return <TeamSkeleton />;

  const identity = teamIdentity(detail.team.abbreviation);
  const advanced = detail.stats.advanced ?? {};
  const rosterPlayers = roster?.roster ?? [];
  const ages = rosterPlayers.map((p) => p.age).filter((a): a is number => a !== null);
  const avgAge = ages.length ? ages.reduce((sum, a) => sum + a, 0) / ages.length : null;
  const topRotation = [...rosterPlayers].sort((a, b) => (b.tei ?? -99) - (a.tei ?? -99)).slice(0, 8);
  const rotationAges = topRotation.map((p) => p.age).filter((a): a is number => a !== null);
  const avgRotationAge = rotationAges.length
    ? rotationAges.reduce((sum, a) => sum + a, 0) / rotationAges.length
    : null;
  const competitiveWindow = windowLabel(avgRotationAge);

  const sortedNeeds = needs?.needs ?? [];
  const weaknesses = selectWeaknesses(sortedNeeds);
  const strengths = selectStrengths(sortedNeeds);

  const groups: Record<Group, RosterPlayer[]> = { Guards: [], Wings: [], Bigs: [] };
  for (const player of rosterPlayers) groups[positionGroup(player.position)].push(player);
  for (const group of GROUPS) groups[group].sort((a, b) => (b.tei ?? -99) - (a.tei ?? -99));

  const teiValues = rosterPlayers.map((p) => p.tei).filter((t): t is number => t !== null);
  const maxTei = teiValues.length ? Math.max(...teiValues, 1) : 1;

  return (
    <div className="space-y-6" style={teamVars(detail.team.abbreviation)}>
      {/* ------------------------------------------------------ broadcast banner */}
      <section className="panel relative overflow-hidden">
        <div
          aria-hidden
          className="pointer-events-none absolute inset-0"
          style={{
            background: `linear-gradient(105deg, ${identity.primary}3d 0%, transparent 58%)`,
          }}
        />
        <HalfCourt className="pointer-events-none absolute -bottom-6 right-2 hidden h-[125%] w-[26%] text-signal/15 md:block" />

        <div className="relative flex flex-col gap-5 p-5 md:flex-row md:items-center md:gap-6 md:p-6">
          <div className="flex min-w-0 flex-1 items-center gap-4 md:gap-6">
            <TeamCrest
              abbreviation={detail.team.abbreviation}
              name={detail.team.full_name}
              size={76}
            />

            <div className="min-w-0">
              <div className="eyebrow flex flex-wrap items-center gap-x-2.5 gap-y-1">
                <span className="whitespace-nowrap" style={{ color: identity.bright }}>
                  {detail.team.abbreviation}
                </span>
                <span aria-hidden className="text-faint">
                  /
                </span>
                <span className="whitespace-nowrap">
                  {detail.team.conference ?? "—"}
                  {detail.team.division ? ` · ${detail.team.division}` : ""}
                </span>
                <span aria-hidden className="text-faint">
                  /
                </span>
                <span className="whitespace-nowrap">{detail.season}</span>
              </div>
              <h1 className="title-xl mt-2 text-foreground">{detail.team.full_name}</h1>
              <div className="mt-3 flex flex-wrap items-center gap-x-2.5 gap-y-1">
                <Badge status={competitiveWindow.status}>window: {competitiveWindow.label}</Badge>
                <span className="text-[12px] text-muted">{competitiveWindow.hint}</span>
              </div>
            </div>
          </div>

          {detail.standing ? (
            <div className="shrink-0 border-t border-hairline pt-4 md:border-l md:border-t-0 md:pl-6 md:pt-0">
              <div className="eyebrow text-[0.5625rem]">Record · {detail.season}</div>
              <div
                className="numeral mt-1 whitespace-nowrap text-[3.25rem] leading-none"
                style={{ color: identity.bright }}
              >
                {detail.standing.wins}–{detail.standing.losses}
              </div>
              <div className="mt-1 whitespace-nowrap text-[12px] text-muted">
                {pct(detail.standing.win_pct, 1)} · #{detail.standing.playoff_rank ?? "—"} in the{" "}
                {detail.standing.conference ?? "conference"}
              </div>
            </div>
          ) : (
            <div className="shrink-0 border-t border-hairline pt-4 md:border-l md:border-t-0 md:pl-6 md:pt-0">
              <div className="eyebrow text-[0.5625rem]">Record</div>
              <div className="numeral mt-1 text-[2.5rem] leading-none text-unavail">—</div>
              <div className="mt-1 text-[12px] text-muted">no standings row ingested</div>
            </div>
          )}
        </div>

        <div className="relative flex flex-wrap items-center gap-2 border-t border-hairline px-5 py-3 md:px-6">
          <ButtonLink href={`/trade-evaluator?team=${teamId}`} variant="primary" size="sm">
            Start a trade
          </ButtonLink>
          <ButtonLink href={`/player-explorer?team=${teamId}`} size="sm">
            Compare players
          </ButtonLink>
          <ButtonLink href={`/salary-cap-center?team=${teamId}`} size="sm">
            Salary-Cap Center
          </ButtonLink>
          <SourceRail
            className="ml-auto mt-0 w-full border-t-0 pt-0 lg:w-auto"
            source="NBA.com via nba_api"
            retrievedAt={detail.standing?.source_retrieved_at ?? detail.stats_retrieved_at}
          />
        </div>
      </section>

      {/* ------------------------------------------------------------- team line */}
      <section className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <TeamStat
          label="Offense"
          value={advanced.OFF_RATING}
          note="points scored per 100 possessions"
          accent="var(--signal)"
        />
        <TeamStat
          label="Defense"
          value={advanced.DEF_RATING}
          note="points allowed per 100 · lower is better"
          accent="var(--signal)"
        />
        <TeamStat
          label="Net rating"
          value={advanced.NET_RATING}
          note="scoring margin per 100 possessions"
          accent={
            (advanced.NET_RATING ?? 0) >= 0 ? "var(--legal)" : "var(--illegal)"
          }
          signed
        />
        <TeamStat
          label="Average age"
          value={avgAge ?? undefined}
          note={`${rosterPlayers.length} players on the roster`}
          accent={identity.bright}
        />
      </section>

      {/* ------------------------------------------------------- roster + panels */}
      <div className="grid items-start gap-3 lg:grid-cols-[minmax(0,1fr)_minmax(0,340px)] xl:grid-cols-[minmax(0,1fr)_minmax(0,380px)]">
        <Panel
          className="min-w-0"
          accent={identity.bright}
          title={`Roster · ${rosterPlayers.length}`}
          subtitle="Grouped by position, sorted by estimated impact within each group"
          actions={
            <Link href="/methodology#tei" className="eyebrow whitespace-nowrap text-signal">
              What is impact? →
            </Link>
          }
        >
          {!roster ? (
            <SkeletonRows rows={10} height="h-12" />
          ) : rosterPlayers.length === 0 ? (
            <EmptyState
              title="No roster rows for this team"
              hint="Run `make sync-data` on the backend to pull the current roster from NBA.com."
              action={<ButtonLink href="/data-health" size="sm">Open Data Health</ButtonLink>}
            />
          ) : (
            <div className="space-y-5">
              {GROUPS.filter((group) => groups[group].length > 0).map((group) => (
                <div key={group}>
                  <div className="flex items-baseline justify-between gap-3 border-b border-hairline pb-1.5">
                    <h3 className="eyebrow" style={{ color: identity.bright }}>
                      {group}
                    </h3>
                    <span className="eyebrow text-[0.5rem]">{groups[group].length}</span>
                  </div>
                  <ul className="divide-y divide-hairline">
                    {groups[group].map((player) => (
                      <li key={player.player_id}>
                        <Link
                          href={`/players/${player.player_id}`}
                          className="group flex items-center gap-3 rounded-md px-1 py-2 transition-colors hover:bg-panel2"
                        >
                          <PlayerPhoto
                            nbaPlayerId={player.nba_player_id}
                            name={player.name}
                            size={36}
                          />
                          <span className="min-w-0 flex-1">
                            <span className="block truncate text-sm text-foreground transition-colors group-hover:text-signal">
                              {player.name}
                            </span>
                            <span className="eyebrow mt-0.5 block truncate text-[0.5rem]">
                              {player.position ?? "—"} · age {player.age?.toFixed(0) ?? "—"} ·{" "}
                              {height(player.height_inches)}
                            </span>
                          </span>
                          {player.archetype && (
                            <span className="hidden shrink-0 whitespace-nowrap text-[11px] text-faint xl:inline">
                              {player.archetype}
                            </span>
                          )}
                          <span className="w-20 shrink-0 text-right">
                            <span
                              className="numeral block text-[19px] leading-none"
                              style={{
                                color:
                                  player.tei === null
                                    ? "var(--unknown)"
                                    : player.tei >= 0
                                      ? identity.bright
                                      : "var(--chalk-dim)",
                              }}
                              title="Estimated player impact (per-100 index) — see Methodology"
                            >
                              {tei(player.tei)}
                            </span>
                            {player.tei !== null && player.tei > 0 && (
                              <MeterBar
                                value={player.tei}
                                max={maxTei}
                                color={identity.bright}
                                className="ml-auto mt-1 !h-1 w-16"
                                label={`impact ${tei(player.tei)}, top rotation impact is ${tei(maxTei)}`}
                              />
                            )}
                          </span>
                        </Link>
                      </li>
                    ))}
                  </ul>
                </div>
              ))}
              <SourceRail
                source={roster.source}
                retrievedAt={roster.source_retrieved_at}
                extra={<span>· impact estimated by RosterLab, not a provider metric</span>}
              />
            </div>
          )}
        </Panel>

        <div className="space-y-3">
          {/* ------------------------------------------------ strengths & needs */}
          <Panel
            title="Strengths & needs"
            subtitle="Percentile rules over real league stats — no scouting opinions"
          >
            {!needs ? (
              <SkeletonRows rows={5} height="h-8" />
            ) : sortedNeeds.length === 0 ? (
              <UnavailableNotice reason="Team needs haven't been computed for this season yet — run `make score` on the backend." />
            ) : (
              <div className="space-y-4">
                {strengths.length > 0 && (
                  <div>
                    <h4 className="eyebrow text-legal">Strengths</h4>
                    <ul className="mt-2 space-y-2">
                      {strengths.map((need) => (
                        <li key={need.need_key} title={need.explanation}>
                          <div className="flex items-baseline justify-between gap-3 text-[13px]">
                            <span className="min-w-0 truncate text-foreground">
                              {NEED_LABEL[need.need_key] ?? need.need_key}
                            </span>
                            <span className="data shrink-0 text-[11px] text-muted">
                              {ordinal(need.percentile)}
                            </span>
                          </div>
                          <MeterBar
                            value={need.percentile ?? 0}
                            max={100}
                            color="var(--legal)"
                            className="mt-1"
                            label={`${NEED_LABEL[need.need_key] ?? need.need_key} at the ${ordinal(need.percentile)} percentile`}
                          />
                        </li>
                      ))}
                    </ul>
                  </div>
                )}

                <div>
                  <h4 className="eyebrow text-illegal">Needs</h4>
                  {/* The old fallback rendered the first four rows by severity order
                      regardless of severity, so Atlanta showed "Defensive rebounding
                      67th" under Strengths *and* under Needs, with a zero-length bar
                      beneath the caption "longer bar = larger shortfall". Deleting the
                      fallback outright would leave ATL and CLE with an empty <ul> under
                      a bare heading, so the empty case gets a real state. */}
                  {weaknesses.length === 0 ? (
                    <p className="mt-2 rounded-lg border border-hairline bg-panel2 px-3 py-2.5 text-[13px] leading-relaxed text-muted">
                      No pressing needs. Every measured category sits at or above the
                      league median for this team, so nothing here reads as a shortfall.
                    </p>
                  ) : (
                    <ul className="mt-2 space-y-2">
                      {weaknesses.map((need) => (
                        <li key={need.need_key} title={need.explanation}>
                          <div className="flex items-baseline justify-between gap-3 text-[13px]">
                            <span className="min-w-0 truncate text-foreground">
                              {NEED_LABEL[need.need_key] ?? need.need_key}
                            </span>
                            <span className="data shrink-0 text-[11px] text-muted">
                              {ordinal(need.percentile)}
                            </span>
                          </div>
                          <MeterBar
                            value={need.severity}
                            color={need.severity > 0.5 ? "var(--illegal)" : "var(--conditional)"}
                            className="mt-1"
                            label={`${NEED_LABEL[need.need_key] ?? need.need_key} severity ${(need.severity * 100).toFixed(0)} percent`}
                          />
                        </li>
                      ))}
                    </ul>
                  )}
                </div>

                <p className="text-[11px] leading-relaxed text-faint">
                  {weaknesses.length > 0 ? "Longer bar under Needs = larger shortfall. " : ""}
                  <Link href="/methodology#needs" className="text-signal underline">
                    How this is calculated
                  </Link>
                </p>
              </div>
            )}
          </Panel>

          {/* ------------------------------------------------------- strategy */}
          <Panel
            title="Team strategy"
            subtitle="Drives how every trade is scored for this franchise"
          >
            <fieldset className="space-y-1.5">
              <legend className="sr-only">Choose a strategy for {detail.team.full_name}</legend>
              {STRATEGIES.map(([value, label, hint]) => {
                const checked = strategy === value;
                return (
                  <label
                    key={value}
                    className={`flex cursor-pointer items-start gap-2.5 rounded-md border px-3 py-2 transition-colors ${
                      checked
                        ? "border-signal/50 bg-signal/8"
                        : "border-transparent hover:bg-panel2"
                    }`}
                  >
                    <input
                      type="radio"
                      name="strategy"
                      value={value}
                      checked={checked}
                      onChange={() => setStrategy(value)}
                      className="mt-0.5 h-3.5 w-3.5 shrink-0 accent-[var(--signal)]"
                    />
                    <span className="min-w-0">
                      <span
                        className={`block whitespace-nowrap text-[13px] font-semibold ${
                          checked ? "text-signal" : "text-foreground"
                        }`}
                      >
                        {label}
                      </span>
                      <span className="block text-[11px] leading-snug text-muted">{hint}</span>
                    </span>
                  </label>
                );
              })}
            </fieldset>
            <Button
              variant="primary"
              className="mt-3 w-full"
              disabled={saveStrategy.isPending}
              onClick={() => saveStrategy.mutate()}
            >
              {saveStrategy.isPending ? "Saving…" : "Save strategy"}
            </Button>
            <p className="mt-2 text-[11px] leading-relaxed text-faint">
              Fine-grained weights and untouchable players live in the Trade Evaluator.{" "}
              <Link href="/methodology#weights" className="text-signal underline">
                How weights work
              </Link>
            </p>
          </Panel>

        </div>
      </div>

      {/* --------------------------------------------------- money & assets */}
      <div className="grid items-start gap-3 lg:grid-cols-2">
        {/* ---------------------------------------------------------- payroll */}
        <Panel title="Payroll & cap status" className="min-w-0">
            {!payroll ? (
              <SkeletonRows rows={3} height="h-8" />
            ) : payroll.payroll_available ? (
              <div className="space-y-3">
                <StatBlock
                  label={`Committed payroll · ${payroll.league_year}`}
                  value={money(payroll.payroll)}
                  note={`${payroll.players_with_salary} of ${payroll.roster_size} players with a salary on file`}
                  accent="var(--leather)"
                />
                {payroll.cap_context && (
                  <dl className="space-y-1.5 border-t border-hairline pt-3">
                    <MoneyRow label="Luxury-tax line" value={money(payroll.cap_context.luxury_tax)} />
                    <MoneyRow label="Room below tax" value={money(payroll.cap_context.room_below_tax)} />
                    <MoneyRow label="First apron" value={money(payroll.cap_context.first_apron)} />
                  </dl>
                )}
                <ButtonLink href={`/salary-cap-center?team=${teamId}`} size="sm" className="w-full">
                  Full picture in Salary-Cap Center
                </ButtonLink>
                {payroll.cap_context && (
                  <SourceRail source={payroll.cap_context.cap_source} retrievedAt={undefined} />
                )}
              </div>
            ) : (
              <UnavailableNotice
                reason={
                  payroll.unavailable_reason ??
                  "Contract data hasn't been imported, so payroll can't be computed."
                }
                steps={
                  <p className="text-[12px] leading-relaxed text-muted">
                    Salary-matching rules will keep reporting <em>unavailable</em> until a contract
                    provider is configured.{" "}
                    <Link href="/data-health" className="text-signal underline">
                      See the exact next step
                    </Link>
                  </p>
                }
              />
            )}
          </Panel>

        {/* ---------------------------------------------------- draft capital */}
        <Panel title="Draft capital" className="min-w-0">
          <UnavailableNotice reason="Verified draft-pick ownership isn't configured, and RosterLab won't guess it. Hypothetical picks can still be added inside a trade, clearly labeled as hypothetical." />
        </Panel>
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ pieces */

function TeamStat({
  label,
  value,
  note,
  accent,
  signed = false,
}: {
  label: string;
  value: number | undefined | null;
  note: string;
  accent: string;
  signed?: boolean;
}) {
  const shown =
    value === undefined || value === null
      ? "—"
      : signed
        ? `${value >= 0 ? "+" : ""}${Number(value).toFixed(1)}`
        : Number(value).toFixed(1);
  return (
    <Panel padded={false} className="px-4 py-3.5">
      <StatBlock
        label={label}
        value={shown}
        note={note}
        accent={value === undefined || value === null ? "var(--unknown)" : accent}
      />
    </Panel>
  );
}

function MoneyRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-baseline justify-between gap-3">
      <dt className="text-[13px] text-muted">{label}</dt>
      <dd className="data shrink-0 text-[13px] text-foreground">{value}</dd>
    </div>
  );
}

function TeamSkeleton() {
  return (
    <div className="space-y-6" role="status" aria-label="Loading team">
      <div className="panel flex flex-wrap items-center gap-6 p-6">
        <Skeleton className="h-20 w-20 rounded-full" />
        <div className="min-w-0 flex-1 space-y-3">
          <Skeleton className="h-4 w-40" />
          <Skeleton className="h-10 w-80 max-w-full" />
          <Skeleton className="h-6 w-64" />
        </div>
        <Skeleton className="h-16 w-40" />
      </div>
      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        {Array.from({ length: 4 }).map((_, i) => (
          <Skeleton key={i} className="h-24" />
        ))}
      </div>
      <div className="grid gap-3 lg:grid-cols-[minmax(0,1fr)_minmax(0,340px)]">
        <Skeleton className="h-[520px]" />
        <div className="space-y-3">
          <Skeleton className="h-56" />
          <Skeleton className="h-64" />
          <Skeleton className="h-40" />
        </div>
      </div>
    </div>
  );
}
