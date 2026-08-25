"use client";

/**
 * Salary-Cap Center — the multi-season payroll picture for one franchise.
 *
 * DATA HONESTY: contract data is opt-in and manually imported, so the endpoint
 * usually answers available=false. That is the DEFAULT state of this module and
 * it is designed as a deliberate import guide — never a broken-looking page, and
 * never a placeholder number. When contracts exist we render exactly what the
 * backend provides (payroll by season, per-contract rows, league cap
 * parameters) and never derive cap space or apron position on the client.
 */

import { useQuery } from "@tanstack/react-query";
import { useSearchParams } from "next/navigation";
import { Suspense, useMemo, useState } from "react";
import { api } from "@/lib/api";
import { dataHealthSchema } from "@/lib/schemas";
import { formatDate, money } from "@/lib/format";
import { teamIdentity } from "@/lib/teamIdentity";
import type {
  CapOutlookAvailable,
  CapOutlookResponse,
  DataHealth,
  RosterResponse,
  Team,
} from "@/lib/types";
import { SalaryTimeline } from "@/components/charts";
import { PlayerPhoto, TeamCrest, TeamLogo } from "@/components/media";
import {
  Badge,
  ButtonLink,
  EmptyState,
  ErrorState,
  PageHeader,
  Panel,
  Skeleton,
  SkeletonRows,
  SourceRail,
  StatBlock,
  Td,
  Th,
  UnavailableNotice,
} from "@/components/ui";

const IMPORT_STEPS: { title: string; body: React.ReactNode; code?: string }[] = [
  {
    title: "Save the contracts page",
    body: (
      <>
        Download the Basketball-Reference player-contracts page and save the HTML snapshot into the
        repository at
      </>
    ),
    code: "data/imports/contracts/players.html",
  },
  {
    title: "Point the app at the snapshot",
    body: <>Set the contract provider in your environment file (.env)</>,
    code: "CONTRACT_DATA_PROVIDER=bbref_snapshot",
  },
  {
    title: "Run the sync",
    body: <>Parse and load the contracts alongside the rest of the data</>,
    code: "make sync-data",
  },
];

const UNLOCKS = [
  {
    title: "Salary matching in the rules check",
    body: "Deals move from “Incomplete check” to a verified legal or illegal verdict.",
  },
  {
    title: "Payroll by season",
    body: "Committed money per league year, expiring contracts and option years.",
  },
  {
    title: "Contract value as a scored component",
    body: "Salary paid vs estimated on-court value enters every deal evaluation.",
  },
];

export default function SalaryCapCenterPage() {
  return (
    <Suspense
      fallback={
        <div className="space-y-4">
          <Skeleton className="h-24" />
          <Skeleton className="h-20" />
          <Skeleton className="h-64" />
        </div>
      }
    >
      <SalaryCapCenter />
    </Suspense>
  );
}

