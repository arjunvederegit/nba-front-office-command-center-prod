"use client";

/**
 * Player Lab — fan-facing exploration of the imported season-totals directory.
 * One request loads every imported player; search/filter/sort, league-percentile
 * context and a 2-4 player comparison drawer all run client-side. Totals mode and
 * per-game mode are strictly separated — the two scales are never mixed in one view.
 */

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Suspense, useMemo, useState } from "react";
import { api } from "@/lib/api";
import { pct } from "@/lib/format";
import { teamTheme } from "@/lib/teamTheme";
import type { SeasonTotalsPlayer, SeasonTotalsResponse, Team } from "@/lib/types";
import { PlayerPhoto, TeamLogo } from "@/components/media";
import {
  Card,
  EmptyState,
  ErrorState,
  MeterBar,
  SourceLine,
  Spinner,
  Td,
  Th,
} from "@/components/ui";

const SEASON = "2025-26";

type Mode = "per_game" | "totals";

/** Columns shown in the directory; `kind` decides which stat bag a value reads from. */
interface StatColumn {
  key: string;
  label: string;
  kind: "counting" | "rate";
  digits?: number;
}

const COUNTING_COLUMNS: StatColumn[] = [
  { key: "PTS", label: "PTS", kind: "counting" },
  { key: "REB", label: "REB", kind: "counting" },
  { key: "AST", label: "AST", kind: "counting" },
  { key: "STL", label: "STL", kind: "counting" },
  { key: "BLK", label: "BLK", kind: "counting" },
];

const RATE_COLUMNS: StatColumn[] = [
  { key: "FG_PCT", label: "FG%", kind: "rate" },
  { key: "FG3_PCT", label: "3P%", kind: "rate" },
  { key: "FT_PCT", label: "FT%", kind: "rate" },
  { key: "EFF", label: "EFF", kind: "rate", digits: 1 },
];

const ALL_COLUMNS = [...COUNTING_COLUMNS, ...RATE_COLUMNS];

function statValue(player: SeasonTotalsPlayer, column: StatColumn, mode: Mode): number | null {
  const bag =
    column.kind === "rate" ? player.rates : mode === "per_game" ? player.per_game : player.totals;
  const value = bag?.[column.key];
  return typeof value === "number" ? value : null;
}

function formatStat(value: number | null, column: StatColumn, mode: Mode): string {
  if (value === null) return "—";
  if (column.kind === "rate") {
    if (column.key.endsWith("_PCT")) return pct(value, 1);
    return value.toFixed(column.digits ?? 1);
  }
  return mode === "per_game" ? value.toFixed(1) : String(Math.round(value));
}

/** Share of loaded players at or below this value (0-100). */
function percentileOf(sortedValues: number[], value: number): number {
  if (sortedValues.length === 0) return 0;
  let lo = 0;
  let hi = sortedValues.length;
  while (lo < hi) {
    const mid = (lo + hi) >> 1;
    if (sortedValues[mid] <= value) lo = mid + 1;
    else hi = mid;
  }
  return (lo / sortedValues.length) * 100;
}

const PAGE_SIZE = 100;
const COMPARE_MAX = 4;
const COMPARE_MIN = 2;

/** Rows of the comparison panel: always the per-game line plus rates (labeled). */
const COMPARE_ROWS: { label: string; get: (p: SeasonTotalsPlayer) => number | null; fmt: (v: number) => string }[] = [
  { label: "MIN/g", get: (p) => numOrNull(p.per_game.MIN), fmt: (v) => v.toFixed(1) },
  { label: "PTS/g", get: (p) => numOrNull(p.per_game.PTS), fmt: (v) => v.toFixed(1) },
  { label: "REB/g", get: (p) => numOrNull(p.per_game.REB), fmt: (v) => v.toFixed(1) },
  { label: "AST/g", get: (p) => numOrNull(p.per_game.AST), fmt: (v) => v.toFixed(1) },
  { label: "STL/g", get: (p) => numOrNull(p.per_game.STL), fmt: (v) => v.toFixed(1) },
  { label: "BLK/g", get: (p) => numOrNull(p.per_game.BLK), fmt: (v) => v.toFixed(1) },
  { label: "TOV/g", get: (p) => numOrNull(p.per_game.TOV), fmt: (v) => v.toFixed(1) },
  { label: "FG%", get: (p) => numOrNull(p.rates.FG_PCT), fmt: (v) => pct(v, 1) },
  { label: "3P%", get: (p) => numOrNull(p.rates.FG3_PCT), fmt: (v) => pct(v, 1) },
  { label: "FT%", get: (p) => numOrNull(p.rates.FT_PCT), fmt: (v) => pct(v, 1) },
  { label: "AST/TOV", get: (p) => numOrNull(p.rates.AST_TOV), fmt: (v) => v.toFixed(2) },
  { label: "EFF", get: (p) => numOrNull(p.rates.EFF), fmt: (v) => v.toFixed(1) },
];

