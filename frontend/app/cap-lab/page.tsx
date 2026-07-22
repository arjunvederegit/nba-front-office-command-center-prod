"use client";

/**
 * Cap Lab — team payroll workspace over the cap-outlook endpoint.
 * DATA HONESTY: with no contract data imported the endpoint answers available=false
 * and this page renders a deliberate guided empty state (import instructions, no
 * estimates). When data exists we show exactly what the backend provides — payroll
 * by season, per-contract rows and league cap parameters — and never derive cap
 * space or apron position client-side.
 */

import { useQuery } from "@tanstack/react-query";
import { useSearchParams } from "next/navigation";
import { Suspense, useMemo, useState } from "react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { api } from "@/lib/api";
import { formatDate, money } from "@/lib/format";
import { teamTheme } from "@/lib/teamTheme";
import type {
  CapOutlookAvailable,
  CapOutlookResponse,
  CapParameters,
  RosterResponse,
  Team,
} from "@/lib/types";
import { PlayerPhoto, TeamLogo } from "@/components/media";
import {
  Badge,
  Card,
  EmptyState,
  ErrorState,
  Spinner,
  Td,
  Th,
  UnavailableNotice,
} from "@/components/ui";

/** Chart styling kept consistent with components/charts.tsx. */
const AXIS = { fill: "var(--muted)", fontSize: 11 };
const TOOLTIP_STYLE = {
  backgroundColor: "var(--panel)",
  border: "1px solid var(--border)",
  borderRadius: 6,
  fontSize: 12,
};

export default function CapLabPage() {
  return (
    <Suspense fallback={<Spinner label="Loading Cap Lab…" />}>
      <CapLab />
    </Suspense>
  );
}

function CapLab() {
  const searchParams = useSearchParams();
  const teamParam = searchParams.get("team");

  const { data: teams } = useQuery({
    queryKey: ["teams"],
    queryFn: () => api.get<Team[]>("/teams"),
    staleTime: 300_000,
  });

  const [selectedId, setSelectedId] = useState<string | null>(null);

  // Seed selection once teams load: honor ?team=<id>, else first team.
  const [seeded, setSeeded] = useState(false);
  if (!seeded && teams && teams.length > 0) {
    setSeeded(true);
    if (teamParam && teams.some((t) => t.id === teamParam)) setSelectedId(teamParam);
    else setSelectedId(teams[0].id);
  }

  const selectedTeam = teams?.find((t) => t.id === selectedId) ?? null;

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
    for (const p of roster?.roster ?? []) map[p.player_id] = p.nba_player_id;
    return map;
  }, [roster]);

  const theme = teamTheme(selectedTeam?.abbreviation);

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-2xl font-bold">Cap Lab</h1>
        <p className="mt-1 text-sm text-muted">
          Multi-season payroll picture per franchise, built strictly from imported contract data —
          nothing is estimated.
        </p>
      </div>

      {/* Team selector row */}
      {!teams ? (
        <div className="skeleton h-12 rounded-lg" />
      ) : (
        <div
          role="group"
          aria-label="Choose a team"
          className="flex flex-wrap items-center gap-1.5 rounded-lg border border-line bg-panel p-2"
        >
          {teams.map((team) => {
            const active = team.id === selectedId;
            const tTheme = teamTheme(team.abbreviation);
            return (
              <button
                key={team.id}
                type="button"
                onClick={() => setSelectedId(team.id)}
                aria-pressed={active}
                aria-label={team.full_name}
                title={team.full_name}
                className={`flex items-center gap-1 rounded-md border px-1.5 py-1 text-[11px] transition ${
                  active
                    ? "bg-panel3 font-semibold text-foreground"
                    : "border-transparent text-muted hover:bg-panel2 hover:text-foreground"
                }`}
                style={active ? { borderColor: tTheme.primary } : undefined}
              >
                <TeamLogo abbreviation={team.abbreviation} size={18} />
                {team.abbreviation}
              </button>
            );
          })}
        </div>
      )}

      {/* Team header with color accent */}
      {selectedTeam && (
        <div
          className="flex items-center gap-3 rounded-lg border border-line bg-panel px-4 py-3"
          style={{
            borderLeft: `4px solid ${theme.primary}`,
            background: `linear-gradient(90deg, ${theme.primary}1f, var(--panel) 55%)`,
          }}
        >
          <TeamLogo abbreviation={selectedTeam.abbreviation} name={selectedTeam.full_name} size={44} />
          <div>
            <h2 className="text-lg font-bold">{selectedTeam.full_name}</h2>
            <p className="text-xs text-muted">
              {selectedTeam.city} · {selectedTeam.conference ?? "—"}
              {selectedTeam.division ? ` · ${selectedTeam.division}` : ""}
            </p>
          </div>
        </div>
      )}

      {!selectedId || isLoading ? (
        <Spinner label="Loading cap outlook…" />
      ) : error ? (
        <ErrorState message={(error as Error).message} />
      ) : !outlook ? null : outlook.available ? (
        <CapOutlookView outlook={outlook} nbaIdByPlayer={nbaIdByPlayer} accent={theme.bright} />
      ) : (
        <ContractsMissingState
          reason={outlook.reason}
          providerConfigured={outlook.contract_provider_configured}
        />
      )}
    </div>
  );
}

