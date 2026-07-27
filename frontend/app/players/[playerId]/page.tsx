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
import { height, money, pct, tei } from "@/lib/format";
import { teamIdentity, teamVars } from "@/lib/teamIdentity";
import type { Team } from "@/lib/types";
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
    provenance: { source_retrieved_at: string | null } | null;
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
  archetype: { label: string; cluster_id: number } | null;
  comparables: {
    player_id: string;
    name: string;
    tei: number;
    archetype: string;
  }[];
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
  const { data: stats } = useQuery({
    queryKey: ["player-stats", playerId],
    queryFn: () => api.get<PlayerStats>(`/players/${playerId}/stats`),
  });
  const { data: contract } = useQuery({
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
            source="NBA.com via nba_api"
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
            {!stats ? (
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
          <Panel title="Archetype" accent="var(--signal)">
            {data.archetype ? (
              <div>
                <div className="display text-xl leading-tight text-foreground">
                  {data.archetype.label}
                </div>
                <p className="mt-1.5 text-[12px] leading-relaxed text-muted">
                  Assigned by clustering box-score profiles across the league — a role label, not a
                  quality rating.
                </p>
              </div>
            ) : (
              <UnavailableNotice reason="No archetype cluster has been assigned to this player yet." />
            )}
          </Panel>

          <Panel
            title="Comparable players"
            subtitle="Same archetype cluster, nearest impact estimate"
          >
            {data.comparables.length === 0 ? (
              <UnavailableNotice reason="Comparables need an archetype cluster, which hasn't been assigned to this player." />
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
            {!contract ? (
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
