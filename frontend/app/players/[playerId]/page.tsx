"use client";

/**
 * Player detail — the scouting page.
 *
 * Banner first (who this is), then the impact estimate with its uncertainty band
 * shown as a band rather than a point, then the season line, comparables and the
 * contract panel, which stays honestly empty until contracts are imported.
 */

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { use, useState } from "react";
import { api } from "@/lib/api";
import { count, height, money, ordinal, pct, tei } from "@/lib/format";
import { playerIntelligenceSchema } from "@/lib/schemas";
import { teamIdentity, teamVars } from "@/lib/teamIdentity";
import type {
  Provenance,
  ArchetypeAssignment,
  ComparablePlayer,
  Measurement,
  PlayerIntelligence,
  SkillEntry,
  Team,
} from "@/lib/types";
import { TeamLogo, PlayerPhoto } from "@/components/media";
import {
  Badge,
  ButtonLink,
  ErrorState,
  Panel,
  Skeleton,
  SkeletonRows,
  SourceRail,
  StatBlock,
  Td,
  Th,
  UnavailableNotice,
} from "@/components/ui";

interface PlayerDetail {
  player: {
    id: string;
    nba_player_id: number;
    full_name: string;
    is_active: boolean;
    position: string | null;
    birth_date: string | null;
    height_inches: number | null;
    weight_lbs: number | null;
    years_experience: number | null;
    current_team: Team | null;
    provenance: Provenance | null;
  };
  impact: {
    tei?: number;
    tei_offense?: number | null;
    tei_defense?: number | null;
    tei_range_10_90?: [number, number] | null;
    availability?: number | null;
    minutes_estimate?: number | null;
    model?: string | null;
    note: string;
  };
  archetype: ArchetypeAssignment | null;
  comparables: ComparablePlayer[];
}

interface PlayerStats {
  seasons: {
    season: string;
    source_retrieved_at: string | null;
    base?: Record<string, number>;
    advanced?: Record<string, number>;
  }[];
  source: string;
}

interface PlayerContract {
  available: boolean;
  reason?: string;
  contract_type?: string;
  source_name?: string;
  source_date?: string;
  no_trade_clause?: boolean | null;
  years?: {
    season: string;
    salary: number;
    player_option: boolean | null;
    team_option: boolean | null;
  }[];
  note?: string;
}