/**
 * The intentional default state: contract data is opt-in and manually imported,
 * so we guide the user through the import instead of showing a broken page.
 */
function ContractsMissingState({
  reason,
  providerConfigured,
}: {
  reason: string;
  providerConfigured: boolean;
}) {
  return (
    <Card
      title="Contract data not imported"
      subtitle="Cap Lab renders only real, imported contracts"
      actions={
        <Badge status={providerConfigured ? "info" : "unavailable"}>
          provider {providerConfigured ? "configured" : "not configured"}
        </Badge>
      }
    >
      <div className="space-y-4">
        <UnavailableNotice reason={reason} />
        <div className="rounded-md border border-line bg-panel2 p-4">
          <h3 className="text-sm font-semibold">How to import contracts</h3>
          <ol className="mt-2 list-decimal space-y-1.5 pl-5 text-sm text-muted">
            <li>
              Download the Basketball-Reference player-contracts page and save the snapshot to{" "}
              <code className="rounded bg-panel3 px-1 py-0.5 text-[12px] text-foreground">
                data/imports/contracts/players.html
              </code>
              .
            </li>
            <li>
              Set{" "}
              <code className="rounded bg-panel3 px-1 py-0.5 text-[12px] text-foreground">
                CONTRACT_DATA_PROVIDER=bbref_snapshot
              </code>{" "}
              in your environment (.env).
            </li>
            <li>
              Run{" "}
              <code className="rounded bg-panel3 px-1 py-0.5 text-[12px] text-foreground">
                make sync-data
              </code>{" "}
              to parse and load the contracts.
            </li>
          </ol>
        </div>
        <p className="text-xs text-muted">
          Nothing here is estimated without imported contracts — no salaries, payroll totals, cap
          space or apron positions are ever invented. Once the import runs, this page fills in
          automatically.
        </p>
      </div>
    </Card>
  );
}