function SalaryCapCenter() {
  const searchParams = useSearchParams();
  const teamParam = searchParams.get("team");

  const { data: teams } = useQuery({
    queryKey: ["teams"],
    queryFn: () => api.get<Team[]>("/teams"),
    staleTime: 300_000,
  });
  const { data: health } = useQuery({
    queryKey: ["data-health"],
    queryFn: () => api.get<DataHealth>("/data-health", dataHealthSchema),
    staleTime: 120_000,
  });

  const [selectedId, setSelectedId] = useState<string | null>(null);

  // Seed selection once teams load: honor ?team=<id>, else the first team.
  const [seeded, setSeeded] = useState(false);
  if (!seeded && teams && teams.length > 0) {
    setSeeded(true);
    if (teamParam && teams.some((team) => team.id === teamParam)) setSelectedId(teamParam);
    else setSelectedId(teams[0].id);
  }

  const selectedTeam = teams?.find((team) => team.id === selectedId) ?? null;
  const identity = teamIdentity(selectedTeam?.abbreviation);

  const {
    data: outlook,
    isLoading,
    error,
  } = useQuery({
    queryKey: ["cap-outlook", selectedId],
    queryFn: () => api.get<CapOutlookResponse>(`/teams/${selectedId}/cap-outlook`),
    enabled: !!selectedId,
  });

  // Roster gives player_id -> nba_player_id so contract rows can show real photos.
  const { data: roster } = useQuery({
    queryKey: ["roster", selectedId],
    queryFn: () => api.get<RosterResponse>(`/teams/${selectedId}/roster`),
    enabled: !!selectedId,
    staleTime: 300_000,
  });
  const nbaIdByPlayer = useMemo(() => {
    const map: Record<string, number> = {};
    for (const player of roster?.roster ?? []) map[player.player_id] = player.nba_player_id;
    return map;
  }, [roster]);

  const contractsConfigured = health?.providers?.contracts?.configured ?? false;
  const capLeagueYear =
    (outlook && outlook.available ? outlook.cap_league_year : null) ??
    health?.cap_league_year ??
    null;

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="Salary-Cap Center"
        title="Payroll & commitments"
        lede="The multi-season money picture for one franchise, built strictly from imported contract data. Nothing on this page is estimated — a missing salary stays missing."
        accent={identity.bright}
        meta={
          <>
            {capLeagueYear && <Badge status="info">league year {capLeagueYear}</Badge>}
            <Badge status={contractsConfigured ? "pass" : "unavailable"}>
              contract provider {contractsConfigured ? "configured" : "not configured"}
            </Badge>
          </>
        }
        actions={
          selectedTeam ? (
            <>
              <ButtonLink href={`/team-outlook/${selectedTeam.id}`} size="sm" variant="secondary">
                Team Outlook
              </ButtonLink>
              <ButtonLink
                href={`/trade-evaluator?team=${selectedTeam.id}`}
                size="sm"
                variant="secondary"
              >
                Trade Evaluator
              </ButtonLink>
            </>
          ) : undefined
        }
      />

      {/* ---------------------------------------------------- team selector */}
      <section aria-labelledby="team-strip-heading">
        <div className="mb-2 flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
          <h2 id="team-strip-heading" className="eyebrow">
            Choose a franchise
          </h2>
          <p className="text-[11px] text-faint">Scroll the strip · all 30 teams</p>
        </div>
        {!teams ? (
          <div className="flex gap-2 overflow-hidden">
            {Array.from({ length: 12 }).map((_, index) => (
              <Skeleton key={index} className="h-[68px] w-[76px] shrink-0" />
            ))}
          </div>
        ) : (
          <div className="relative">
          <div
            role="group"
            aria-label="Choose a franchise"
            className="scroll-thin -mx-1 flex snap-x gap-2 overflow-x-auto px-1 pb-2"
          >
            {teams.map((team) => {
              const active = team.id === selectedId;
              const colors = teamIdentity(team.abbreviation);
              return (
                <button
                  key={team.id}
                  type="button"
                  onClick={() => setSelectedId(team.id)}
                  aria-pressed={active}
                  aria-label={team.full_name}
                  title={team.full_name}
                  className={`flex w-[76px] shrink-0 snap-start flex-col items-center gap-1.5 rounded-lg border px-1 py-2.5 transition-colors ${
                    active
                      ? "bg-panel2 shadow-[var(--shadow-panel)]"
                      : "border-hairline bg-panel hover:bg-panel2"
                  }`}
                  style={active ? { borderColor: colors.bright } : undefined}
                >
                  <TeamLogo
                    abbreviation={team.abbreviation}
                    name={team.full_name}
                    size={30}
                    decorative
                  />
                  <span
                    className="numeral text-[13px] leading-none"
                    style={{ color: active ? colors.bright : undefined }}
                  >
                    {team.abbreviation}
                  </span>
                  <span
                    aria-hidden
                    className="block h-0.5 w-6 rounded-full"
                    style={{ background: active ? colors.bright : "transparent" }}
                  />
                </button>
              );
            })}
          </div>
          <span
            aria-hidden
            className="pointer-events-none absolute inset-y-0 right-0 w-12 bg-gradient-to-l from-court via-court/70 to-transparent"
          />
          </div>
        )}
      </section>

      {/* -------------------------------------------------------- team head */}
      {selectedTeam && (
        <Panel accent={identity.bright} padded={false}>
          <div className="flex flex-wrap items-center gap-x-5 gap-y-3 px-4 py-4">
            <TeamCrest
              abbreviation={selectedTeam.abbreviation}
              name={selectedTeam.full_name}
              size={56}
            />
            <div className="min-w-0">
              <div className="eyebrow">{selectedTeam.city}</div>
              <h2 className="title-lg mt-0.5 whitespace-nowrap text-foreground">
                {selectedTeam.full_name}
              </h2>
            </div>
            <div className="ml-auto flex flex-wrap items-center gap-2">
              <Badge status="info">{selectedTeam.conference ?? "conference n/a"}</Badge>
              {selectedTeam.division && <Badge status="info">{selectedTeam.division}</Badge>}
            </div>
          </div>
        </Panel>
      )}

      {/* ------------------------------------------------------------ body */}
      {!selectedId || isLoading ? (
        <div className="space-y-4">
          <div className="grid gap-4 lg:grid-cols-[minmax(0,2fr)_minmax(0,1fr)]">
            <Skeleton className="h-[300px]" />
            <Skeleton className="h-[300px]" />
          </div>
          <Panel title="Contracts">
            <SkeletonRows rows={6} />
          </Panel>
        </div>
      ) : error ? (
        <ErrorState
          message={`Could not load the cap outlook: ${(error as Error).message}`}
          action={
            <ButtonLink href="/data-health" size="sm">
              Check Data Health
            </ButtonLink>
          }
        />
      ) : !outlook ? null : outlook.available ? (
        <CapOutlookView
          outlook={outlook}
          nbaIdByPlayer={nbaIdByPlayer}
          accent={identity.bright}
          teamName={selectedTeam?.full_name ?? "This team"}
        />
      ) : (
        <ContractsNotImported
          reason={outlook.reason}
          providerConfigured={outlook.contract_provider_configured}
          teamName={selectedTeam?.full_name ?? "this team"}
          accent={identity.bright}
        />
      )}
    </div>
  );
}