export default function PlayerPage({ params }: { params: Promise<{ playerId: string }> }) {
  const { playerId } = use(params);
  const { data, error } = useQuery({
    queryKey: ["player", playerId],
    queryFn: () => api.get<PlayerDetail>(`/players/${playerId}`),
  });
  const { data: stats, error: statsError } = useQuery({
    queryKey: ["player-stats", playerId],
    queryFn: () => api.get<PlayerStats>(`/players/${playerId}/stats`),
  });
  const { data: contract, error: contractError } = useQuery({
    queryKey: ["player-contract", playerId],
    queryFn: () => api.get<PlayerContract>(`/players/${playerId}/contract`),
  });
  const [now] = useState(() => Date.now());

  if (error) return <ErrorState message={`Could not load player: ${String(error)}`} />;
  if (!data) return <PlayerSkeleton />;

  const player = data.player;
  const team = player.current_team;
  const identity = teamIdentity(team?.abbreviation);
  const age = player.birth_date
    ? Math.floor((now - new Date(player.birth_date).getTime()) / (365.25 * 24 * 3600 * 1000))
    : null;
  const impact = data.impact;
  const range = impact.tei_range_10_90 ?? null;

  return (
    <div className="space-y-6" style={teamVars(team?.abbreviation)}>
      {/* ------------------------------------------------------------- banner */}
      <section
        className="panel relative overflow-hidden"
        style={{ "--edge": identity.bright } as React.CSSProperties}
      >
        <div
          aria-hidden
          className="pointer-events-none absolute inset-0"
          style={{
            background: `radial-gradient(560px 260px at 92% 0%, ${identity.primary}30, transparent 70%)`,
          }}
        />
        <div className="relative flex flex-col gap-5 p-5 md:flex-row md:items-center md:gap-7 md:p-6">
          <div className="flex min-w-0 flex-1 items-center gap-4 md:gap-5">
            <PlayerPhoto
              nbaPlayerId={player.nba_player_id}
              name={player.full_name}
              size={104}
              square
              className="border border-hairline"
            />

            <div className="min-w-0">
              <div className="eyebrow flex flex-wrap items-center gap-x-2.5 gap-y-1">
                <span className="whitespace-nowrap">Player file</span>
                {player.position && (
                  <>
                    <span aria-hidden className="text-faint">
                      /
                    </span>
                    <span className="whitespace-nowrap">{player.position}</span>
                  </>
                )}
                {data.archetype && (
                  <>
                    <span aria-hidden className="text-faint">
                      /
                    </span>
                    <span className="whitespace-nowrap text-signal">{data.archetype.label}</span>
                  </>
                )}
              </div>

              <h1 className="title-xl mt-2 text-foreground">{player.full_name}</h1>

              <div className="mt-3 flex flex-wrap items-center gap-2">
                {team ? (
                  <Link
                    href={`/team-outlook/${team.id}`}
                    className="inline-flex items-center gap-2 whitespace-nowrap rounded-full border px-2.5 py-1 text-[13px] transition-colors hover:bg-panel2"
                    style={{ borderColor: `${identity.bright}55` }}
                  >
                    <TeamLogo abbreviation={team.abbreviation} size={18} decorative />
                    <span className="text-foreground">{team.full_name}</span>
                  </Link>
                ) : (
                  <Badge status="unavailable">no current team on file</Badge>
                )}
                {!player.is_active && <Badge status="unavailable">not active</Badge>}
              </div>
            </div>
          </div>

          <div className="shrink-0 border-t border-hairline pt-4 md:border-l md:border-t-0 md:pl-7 md:pt-0">
            <dl className="grid grid-cols-3 gap-x-6 gap-y-3.5 sm:grid-cols-5">
              <BioFact label="Age" value={age !== null ? String(age) : "—"} />
              <BioFact label="Height" value={height(player.height_inches)} />
              <BioFact label="Weight" value={player.weight_lbs ? `${player.weight_lbs} lb` : "—"} />
              <BioFact
                label="Experience"
                value={player.years_experience !== null ? `${player.years_experience} yr` : "—"}
              />
              <BioFact label="Position" value={player.position ?? "—"} />
            </dl>
            {team && (
              <div className="mt-4 flex flex-wrap gap-2 border-t border-hairline pt-4">
                <ButtonLink href={`/trade-evaluator?team=${team.id}`} variant="primary" size="sm">
                  Trade this roster
                </ButtonLink>
                <ButtonLink href={`/player-explorer?team=${team.id}`} size="sm">
                  Compare teammates
                </ButtonLink>
              </div>
            )}
          </div>
        </div>
        <div className="relative border-t border-hairline px-5 pb-3 pt-2.5 md:px-6">
          <SourceRail
            className="mt-0 border-t-0 pt-0"
            source={player.provenance?.upstream ?? "unknown source"}
            retrievedAt={player.provenance?.source_retrieved_at}
          />
        </div>
      </section>

      {/* -------------------------------------------- analysis: two flowing columns */}
      <section className="grid items-start gap-3 lg:grid-cols-[minmax(0,1.55fr)_minmax(0,1fr)]">
        <div className="min-w-0 space-y-3">
          <Panel
            className="min-w-0"
            title="Estimated impact"
            subtitle={impact.model ? `Model: ${impact.model}` : undefined}
            actions={
              <Link href="/methodology#tei" className="eyebrow whitespace-nowrap text-signal">
                How it&apos;s built →
              </Link>
            }
            accent="var(--signal)"
          >
            {impact.tei === undefined ? (
              <UnavailableNotice reason={impact.note} />
            ) : (
              <div className="space-y-4">
                <div className="flex flex-wrap items-end gap-x-8 gap-y-4">
                  <div>
                    <div className="eyebrow text-[0.625rem]">Impact index</div>
                    <div className="numeral mt-1 text-[3.25rem] leading-none text-signal">
                      {tei(impact.tei)}
                    </div>
                    <div className="mt-1 text-[11px] text-muted">
                      scoring margin per 100 possessions
                    </div>
                  </div>
                  {range && <ImpactRange low={range[0]} high={range[1]} median={impact.tei} />}
                </div>

                <div className="grid grid-cols-2 gap-x-6 gap-y-4 border-t border-hairline pt-4 sm:grid-cols-4">
                  <StatBlock label="Offense" value={tei(impact.tei_offense)} size="sm" />
                  <StatBlock label="Defense" value={tei(impact.tei_defense)} size="sm" />
                  <StatBlock
                    label="Availability"
                    value={pct(impact.availability)}
                    note="historical games played"
                    size="sm"
                  />
                  <StatBlock
                    label="Minutes est."
                    value={impact.minutes_estimate?.toFixed(1) ?? "—"}
                    note="per game, model estimate"
                    size="sm"
                  />
                </div>

                <p className="text-[11px] leading-relaxed text-faint">{impact.note}</p>
              </div>
            )}
          </Panel>

          <Panel
            className="min-w-0"
            title="Season by season"
            subtitle="Per-game averages from the league dashboard, with advanced rates"
          >
            {statsError ? (
              <ErrorState message={`Could not load season stats: ${String(statsError)}`} />
            ) : !stats ? (
              <SkeletonRows rows={3} height="h-9" />
            ) : stats.seasons.length === 0 ? (
              <UnavailableNotice reason="No season rows have been ingested for this player." />
            ) : (
              <>
                <div className="scroll-thin overflow-x-auto">
                  <table className="w-full min-w-[680px]">
                    <thead>
                      <tr className="border-b border-line">
                        <Th>Season</Th>
                        <Th numeric>GP</Th>
                        <Th numeric>MIN</Th>
                        <Th numeric>PTS</Th>
                        <Th numeric>REB</Th>
                        <Th numeric>AST</Th>
                        <Th numeric>TS%</Th>
                        <Th numeric>USG%</Th>
                        <Th numeric>Net rtg</Th>
                      </tr>
                    </thead>
                    <tbody>
                      {stats.seasons.map((season) => (
                        <tr key={season.season} className="border-b border-hairline">
                          <Td className="numeral whitespace-nowrap text-[15px]">{season.season}</Td>
                          <Td numeric>{season.base?.GP ?? "—"}</Td>
                          <Td numeric>{season.base?.MIN?.toFixed(1) ?? "—"}</Td>
                          <Td numeric className="text-foreground">
                            {season.base?.PTS?.toFixed(1) ?? "—"}
                          </Td>
                          <Td numeric>{season.base?.REB?.toFixed(1) ?? "—"}</Td>
                          <Td numeric>{season.base?.AST?.toFixed(1) ?? "—"}</Td>
                          <Td numeric>
                            {season.advanced?.TS_PCT !== undefined
                              ? pct(season.advanced.TS_PCT, 1)
                              : "—"}
                          </Td>
                          <Td numeric>
                            {season.advanced?.USG_PCT !== undefined
                              ? pct(season.advanced.USG_PCT, 1)
                              : "—"}
                          </Td>
                          <Td numeric>{season.advanced?.NET_RATING?.toFixed(1) ?? "—"}</Td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                <SourceRail
                  source={stats.source}
                  retrievedAt={stats.seasons[0]?.source_retrieved_at ?? null}
                />
              </>
            )}
          </Panel>
        </div>

        <div className="min-w-0 space-y-3">
          <Panel title="Role" accent="var(--signal)">
            {data.archetype ? (
              <div>
                <div className="display text-xl leading-tight text-balance text-foreground">
                  {data.archetype.label}
                </div>
                <p className="mt-1.5 text-[12px] leading-relaxed text-muted">
                  Assigned by a fixed rule chain over league percentiles — size first, then role
                  within that size. A role label, not a quality rating, and the same profile always
                  produces the same label.
                </p>
              </div>
            ) : (
              <UnavailableNotice reason="No role has been assigned to this player yet." />
            )}
          </Panel>

          <Panel
            title="Comparable players"
            subtitle="Same role, nearest impact estimate"
          >
            {data.comparables.length === 0 ? (
              <UnavailableNotice reason="Comparables need a role, which hasn't been assigned to this player." />
            ) : (
              <ul className="divide-y divide-hairline">
                {data.comparables.map((comparable) => (
                  <li key={comparable.player_id}>
                    <Link
                      href={`/players/${comparable.player_id}`}
                      className="flex items-center gap-3 py-2 transition-colors hover:text-signal"
                    >
                      <span className="min-w-0 flex-1 truncate text-sm">{comparable.name}</span>
                      <span className="data shrink-0 text-sm text-muted">
                        {tei(comparable.tei)}
                      </span>
                    </Link>
                  </li>
                ))}
              </ul>
            )}
          </Panel>

          <Panel title="Contract" className="min-w-0">
            {contractError ? (
              <ErrorState message={`Could not load the contract: ${String(contractError)}`} />
            ) : !contract ? (
              <SkeletonRows rows={3} height="h-8" />
            ) : contract.available ? (
              <div className="space-y-3">
                <div className="flex flex-wrap items-center gap-2">
                  {contract.contract_type && <Badge status="info">{contract.contract_type}</Badge>}
                  {contract.no_trade_clause && <Badge status="warning">no-trade clause</Badge>}
                </div>
                <table className="w-full">
                  <thead>
                    <tr className="border-b border-line">
                      <Th>Season</Th>
                      <Th numeric>Salary</Th>
                      <Th>Option</Th>
                    </tr>
                  </thead>
                  <tbody>
                    {contract.years?.map((year) => (
                      <tr key={year.season} className="border-b border-hairline">
                        <Td className="numeral whitespace-nowrap text-[15px]">{year.season}</Td>
                        <Td numeric>{money(year.salary)}</Td>
                        <Td className="text-xs text-muted">
                          {year.player_option ? "player" : year.team_option ? "team" : "—"}
                        </Td>
                      </tr>
                    ))}
                  </tbody>
                </table>
                {contract.note && (
                  <p className="text-[11px] leading-relaxed text-faint">{contract.note}</p>
                )}
                <SourceRail
                  source={contract.source_name ?? "user-imported contract snapshot"}
                  retrievedAt={contract.source_date ?? null}
                />
              </div>
            ) : (
              <UnavailableNotice
                reason={contract.reason ?? "Contract data has not been imported."}
                steps={
                  <p className="text-[12px] leading-relaxed text-muted">
                    Until a contract provider is configured, salary-matching rules report{" "}
                    <em>unavailable</em> everywhere — see{" "}
                    <Link href="/data-health" className="text-signal underline">
                      Data Health
                    </Link>{" "}
                    for the exact next step.
                  </p>
                }
              />
            )}
          </Panel>
        </div>
      </section>

      {/* -------------------------------------------------- player intelligence */}
      <PlayerIntelligencePanel playerId={playerId} />
    </div>
  );
}

/* ------------------------------------------------------------------ pieces */

function BioFact({ label, value }: { label: string; value: string }) {
  return (
    <div className="min-w-0">
      <dt className="eyebrow text-[0.5625rem]">{label}</dt>
      <dd className="numeral mt-1 whitespace-nowrap text-lg leading-none text-foreground">
        {value}
      </dd>
    </div>
  );
}

/** The 10th–90th percentile band, drawn so the range reads before the midpoint. */
function ImpactRange({ low, high, median }: { low: number; high: number; median: number }) {
  const min = Math.min(low, -1);
  const max = Math.max(high, 1);
  const span = max - min || 1;
  const toPct = (value: number) => ((value - min) / span) * 100;

  return (
    <div className="min-w-[240px] flex-1">
      <div className="eyebrow text-[0.625rem]">Uncertainty · 10th–90th percentile</div>
      <div className="relative mt-2 h-7 overflow-hidden rounded-md border border-hairline bg-panel3">
        <div
          aria-hidden
          className="absolute inset-y-0 w-px bg-faint/70"
          style={{ left: `${toPct(0)}%` }}
        />
        <div
          aria-hidden
          className="absolute inset-y-1.5 rounded-sm"
          style={{
            left: `${toPct(low)}%`,
            width: `${Math.max(1, toPct(high) - toPct(low))}%`,
            background: "linear-gradient(90deg, rgb(34 211 238 / 0.25), rgb(34 211 238 / 0.55))",
          }}
        />
        <div
          aria-hidden
          className="absolute inset-y-0 w-0.5 bg-signal"
          style={{ left: `${toPct(median)}%` }}
        />
      </div>
      <div className="mt-1 flex items-baseline justify-between gap-3 text-[11px] text-muted">
        <span className="data shrink-0">{tei(low)}</span>
        <span className="hidden min-w-0 text-center sm:block">
          a wide band means the box score can&apos;t pin this player down
        </span>
        <span className="data shrink-0">{tei(high)}</span>
      </div>
      <p className="mt-1 text-[11px] leading-snug text-faint sm:hidden">
        A wide band means the box score can&apos;t pin this player down.
      </p>
    </div>
  );
}

function PlayerSkeleton() {
  return (
    <div className="space-y-6" role="status" aria-label="Loading player">
      <div className="panel flex flex-wrap items-start gap-5 p-5">
        <Skeleton className="h-28 w-28 rounded-lg" />
        <div className="min-w-0 flex-1 space-y-3">
          <Skeleton className="h-4 w-32" />
          <Skeleton className="h-10 w-72 max-w-full" />
          <Skeleton className="h-7 w-52" />
          <Skeleton className="h-12 w-full max-w-md" />
        </div>
      </div>
      <div className="grid gap-3 lg:grid-cols-[minmax(0,1.55fr)_minmax(0,1fr)]">
        <Skeleton className="h-64" />
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-1">
          <Skeleton className="h-28" />
          <Skeleton className="h-32" />
        </div>
      </div>
      <div className="grid gap-3 lg:grid-cols-[minmax(0,1.55fr)_minmax(0,1fr)]">
        <Skeleton className="h-52" />
        <Skeleton className="h-40" />
      </div>
    </div>
  );
}

/* ----------------------------------------------------------- intelligence */

/** Declared order of the sides, so the reader meets them the same way every time. */
const SKILL_SIDES = [
  ["offense", "Offense"],
  ["defense", "Defense"],
  ["physical", "Physical"],
] as const;

/** A dimension that carries a number. Narrowed, never defaulted — there is no `?? 0` here. */
type MeasuredSkill = SkillEntry & { percentile: number };

/**
 * Player intelligence — what Pivot measures about this player, and what it does not.
 *
 * The unmeasured dimensions are not an appendix and are not collapsed: a reader who saw
 * only the bars would conclude Pivot has seen everything, so each declared-but-unavailable
 * dimension is listed at full size with the reason it is unavailable. The gap belongs to
 * Pivot, not to the player.
 *
 * Nothing basketball is decided in here. The percentiles, the counts, the archetype and
 * the coverage sentence all arrive decided; this component groups, formats and orders.
 */
function PlayerIntelligencePanel({ playerId }: { playerId: string }) {
  const { data, error } = useQuery({
    queryKey: ["player-intelligence", playerId],
    queryFn: () =>
      api.get<PlayerIntelligence>(`/intelligence/players/${playerId}`, playerIntelligenceSchema),
  });

  const measured =
    data?.skills.filter((s): s is MeasuredSkill => s.available && s.percentile !== null) ?? [];
  const unmeasured = data?.skills.filter((s) => !s.available) ?? [];

  return (
    <Panel
      title="Player intelligence"
      subtitle="The measured dimensions, the dimensions Pivot cannot see, and the role it infers"
      accent="var(--signal)"
      actions={
        <Link href="/methodology" className="eyebrow whitespace-nowrap text-signal">
          What Pivot measures →
        </Link>
      }
    >
      {error ? (
        <ErrorState message={`Could not load player intelligence: ${String(error)}`} />
      ) : !data ? (
        <SkeletonRows rows={6} height="h-9" />
      ) : (
        <div className="space-y-5">
          {/* --------------------------------------------------------- coverage */}
          <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
            <span className="numeral text-2xl leading-none text-signal">
              {data.skills_measured}
              <span className="text-muted"> / {data.skills_declared}</span>
            </span>
            <span className="eyebrow text-[0.625rem]">declared dimensions measured</span>
            <span className="data text-[11px] text-muted">{data.season}</span>
          </div>
          <p className="text-[12px] leading-relaxed text-muted">{data.coverage_note}</p>

          <div className="grid gap-5 border-t border-hairline pt-4 lg:grid-cols-[minmax(0,1.35fr)_minmax(0,1fr)]">
            {/* ------------------------------------------------------- measured */}
            <div className="min-w-0 space-y-4">
              <h3 className="eyebrow">Measured dimensions</h3>
              {measured.length === 0 ? (
                <UnavailableNotice reason="None of the declared dimensions could be measured for this player." />
              ) : (
                <>
                  {SKILL_SIDES.map(([side, label]) => {
                    const rows = measured.filter((skill) => skill.side === side);
                    if (rows.length === 0) return null;
                    return (
                      <div key={side}>
                        <h4 className="eyebrow text-[0.5625rem] text-faint">{label}</h4>
                        <ul className="mt-2 space-y-2.5">
                          {rows.map((skill) => (
                            <li key={skill.key} className="min-w-0" title={methodTitle(skill)}>
                              <div className="flex items-baseline justify-between gap-3 text-[13px]">
                                <span className="min-w-0 truncate text-foreground">
                                  {skill.label}
                                </span>
                                <span className="data shrink-0 text-[11px] text-muted">
                                  {ordinal(skill.percentile * 100)} percentile
                                </span>
                              </div>
                              <div
                                role="img"
                                aria-label={`${skill.label} at the ${ordinal(
                                  skill.percentile * 100,
                                )} league percentile`}
                                className="mt-1 h-1.5 w-full overflow-hidden rounded-full bg-panel2"
                              >
                                <div
                                  className="h-full rounded-full"
                                  style={{
                                    width: `${skill.percentile * 100}%`,
                                    background: "var(--signal)",
                                  }}
                                />
                              </div>
                            </li>
                          ))}
                        </ul>
                      </div>
                    );
                  })}
                  {/* A number is never shown without its method being reachable. The row
                      title carries it on hover; this carries it to a keyboard as well. */}
                  <details className="group">
                    <summary className="eyebrow cursor-pointer list-none text-muted transition-colors hover:text-foreground">
                      <span
                        aria-hidden
                        className="mr-1.5 inline-block transition-transform group-open:rotate-90"
                      >
                        ›
                      </span>
                      How each measured dimension is computed
                    </summary>
                    <ul className="mt-2.5 space-y-3">
                      {measured.map((skill) => (
                        <li key={skill.key} className="text-[12px] leading-relaxed">
                          <span className="text-foreground">{skill.label}</span>
                          <span className="text-faint">
                            {" "}
                            · {skill.evidence} · {skill.confidence}
                          </span>
                          {skill.definition && <p className="text-muted">{skill.definition}</p>}
                          <p className="text-muted">{skill.method}</p>
                          <Limitations limitations={skill.limitations} />
                        </li>
                      ))}
                    </ul>
                  </details>
                  <SourceRail source={measured[0].source} />
                </>
              )}
            </div>

            <div className="min-w-0 space-y-5">
              {/* ----------------------------------------------------- impact */}
              <div>
                <h3 className="eyebrow">Impact</h3>
                {data.impact.available && data.impact.value !== null ? (
                  <div className="mt-2 space-y-2.5">
                    <StatBlock
                      label="Impact index (TEI)"
                      value={tei(data.impact.value)}
                      note="scoring margin per 100 possessions"
                      accent="var(--signal)"
                      title={methodTitle(data.impact)}
                    />
                    <div className="flex flex-wrap gap-2">
                      <Badge status="derived">{data.impact.evidence}</Badge>
                      <Badge status="info">{data.impact.confidence}</Badge>
                    </div>
                    <details className="group">
                      <summary className="eyebrow cursor-pointer list-none text-muted transition-colors hover:text-foreground">
                        <span
                          aria-hidden
                          className="mr-1.5 inline-block transition-transform group-open:rotate-90"
                        >
                          ›
                        </span>
                        Method and limitations
                      </summary>
                      <div className="mt-2 space-y-1 text-[12px] leading-relaxed">
                        <p className="text-muted">{data.impact.method}</p>
                        <p className="text-faint">Source: {data.impact.source}</p>
                        <Limitations limitations={data.impact.limitations} />
                      </div>
                    </details>
                  </div>
                ) : (
                  <div className="mt-2">
                    <UnavailableNotice reason={data.impact.reason} />
                  </div>
                )}
              </div>

              {/* -------------------------------------------------- archetypes */}
              <div>
                <h3 className="eyebrow">Archetype</h3>
                {data.archetypes.length === 0 ? (
                  <p className="mt-2 rounded-lg border border-hairline bg-panel2 px-3 py-2.5 text-[13px] leading-relaxed text-muted">
                    No archetype has been assigned to this player for {data.season}.
                  </p>
                ) : (
                  <ul className="mt-2 space-y-2.5">
                    {data.archetypes.map((archetype) => (
                      <li
                        key={archetype.key}
                        className="rounded-lg border border-hairline bg-panel2 px-3 py-2.5"
                      >
                        <div className="flex flex-wrap items-center gap-2">
                          <span className="text-sm text-foreground">{archetype.label}</span>
                          {archetype.primary && <Badge status="info">primary</Badge>}
                          <Badge status="derived">
                            {archetype.evidence} · {archetype.confidence}
                          </Badge>
                        </div>
                        {archetype.definition && (
                          <p className="mt-1.5 text-[12px] leading-relaxed text-muted">
                            {archetype.definition}
                          </p>
                        )}
                        <p className="mt-1.5 text-[11px] leading-relaxed text-faint">
                          An inference drawn from the measured dimensions, not something
                          observed. {archetype.method}
                        </p>
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            </div>
          </div>

          {/* ------------------------------------------------------ unmeasured */}
          {unmeasured.length > 0 && (
            <div className="border-t border-hairline pt-4">
              <h3 className="eyebrow text-unavail">
                Declared, not measured · {count(unmeasured.length, "dimension")}
              </h3>
              <p className="mt-1.5 text-[12px] leading-relaxed text-muted">
                Pivot declares these dimensions and cannot see them in the data it ingests.
                They are listed rather than dropped, because a missing dimension is a limit
                of the model and not a statement that the dimension does not matter.
              </p>
              <ul className="mt-3 grid gap-x-6 gap-y-3 sm:grid-cols-2">
                {unmeasured.map((skill) => (
                  <li key={skill.key} className="min-w-0">
                    <div className="flex items-baseline gap-2">
                      <span aria-hidden className="font-mono text-[11px] text-unavail">
                        —
                      </span>
                      <span className="text-[13px] text-foreground">{skill.label}</span>
                      <span className="eyebrow text-[0.5rem] text-faint">{skill.side}</span>
                    </div>
                    <p className="mt-0.5 pl-5 text-[12px] leading-relaxed text-muted">
                      {skill.reason}
                    </p>
                    {skill.definition && (
                      <p className="mt-0.5 pl-5 text-[11px] leading-relaxed text-faint">
                        {skill.definition}
                      </p>
                    )}
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}
    </Panel>
  );
}

function Limitations({ limitations }: { limitations: string[] }) {
  if (!limitations || limitations.length === 0) return null;
  return (
    <ul className="mt-0.5 space-y-0.5 pl-4 text-[11px] leading-relaxed text-faint">
      {limitations.map((limitation) => (
        <li key={limitation} className="list-disc">
          {limitation}
        </li>
      ))}
    </ul>
  );
}

/** The hover-reachable half of the method rule; the disclosures carry the rest. */
function methodTitle(m: Measurement): string {
  const parts = [m.method];
  if (m.limitations?.length) parts.push(`Limitations: ${m.limitations.join(" ")}`);
  return parts.filter(Boolean).join(" — ");
}