function CapOutlookView({
  outlook,
  nbaIdByPlayer,
  accent,
}: {
  outlook: CapOutlookAvailable;
  nbaIdByPlayer: Record<string, number>;
  accent: string;
}) {
  const seasons = outlook.seasons.map((s) => s.season);
  const missing = outlook.roster_size - outlook.players_with_contracts;

  return (
    <div className="space-y-4">
      {!outlook.complete && (
        <div className="flex flex-wrap items-center gap-2">
          <Badge status="warning">
            only {outlook.players_with_contracts} of {outlook.roster_size} rostered players have
            contract data — totals are partial and cap position is withheld
          </Badge>
          <span className="text-xs text-muted">({missing} players missing contracts)</span>
        </div>
      )}
      {outlook.complete && (
        <Badge status="pass">
          all {outlook.roster_size} rostered players have contract data
        </Badge>
      )}

      <div className="grid gap-4 lg:grid-cols-3">
        <Card
          title="Payroll by season"
          subtitle={
            outlook.complete
              ? "Sum of imported contract salaries per season"
              : "Sum of imported contract salaries per season — partial roster coverage"
          }
          className="lg:col-span-2"
        >
          <SalaryTimeline
            seasons={outlook.seasons}
            capParameters={outlook.cap_parameters}
            accent={accent}
          />
          {outlook.cap_parameters && (
            <p className="mt-2 text-[11px] text-muted">
              Dashed lines: league cap parameters for {outlook.cap_league_year} (they apply to that
              league year; later seasons are shown for contract context only).
            </p>
          )}
        </Card>

        <Card title="Cap parameter reference" subtitle={`League year ${outlook.cap_league_year}`}>
          {outlook.cap_parameters ? (
            <dl className="space-y-2.5">
              {(
                [
                  ["Salary cap", outlook.cap_parameters.salary_cap],
                  ["Luxury tax", outlook.cap_parameters.luxury_tax],
                  ["First apron", outlook.cap_parameters.first_apron],
                  ["Second apron", outlook.cap_parameters.second_apron],
                ] as const
              ).map(([label, value]) => (
                <div key={label} className="flex items-baseline justify-between gap-2">
                  <dt className="text-xs text-muted">{label}</dt>
                  <dd className="text-sm font-semibold tabular-nums">{money(value)}</dd>
                </div>
              ))}
            </dl>
          ) : (
            <EmptyState
              title="Cap parameters unavailable"
              hint={`No league cap parameters loaded for ${outlook.cap_league_year}.`}
            />
          )}
          <p className="mt-3 border-t border-line pt-3 text-[11px] text-muted">{outlook.note}</p>
        </Card>
      </div>

      <Card
        title="Contracts"
        subtitle={`${outlook.players.length} contracts · PO = player option, TO = team option`}
      >
        {outlook.players.length === 0 ? (
          <EmptyState title="No contract rows" hint="No imported contracts matched this roster." />
        ) : (
          <div className="overflow-x-auto">
            <table className="min-w-[760px] w-full">
              <thead>
                <tr className="border-b border-line">
                  <Th>Player</Th>
                  {seasons.map((season) => (
                    <Th key={season} className="text-right">
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
                    <tr key={player.player_id} className="border-b border-line/60 hover:bg-panel2/60">
                      <Td>
                        <span className="flex items-center gap-2">
                          <PlayerPhoto
                            nbaPlayerId={nbaIdByPlayer[player.player_id] ?? null}
                            name={player.name}
                            size={28}
                          />
                          <span className="whitespace-nowrap font-medium">{player.name}</span>
                        </span>
                      </Td>
                      {seasons.map((season) => {
                        const year = bySeason.get(season);
                        return (
                          <Td key={season} className="text-right tabular-nums">
                            {year ? (
                              <>
                                {money(year.salary)}
                                {year.player_option && (
                                  <span
                                    className="ml-1 text-[10px] font-semibold text-accent"
                                    title="Player option"
                                  >
                                    PO
                                  </span>
                                )}
                                {year.team_option && (
                                  <span
                                    className="ml-1 text-[10px] font-semibold text-warn"
                                    title="Team option"
                                  >
                                    TO
                                  </span>
                                )}
                              </>
                            ) : (
                              <span className="text-muted">—</span>
                            )}
                          </Td>
                        );
                      })}
                      <Td>
                        <span className="flex flex-wrap gap-1">
                          {player.expiring && <Badge status="warning">expiring</Badge>}
                          {player.no_trade_clause && <Badge status="info">no-trade</Badge>}
                        </span>
                      </Td>
                      <Td>
                        <span className="whitespace-nowrap text-[11px] text-muted">
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
        )}
      </Card>
    </div>
  );
}

/** Payroll-by-season bars with league cap parameters as reference lines. */
function SalaryTimeline({
  seasons,
  capParameters,
  accent,
}: {
  seasons: { season: string; total: number; players: number }[];
  capParameters: CapParameters | null;
  accent: string;
}) {
  const data = seasons.map((s) => ({ ...s }));
  if (data.length === 0) {
    return <EmptyState title="No seasons" hint="No contract years were found." />;
  }
  return (
    <ResponsiveContainer width="100%" height={260}>
      <BarChart data={data} margin={{ left: 8, right: 16, top: 10 }}>
        <CartesianGrid stroke="var(--border)" strokeDasharray="3 3" vertical={false} />
        <XAxis dataKey="season" tick={AXIS} />
        <YAxis tick={AXIS} tickFormatter={(v: number) => money(v)} width={70} />
        <Tooltip
          contentStyle={TOOLTIP_STYLE}
          formatter={(value, _name, item) => [
            `${money(Number(value))} · ${(item?.payload as { players?: number })?.players ?? "?"} players under contract`,
            "payroll",
          ]}
        />
        {capParameters && (
          <>
            <ReferenceLine
              y={capParameters.salary_cap}
              stroke="var(--pass)"
              strokeDasharray="4 4"
              label={{ value: "cap", position: "insideTopRight", ...AXIS }}
            />
            <ReferenceLine
              y={capParameters.luxury_tax}
              stroke="var(--warn)"
              strokeDasharray="4 4"
              label={{ value: "tax", position: "insideTopRight", ...AXIS }}
            />
            <ReferenceLine
              y={capParameters.first_apron}
              stroke="var(--fail)"
              strokeDasharray="4 4"
              label={{ value: "1st apron", position: "insideTopRight", ...AXIS }}
            />
            <ReferenceLine
              y={capParameters.second_apron}
              stroke="var(--fail)"
              strokeDasharray="2 4"
              label={{ value: "2nd apron", position: "insideTopRight", ...AXIS }}
            />
          </>
        )}
        <Bar dataKey="total" fill={accent} fillOpacity={0.8} radius={[4, 4, 0, 0]} barSize={38} />
      </BarChart>
    </ResponsiveContainer>
  );
}