/* --------------------------------------------------------- default state */

/**
 * The intentional default: contracts are opt-in, so this screen is a designed
 * import guide rather than an error. It states plainly that nothing is
 * estimated in the meantime.
 */
function ContractsNotImported({
  reason,
  providerConfigured,
  teamName,
  accent,
}: {
  reason: string;
  providerConfigured: boolean;
  teamName: string;
  accent: string;
}) {
  return (
    <div className="space-y-4">
      <Panel accent={accent} padded={false}>
        <div className="relative overflow-hidden">
          {/* texture sits behind the copy — court-grid masks its own descendants */}
          <span aria-hidden className="court-grid absolute inset-0" />
          <div className="relative grid gap-6 px-5 py-6 md:px-7 md:py-8 lg:grid-cols-[minmax(0,1fr)_260px] lg:items-center">
            <div className="min-w-0">
              <div className="eyebrow flex flex-wrap items-center gap-x-2 gap-y-1">
                <span className="text-unavail">Contracts</span>
                <span aria-hidden className="text-faint">
                  /
                </span>
                <span>not imported</span>
              </div>
              <h2 className="title-xl mt-2.5 text-foreground">One import away.</h2>
              <p className="mt-2.5 max-w-xl text-[15px] leading-relaxed text-muted">
                RosterLab will not guess a salary. Until a contracts snapshot is loaded, the payroll
                view for {teamName} stays empty on purpose — no placeholder totals, no modelled cap
                space, no invented apron position.
              </p>
              <div className="mt-4 flex flex-wrap items-center gap-2">
                <Badge status={providerConfigured ? "info" : "unavailable"}>
                  provider {providerConfigured ? "configured" : "not configured"}
                </Badge>
                <Badge status="unavailable">payroll withheld</Badge>
                <Badge status="unavailable">cap position withheld</Badge>
              </div>
            </div>
            <EmptyAxesMotif className="hidden justify-self-end text-faint/45 lg:block" />
          </div>
        </div>

        <div className="border-t border-hairline px-4 py-4">
          <UnavailableNotice reason={reason} />
        </div>
      </Panel>

      <div className="grid gap-4 lg:grid-cols-[minmax(0,1.35fr)_minmax(0,1fr)]">
        <Panel
          title="Import contracts in three steps"
          subtitle="Run these once; every cap feature turns on together."
        >
          <ol className="space-y-4">
            {IMPORT_STEPS.map((step, index) => (
              <li key={step.title} className="flex gap-3.5">
                <span
                  aria-hidden
                  className="numeral flex h-8 w-8 shrink-0 items-center justify-center rounded-full border border-signal/40 bg-signal/10 text-base leading-none text-signal"
                >
                  {index + 1}
                </span>
                <div className="min-w-0 flex-1">
                  <h3 className="title-md whitespace-nowrap text-foreground">{step.title}</h3>
                  <p className="mt-1 text-[13px] leading-relaxed text-muted">{step.body}</p>
                  {step.code && (
                    <div className="scroll-thin mt-1.5 overflow-x-auto rounded-md border border-hairline bg-court px-2.5 py-1.5">
                      <code className="data whitespace-nowrap text-[12px] text-signal">
                        {step.code}
                      </code>
                    </div>
                  )}
                </div>
              </li>
            ))}
          </ol>
          <p className="mt-4 border-t border-hairline pt-3 text-[11px] leading-relaxed text-muted">
            The parser reads only the local snapshot you saved — RosterLab does not scrape
            Basketball-Reference at runtime. Provenance for every imported row shows up in the
            contracts table and in Data Health.
          </p>
        </Panel>

        <div className="space-y-4">
          <Panel title="What unlocks when you do" accent="var(--leather)">
            <ul className="space-y-3">
              {UNLOCKS.map((unlock) => (
                <li key={unlock.title} className="flex gap-2.5">
                  <span aria-hidden className="mt-0.5 shrink-0 font-mono text-brand">
                    ▸
                  </span>
                  <span className="min-w-0">
                    <span className="block text-sm font-semibold text-foreground">
                      {unlock.title}
                    </span>
                    <span className="block text-[12px] leading-snug text-muted">{unlock.body}</span>
                  </span>
                </li>
              ))}
            </ul>
          </Panel>

          <Panel title="Until then">
            <p className="text-[13px] leading-relaxed text-muted">
              Every other module keeps working on real NBA data. Trades still get a rules check —
              it simply reports an incomplete check where salary matching is involved, rather than
              claiming a deal is legal.
            </p>
            <div className="mt-3 flex flex-wrap gap-2">
              <ButtonLink href="/trade-evaluator" size="sm" variant="secondary">
                Build a deal anyway
              </ButtonLink>
              <ButtonLink href="/data-health" size="sm" variant="ghost">
                Data Health
              </ButtonLink>
            </div>
          </Panel>
        </div>
      </div>
    </div>
  );
}