function numOrNull(value: number | null | undefined): number | null {
  return typeof value === "number" ? value : null;
}

export default function PlayerLabPage() {
  return (
    <Suspense fallback={<Spinner label="Loading Player Lab…" />}>
      <PlayerLab />
    </Suspense>
  );
}

function PlayerLab() {
  const searchParams = useSearchParams();
  const teamParam = searchParams.get("team");

  const {
    data,
    isLoading,
    error,
  } = useQuery({
    queryKey: ["season-totals", SEASON],
    queryFn: () => api.get<SeasonTotalsResponse>(`/players/season-totals/${SEASON}`),
    staleTime: 300_000,
  });
  const { data: teams } = useQuery({
    queryKey: ["teams"],
    queryFn: () => api.get<Team[]>("/teams"),
    staleTime: 300_000,
  });

  const [search, setSearch] = useState("");
  const [teamAbbr, setTeamAbbr] = useState<string>("all");
  const [mode, setMode] = useState<Mode>("per_game");
  const [sortKey, setSortKey] = useState<string>("PTS");
  const [sortDir, setSortDir] = useState<"desc" | "asc">("desc");
  const [visibleCount, setVisibleCount] = useState(PAGE_SIZE);
  const [selected, setSelected] = useState<string[]>([]);
  const [compareOpen, setCompareOpen] = useState(false);

  // Preselect the team filter from ?team=<team_id> once teams are loaded.
  const [seededTeamParam, setSeededTeamParam] = useState<string | null>(null);
  if (teamParam && teams && seededTeamParam !== teamParam) {
    setSeededTeamParam(teamParam);
    const match = teams.find((t) => t.id === teamParam);
    if (match) setTeamAbbr(match.abbreviation);
  }

  const players = useMemo(() => data?.players ?? [], [data]);
  const sortColumn = ALL_COLUMNS.find((c) => c.key === sortKey) ?? COUNTING_COLUMNS[0];

  /** Sorted values of the active sort stat across ALL loaded players (league context). */
  const leagueValues = useMemo(() => {
    const values: number[] = [];
    for (const player of players) {
      const v = statValue(player, sortColumn, mode);
      if (v !== null) values.push(v);
    }
    values.sort((a, b) => a - b);
    return values;
  }, [players, sortColumn, mode]);

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase();
    const rows = players.filter(
      (p) =>
        (teamAbbr === "all" || p.team_abbr === teamAbbr) &&
        (q.length === 0 || p.name.toLowerCase().includes(q)),
    );
    rows.sort((a, b) => {
      const av = statValue(a, sortColumn, mode);
      const bv = statValue(b, sortColumn, mode);
      if (av === null && bv === null) return a.name.localeCompare(b.name);
      if (av === null) return 1;
      if (bv === null) return -1;
      return sortDir === "desc" ? bv - av : av - bv;
    });
    return rows;
  }, [players, search, teamAbbr, sortColumn, sortDir, mode]);

  const selectedPlayers = useMemo(
    () => selected.map((id) => players.find((p) => p.player_id === id)).filter(Boolean) as SeasonTotalsPlayer[],
    [selected, players],
  );

  function toggleSelected(playerId: string) {
    setSelected((prev) => {
      if (prev.includes(playerId)) return prev.filter((id) => id !== playerId);
      if (prev.length >= COMPARE_MAX) return prev;
      return [...prev, playerId];
    });
  }

  function clearSelection() {
    setSelected([]);
    setCompareOpen(false);
  }

  function setSort(key: string) {
    if (key === sortKey) setSortDir((d) => (d === "desc" ? "asc" : "desc"));
    else {
      setSortKey(key);
      setSortDir("desc");
    }
  }

  if (isLoading) {
    return (
      <div className="space-y-4">
        <PageIntro />
        <div className="skeleton h-10 rounded-lg" />
        <div className="skeleton h-96 rounded-lg" />
      </div>
    );
  }
  if (error) {
    return (
      <div className="space-y-4">
        <PageIntro />
        <ErrorState message={(error as Error).message} />
      </div>
    );
  }
  if (!data || !data.available) {
    return (
      <div className="space-y-4">
        <PageIntro />
        <EmptyState
          title="No season totals imported"
          hint={data?.note ?? "No totals imported for this season."}
        />
      </div>
    );
  }

  const modeSuffix = mode === "per_game" ? "/g" : " (tot)";
  const visible = filtered.slice(0, visibleCount);

  return (
    <div className="space-y-4 pb-24">
      <PageIntro source={data.source} importedAt={data.imported_at} />

      {/* Toolbar */}
      <Card>
        <div className="flex flex-wrap items-center gap-3">
          <input
            type="search"
            aria-label="Search players by name"
            placeholder="Search players…"
            value={search}
            onChange={(e) => {
              setSearch(e.target.value);
              setVisibleCount(PAGE_SIZE);
            }}
            className="w-full rounded-md border border-line bg-panel2 px-3 py-1.5 text-sm placeholder:text-muted/70 sm:w-56"
          />
          <label className="flex items-center gap-2 text-xs text-muted">
            Team
            <select
              aria-label="Filter by team"
              value={teamAbbr}
              onChange={(e) => {
                setTeamAbbr(e.target.value);
                setVisibleCount(PAGE_SIZE);
              }}
              className="rounded-md border border-line bg-panel2 px-2 py-1.5 text-sm text-foreground"
            >
              <option value="all">All teams</option>
              {(teams ?? []).map((team) => (
                <option key={team.id} value={team.abbreviation}>
                  {team.abbreviation} — {team.full_name}
                </option>
              ))}
            </select>
          </label>
          <label className="flex items-center gap-2 text-xs text-muted">
            Sort by
            <select
              aria-label="Sort by stat"
              value={sortKey}
              onChange={(e) => setSort(e.target.value)}
              className="rounded-md border border-line bg-panel2 px-2 py-1.5 text-sm text-foreground"
            >
              {ALL_COLUMNS.map((col) => (
                <option key={col.key} value={col.key}>
                  {col.label}
                  {col.kind === "counting" ? modeSuffix : ""}
                </option>
              ))}
            </select>
          </label>
          <div
            role="group"
            aria-label="Stat display mode"
            className="ml-auto flex overflow-hidden rounded-md border border-line text-xs"
          >
            {(
              [
                ["per_game", "Per game"],
                ["totals", "Season totals"],
              ] as const
            ).map(([value, label]) => (
              <button
                key={value}
                type="button"
                aria-pressed={mode === value}
                onClick={() => setMode(value)}
                className={`px-3 py-1.5 transition-colors ${
                  mode === value
                    ? "bg-brand/15 font-semibold text-brand"
                    : "bg-panel2 text-muted hover:text-foreground"
                }`}
              >
                {label}
              </button>
            ))}
          </div>
        </div>
        <p className="mt-2 text-[11px] text-muted">
          Showing{" "}
          <span className="font-semibold text-foreground">
            {mode === "per_game" ? "per-game values (derived using GP)" : "raw season totals"}
          </span>{" "}
          — the two scales are never mixed. Shooting rates and EFF are scale-independent. Bar next
          to the sorted column = league percentile (among {data.count} imported players).
        </p>
      </Card>

      {/* Directory */}
      <Card
        title={`Player directory · ${data.season}`}
        subtitle={`${filtered.length} of ${data.count} players · sorted by ${sortColumn.label}${
          sortColumn.kind === "counting" ? modeSuffix : ""
        } (${sortDir === "desc" ? "high → low" : "low → high"})`}
      >
        {filtered.length === 0 ? (
          <EmptyState title="No players match" hint="Adjust the search or team filter." />
        ) : (
          <div className="overflow-x-auto">
            <table className="min-w-[880px] w-full">
              <thead>
                <tr className="border-b border-line">
                  <Th className="w-8">
                    <span className="sr-only">Select for comparison</span>
                  </Th>
                  <Th>Player</Th>
                  <Th>Team</Th>
                  <Th>Pos</Th>
                  <Th className="text-right">GP</Th>
                  {ALL_COLUMNS.map((col) => (
                    <Th key={col.key} className="text-right">
                      <button
                        type="button"
                        onClick={() => setSort(col.key)}
                        aria-label={`Sort by ${col.label}${col.kind === "counting" ? (mode === "per_game" ? " per game" : " season total") : ""}`}
                        className={`uppercase tracking-wider ${
                          sortKey === col.key ? "text-brand" : "hover:text-foreground"
                        }`}
                      >
                        {col.label}
                        {col.kind === "counting" ? modeSuffix : ""}
                        {sortKey === col.key ? (sortDir === "desc" ? " ↓" : " ↑") : ""}
                      </button>
                    </Th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {visible.map((player) => {
                  const theme = teamTheme(player.team_abbr);
                  const isSelected = selected.includes(player.player_id);
                  const sortValue = statValue(player, sortColumn, mode);
                  const percentile = sortValue === null ? null : percentileOf(leagueValues, sortValue);
                  return (
                    <tr key={player.player_id} className="border-b border-line/60 hover:bg-panel2/60">
                      <Td>
                        <input
                          type="checkbox"
                          checked={isSelected}
                          disabled={!isSelected && selected.length >= COMPARE_MAX}
                          onChange={() => toggleSelected(player.player_id)}
                          aria-label={`Select ${player.name} for comparison`}
                          className="h-4 w-4 accent-[var(--brand)]"
                        />
                      </Td>
                      <Td>
                        <Link
                          href={`/players/${player.player_id}`}
                          className="flex items-center gap-2 hover:text-brand"
                        >
                          <PlayerPhoto nbaPlayerId={player.nba_player_id} name={player.name} size={28} />
                          <span className="whitespace-nowrap font-medium">{player.name}</span>
                        </Link>
                      </Td>
                      <Td>
                        {player.team_abbr ? (
                          <span
                            className="inline-flex items-center gap-1.5 rounded-full border px-1.5 py-0.5 text-[11px]"
                            style={{ borderColor: `${theme.primary}66` }}
                          >
                            <TeamLogo abbreviation={player.team_abbr} size={16} />
                            {player.team_abbr}
                          </span>
                        ) : (
                          <span className="text-xs text-muted">—</span>
                        )}
                      </Td>
                      <Td className="text-muted">{player.position ?? "—"}</Td>
                      <Td className="text-right tabular-nums">{player.gp}</Td>
                      {ALL_COLUMNS.map((col) => {
                        const value = statValue(player, col, mode);
                        const isSortCol = col.key === sortKey;
                        return (
                          <Td key={col.key} className="text-right tabular-nums">
                            <span className={isSortCol ? "font-semibold text-foreground" : undefined}>
                              {formatStat(value, col, mode)}
                            </span>
                            {isSortCol && percentile !== null && (
                              <MeterBar
                                value={percentile}
                                max={100}
                                color="var(--brand)"
                                className="mt-1 !h-1 w-14 min-w-14"
                              />
                            )}
                          </Td>
                        );
                      })}
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
        {filtered.length > visibleCount && (
          <div className="mt-3 text-center">
            <button
              type="button"
              onClick={() => setVisibleCount(filtered.length)}
              className="rounded-md border border-line bg-panel2 px-4 py-1.5 text-sm text-muted transition hover:text-foreground"
            >
              Show all {filtered.length} players
            </button>
          </div>
        )}
      </Card>

      {/* Comparison panel */}
      {compareOpen && selectedPlayers.length >= COMPARE_MIN && (
        <ComparePanel players={selectedPlayers} onClose={() => setCompareOpen(false)} />
      )}

      {/* Sticky selection bar */}
      {selected.length > 0 && (
        <div className="fixed inset-x-0 bottom-0 z-40 border-t border-line bg-panel/95 backdrop-blur">
          <div className="mx-auto flex max-w-7xl flex-wrap items-center gap-3 px-4 py-2.5">
            <div className="flex items-center gap-1.5" aria-live="polite">
              {selectedPlayers.map((p) => (
                <PlayerPhoto key={p.player_id} nbaPlayerId={p.nba_player_id} name={p.name} size={26} />
              ))}
              <span className="ml-1 text-xs text-muted">
                {selected.length} of {COMPARE_MAX} selected
                {selected.length < COMPARE_MIN ? " — pick at least 2 to compare" : ""}
              </span>
            </div>
            <div className="ml-auto flex items-center gap-2">
              <button
                type="button"
                onClick={clearSelection}
                className="rounded-md border border-line px-3 py-1.5 text-xs text-muted transition hover:text-foreground"
              >
                Clear selection
              </button>
              <button
                type="button"
                disabled={selected.length < COMPARE_MIN}
                onClick={() => setCompareOpen(true)}
                className="rounded-md bg-brand px-4 py-1.5 text-xs font-semibold text-black transition enabled:hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-40"
              >
                Compare
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

function PageIntro({ source, importedAt }: { source?: string; importedAt?: string | null }) {
  return (
    <div>
      <h1 className="text-2xl font-bold">Player Lab</h1>
      <p className="mt-1 text-sm text-muted">
        Explore every imported player — search, filter by team, sort by any stat and pull up to
        four players into a side-by-side comparison.
      </p>
      {source && (
        <SourceLine source={source} retrievedAt={importedAt ?? null} className="mt-1.5" />
      )}
      {source && (
        <p className="text-[11px] text-muted">
          Values labeled &ldquo;season totals&rdquo; are raw totals; per-game values are derived by
          dividing totals by games played (GP).
        </p>
      )}
    </div>
  );
}

function ComparePanel({
  players,
  onClose,
}: {
  players: SeasonTotalsPlayer[];
  onClose: () => void;
}) {
  return (
    <Card
      title={`Comparing ${players.length} players`}
      subtitle="Per-game line (derived using GP), shooting rates and EFF · best value per row highlighted"
      actions={
        <button
          type="button"
          onClick={onClose}
          aria-label="Close comparison"
          className="rounded-md border border-line px-2.5 py-1 text-xs text-muted transition hover:text-foreground"
        >
          Close
        </button>
      }
    >
      <div className="overflow-x-auto">
        <table className="min-w-[560px] w-full">
          <thead>
            <tr className="border-b border-line">
              <Th>Stat</Th>
              {players.map((p) => {
                const theme = teamTheme(p.team_abbr);
                return (
                  <Th key={p.player_id}>
                    <Link
                      href={`/players/${p.player_id}`}
                      className="flex items-center gap-2 normal-case tracking-normal hover:text-brand"
                    >
                      <PlayerPhoto nbaPlayerId={p.nba_player_id} name={p.name} size={34} />
                      <span>
                        <span className="block text-xs font-semibold text-foreground">{p.name}</span>
                        <span
                          className="block text-[10px]"
                          style={{ color: theme.bright }}
                        >
                          {p.team_abbr ?? "—"} · {p.position ?? "—"} · {p.gp} GP
                        </span>
                      </span>
                    </Link>
                  </Th>
                );
              })}
            </tr>
          </thead>
          <tbody>
            {COMPARE_ROWS.map((row) => {
              const values = players.map((p) => row.get(p));
              const best = values.reduce<number | null>(
                (acc, v) => (v !== null && (acc === null || v > acc) ? v : acc),
                null,
              );
              return (
                <tr key={row.label} className="border-b border-line/60">
                  <Td className="text-muted">{row.label}</Td>
                  {players.map((p, i) => {
                    const value = values[i];
                    const isBest = value !== null && best !== null && value === best;
                    return (
                      <Td
                        key={p.player_id}
                        className={`tabular-nums ${
                          isBest ? "bg-pass/10 font-semibold text-pass" : ""
                        }`}
                      >
                        {value === null ? "—" : row.fmt(value)}
                      </Td>
                    );
                  })}
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </Card>
  );
}