/** Empty chart furniture — axes with no series, because there is nothing to draw. */
function EmptyAxesMotif({ className }: { className?: string }) {
  return (
    <div className={className}>
      <svg viewBox="0 0 220 140" className="h-[140px] w-[220px]" aria-hidden fill="none">
        <line x1="26" y1="8" x2="26" y2="116" stroke="currentColor" strokeWidth="1" />
        <line x1="26" y1="116" x2="212" y2="116" stroke="currentColor" strokeWidth="1" />
        {[34, 58, 82].map((y) => (
          <line
            key={y}
            x1="26"
            y1={y}
            x2="212"
            y2={y}
            stroke="currentColor"
            strokeWidth="1"
            strokeDasharray="2 5"
            opacity="0.6"
          />
        ))}
        {[46, 84, 122, 160, 198].map((x) => (
          <rect
            key={x}
            x={x - 13}
            y={100}
            width="26"
            height="16"
            rx="2"
            stroke="currentColor"
            strokeWidth="1"
            strokeDasharray="3 3"
            opacity="0.55"
          />
        ))}
      </svg>
      <p className="mt-1 text-right text-[11px] text-faint">No payroll drawn — nothing estimated</p>
    </div>
  );
}

/* ------------------------------------------------------- available state */

function CapOutlookView({
  outlook,
  nbaIdByPlayer,
  accent,
  teamName,
}: {
  outlook: CapOutlookAvailable;
  nbaIdByPlayer: Record<string, number>;
  accent: string;
  teamName: string;
}) {
  const seasons = outlook.seasons.map((season) => season.season);
  const missing = outlook.roster_size - outlook.players_with_contracts;
  const params = outlook.cap_parameters;
  const sourceName = outlook.players.find((player) => player.source_name)?.source_name ?? null;
  const sourceDate = outlook.players.find((player) => player.source_date)?.source_date ?? null;

  const capParamBlocks = params
    ? ([
        ["Salary cap", params.salary_cap, "var(--signal)"],
        ["Luxury tax", params.luxury_tax, "var(--conditional)"],
        ["First apron", params.first_apron, "var(--illegal)"],
        ["Second apron", params.second_apron, "var(--illegal)"],
      ] as const)
    : [];

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-2">
        {outlook.complete ? (
          <Badge status="pass">
            all {outlook.roster_size} rostered players have contract data
          </Badge>
        ) : (
          <>
            <Badge status="incomplete">
              {outlook.players_with_contracts} of {outlook.roster_size} players covered
            </Badge>
            <span className="text-[12px] text-muted">
              {missing} contract{missing === 1 ? "" : "s"} missing — season totals are partial and
              the cap position is withheld rather than estimated.
            </span>
          </>
        )}
      </div>

      <div className="grid gap-4 lg:grid-cols-[minmax(0,2fr)_minmax(0,1fr)] lg:items-start">
        <Panel
          title="Committed payroll"
          subtitle={
            outlook.complete
              ? "Sum of imported contract salaries per season"
              : "Sum of imported contract salaries per season — partial roster coverage"
          }
          accent={accent}
        >
          {outlook.seasons.length === 0 ? (
            <EmptyState
              title="No contract years found"
              hint="The import produced no season rows for this roster."
            />
          ) : (
            <>
              <SalaryTimeline
                seasons={outlook.seasons}
                capLine={params?.salary_cap}
                taxLine={params?.luxury_tax}
              />
              {params && (
                <p className="mt-2 text-[11px] leading-relaxed text-muted">
                  Dashed lines are the league cap and tax for {outlook.cap_league_year}. They apply
                  to that league year only — later seasons are shown for contract context, not as a
                  cap projection.
                </p>
              )}
            </>
          )}
          <SourceRail
            source={sourceName ? `${sourceName} (imported snapshot)` : "imported contract snapshot"}
            retrievedAt={sourceDate}
          />
        </Panel>

        <Panel title="Cap parameter reference" subtitle={`League year ${outlook.cap_league_year}`}>
          {params ? (
            <div className="grid grid-cols-2 gap-x-4 gap-y-4">
              {capParamBlocks.map(([label, value, color]) => (
                <StatBlock
                  key={label}
                  label={label}
                  value={money(value)}
                  size="sm"
                  accent={color}
                />
              ))}
            </div>
          ) : (
            <UnavailableNotice
              reason={`No league cap parameters are loaded for ${outlook.cap_league_year}, so no cap, tax or apron lines are drawn.`}
            />
          )}

          <div className="mt-4 grid grid-cols-2 gap-x-4 gap-y-4 border-t border-hairline pt-4">
            <StatBlock
              label="Contracts imported"
              value={`${outlook.players_with_contracts}/${outlook.roster_size}`}
              note="rostered players covered"
              size="sm"
              accent={outlook.complete ? "var(--legal)" : "var(--conditional)"}
            />
            <StatBlock
              label="Seasons committed"
              value={outlook.seasons.length}
              note="league years with money on the books"
              size="sm"
              accent="var(--signal)"
            />
          </div>

          <p className="mt-3 border-t border-hairline pt-3 text-[11px] leading-relaxed text-muted">
            {outlook.note}
          </p>
          <p className="mt-2 text-[11px] leading-relaxed text-unavail">
            Cap space, apron position and tax bills are not derived here — RosterLab reports only
            what the import contains.
          </p>
        </Panel>
      </div>

      <Panel
        title="Contracts"
        subtitle={`${outlook.players.length} imported contract${
          outlook.players.length === 1 ? "" : "s"
        } · PO = player option, TO = team option`}
        actions={
          !outlook.complete ? <Badge status="incomplete">partial coverage</Badge> : undefined
        }
      >
        {outlook.players.length === 0 ? (
          <EmptyState
            title="No contract rows matched this roster"
            hint={`The import ran, but none of its rows resolved to a ${teamName} player. Check the snapshot date in Data Health.`}
            action={
              <ButtonLink href="/data-health" size="sm">
                Open Data Health
              </ButtonLink>
            }
          />
        ) : (
          <>
            <div className="scroll-thin overflow-x-auto">
              <table className="w-full min-w-[820px] border-collapse">
                <caption className="sr-only">
                  Imported contracts for {teamName} by season, with option and expiring markers
                </caption>
                <thead>
                  <tr className="border-b border-line">
                    <Th>Player</Th>
                    {seasons.map((season) => (
                      <Th key={season} numeric>
                        {season}
                      </Th>
                    ))}
                    <Th>Status</Th>
                    <Th>Source</Th>
                  </tr>
                </thead>
                <tbody>
                  {outlook.players.map((player) => {
                    const bySeason = new Map(player.seasons.map((s) => [s.season, s]));
                    return (
                      <tr key={player.player_id} className="border-b border-hairline hover:bg-panel2/60">
                        <Td>
                          <span className="flex items-center gap-2.5">
                            <PlayerPhoto
                              nbaPlayerId={nbaIdByPlayer[player.player_id] ?? null}
                              name={player.name}
                              size={28}
                            />
                            <span className="whitespace-nowrap font-medium text-foreground">
                              {player.name}
                            </span>
                          </span>
                        </Td>
                        {seasons.map((season) => {
                          const year = bySeason.get(season);
                          return (
                            <Td key={season} numeric>
                              {year ? (
                                <span className="whitespace-nowrap">
                                  {money(year.salary)}
                                  {year.player_option && (
                                    <span
                                      className="ml-1 text-[10px] font-semibold text-signal"
                                      title="Player option"
                                    >
                                      PO
                                    </span>
                                  )}
                                  {year.team_option && (
                                    <span
                                      className="ml-1 text-[10px] font-semibold text-conditional"
                                      title="Team option"
                                    >
                                      TO
                                    </span>
                                  )}
                                </span>
                              ) : (
                                <span className="text-unavail">—</span>
                              )}
                            </Td>
                          );
                        })}
                        <Td>
                          <span className="flex flex-wrap gap-1">
                            {player.expiring && <Badge status="warning">expiring</Badge>}
                            {player.no_trade_clause && <Badge status="info">no-trade</Badge>}
                            {!player.expiring && !player.no_trade_clause && (
                              <span className="text-[11px] text-faint">—</span>
                            )}
                          </span>
                        </Td>
                        <Td>
                          <span className="whitespace-nowrap text-[11px] text-faint">
                            {player.source_name ?? "unknown"}
                            {player.source_date ? ` · ${formatDate(player.source_date)}` : ""}
                          </span>
                        </Td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
            <p className="mt-2.5 text-[11px] leading-relaxed text-muted">
              A dash means no salary is recorded for that player in that season — it is not a zero.
              Option years are shown at their stated value; RosterLab does not model whether an
              option will be exercised.
            </p>
          </>
        )}
        <SourceRail
          source={sourceName ? `${sourceName} (imported snapshot)` : "imported contract snapshot"}
          retrievedAt={sourceDate}
        />
      </Panel>
    </div>
  );
}
