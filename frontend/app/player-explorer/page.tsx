"use client";

/**
 * Player Explorer — the research surface over the imported season directory.
 *
 * One request loads every imported player; search, filters, sorting, league
 * percentile context and the 2–4 player comparison all run client-side. Totals
 * mode and per-game mode stay strictly separated: the two scales are never mixed
 * inside a single view, and the provenance rail says which one you're reading.
 */

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Suspense, useMemo, useState } from "react";
import { api } from "@/lib/api";
import { useHydrated } from "@/lib/hydrated";
import { ordinal, pct } from "@/lib/format";
import {
  ALL_COLUMNS,
  COUNTING_COLUMNS,
  QUALIFY_MIN,
  formatStat,
  numOrNull,
  percentileOf,
  qualifies,
  statValue,
} from "@/lib/playerStats";
import type { Mode } from "@/lib/playerStats";
import { teamIdentity } from "@/lib/teamIdentity";
import type { SeasonTotalsPlayer, SeasonTotalsResponse, Team } from "@/lib/types";
import { PlayerPhoto, TeamLogo } from "@/components/media";
import {
  Badge,
  Button,
  EmptyState,
  ErrorState,
  MeterBar,
  PageHeader,
  Panel,
  SegmentedControl,
  Skeleton,
  SkeletonRows,
  SourceRail,
  Td,
  Th,
} from "@/components/ui";

const SEASON = "2025-26";

type PositionGroup = "all" | "Guards" | "Wings" | "Bigs";

function positionGroup(position: string | null): PositionGroup {
  const p = (position ?? "").toUpperCase();
  if (!p) return "all";
  if (p.includes("C")) return "Bigs";
  if (p.includes("G") && !p.includes("F")) return "Guards";
  return "Wings";
}

const PAGE_SIZE = 60;
const COMPARE_MAX = 4;
const COMPARE_MIN = 2;

/** Rows of the comparison panel: always the per-game line plus rates (labeled). */
const COMPARE_ROWS: {
  label: string;
  get: (p: SeasonTotalsPlayer) => number | null;
  fmt: (v: number) => string;
  better: "high" | "low";
}[] = [
  { label: "MIN/g", get: (p) => numOrNull(p.per_game.MIN), fmt: (v) => v.toFixed(1), better: "high" },
  { label: "PTS/g", get: (p) => numOrNull(p.per_game.PTS), fmt: (v) => v.toFixed(1), better: "high" },
  { label: "REB/g", get: (p) => numOrNull(p.per_game.REB), fmt: (v) => v.toFixed(1), better: "high" },
  { label: "AST/g", get: (p) => numOrNull(p.per_game.AST), fmt: (v) => v.toFixed(1), better: "high" },
  { label: "STL/g", get: (p) => numOrNull(p.per_game.STL), fmt: (v) => v.toFixed(1), better: "high" },
  { label: "BLK/g", get: (p) => numOrNull(p.per_game.BLK), fmt: (v) => v.toFixed(1), better: "high" },
  { label: "TOV/g", get: (p) => numOrNull(p.per_game.TOV), fmt: (v) => v.toFixed(1), better: "low" },
  { label: "FG%", get: (p) => numOrNull(p.rates.FG_PCT), fmt: (v) => pct(v, 1), better: "high" },
  { label: "3P%", get: (p) => numOrNull(p.rates.FG3_PCT), fmt: (v) => pct(v, 1), better: "high" },
  { label: "FT%", get: (p) => numOrNull(p.rates.FT_PCT), fmt: (v) => pct(v, 1), better: "high" },
  { label: "AST/TOV", get: (p) => numOrNull(p.rates.AST_TOV), fmt: (v) => v.toFixed(2), better: "high" },
  { label: "EFF/g", get: (p) => numOrNull(p.per_game.EFF), fmt: (v) => v.toFixed(1), better: "high" },
];

export default function PlayerExplorerPage() {
  return (
    <Suspense fallback={<ExplorerSkeleton />}>
      <PlayerExplorer />
    </Suspense>
  );
}

function PlayerExplorer() {
  const searchParams = useSearchParams();
  const teamParam = searchParams.get("team");

  const { data, isLoading, error } = useQuery({
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
  const [position, setPosition] = useState<PositionGroup>("all");
  const [minGames, setMinGames] = useState(0);
  const [mode, setMode] = useState<Mode>("per_game");
  const [sortKey, setSortKey] = useState<string>("PTS");
  const [sortDir, setSortDir] = useState<"desc" | "asc">("desc");
  const [visibleCount, setVisibleCount] = useState(PAGE_SIZE);
  const [selected, setSelected] = useState<string[]>([]);
  const [compareOpen, setCompareOpen] = useState(false);

  // Preselect the team filter from ?team=<team_id> once teams are loaded.
  // Gated on hydration: the shell above these pages hydrates first and warms the shared
  // `["teams"]` query cache, so `teams` can already be present on this page's very first
  // client render. Seeding state from it during that render makes the client tree differ
  // from the server HTML and React throws a hydration error. `useHydrated()` is false for
  // the hydration render, so the seed happens in the commit straight after it instead.
  const hydrated = useHydrated();
  const [seededTeamParam, setSeededTeamParam] = useState<string | null>(null);
  if (hydrated && teamParam && teams && seededTeamParam !== teamParam) {
    setSeededTeamParam(teamParam);
    const match = teams.find((t) => t.id === teamParam);
    if (match) setTeamAbbr(match.abbreviation);
  }

  const players = useMemo(() => data?.players ?? [], [data]);
  const sortColumn = ALL_COLUMNS.find((c) => c.key === sortKey) ?? COUNTING_COLUMNS[0];

  /**
   * The population a percentile on the sorted stat is a percentile *of*.
   *
   * Deliberately not every loaded player. A percentile answers "how many of the league
   * is this player above", and a player with two three-point attempts is not evidence
   * about the league — 67 such players sat at exactly 0 % or 100 % from three, pinning
   * both ends of the scale that everyone else was read against. The population is the
   * players whose sample reaches `QUALIFY_MIN` of the column's own denominator, and it
   * ignores the team/position/search filters on purpose: narrowing the *view* must not
   * silently redefine what "league percentile" means.
   */
  const leagueValues = useMemo(() => {
    const values: number[] = [];
    for (const player of players) {
      if (!qualifies(player, sortColumn)) continue;
      const value = statValue(player, sortColumn, mode);
      if (value !== null) values.push(value);
    }
    values.sort((a, b) => a - b);
    return values;
  }, [players, sortColumn, mode]);

  const belowQualifier = useMemo(
    () => players.filter((p) => !qualifies(p, sortColumn)).length,
    [players, sortColumn],
  );

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase();
    const rows = players.filter(
      (p) =>
        (teamAbbr === "all" || p.team_abbr === teamAbbr) &&
        (position === "all" || positionGroup(p.position) === position) &&
        (p.gp ?? 0) >= minGames &&
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
  }, [players, search, teamAbbr, position, minGames, sortColumn, sortDir, mode]);

  const selectedPlayers = useMemo(
    () =>
      selected
        .map((id) => players.find((p) => p.player_id === id))
        .filter(Boolean) as SeasonTotalsPlayer[],
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

  function resetFilters() {
    setSearch("");
    setTeamAbbr("all");
    setPosition("all");
    setMinGames(0);
    setVisibleCount(PAGE_SIZE);
  }

  const modeSuffix = mode === "per_game" ? "/g" : " tot";
  const visible = filtered.slice(0, visibleCount);
  const filtersActive =
    search.trim() !== "" || teamAbbr !== "all" || position !== "all" || minGames > 0;

  if (isLoading) return <ExplorerSkeleton />;

  if (error) {
    return (
      <div className="space-y-5">
        <ExplorerHeader count={null} season={SEASON} />
        <ErrorState message={(error as Error).message} />
      </div>
    );
  }

  if (!data || !data.available) {
    return (
      <div className="space-y-5">
        <ExplorerHeader count={null} season={SEASON} />
        <EmptyState
          title="No season totals imported"
          hint={
            data?.note ??
            "No season-totals file has been imported for this season, so there is nothing to explore yet."
          }
          action={
            <Link
              href="/data-health"
              className="inline-flex items-center justify-center rounded-md bg-brand px-4 py-2 text-sm font-semibold text-court transition-[filter] hover:brightness-110"
            >
              See what&apos;s missing
            </Link>
          }
        />
      </div>
    );
  }

  return (
    <div className="space-y-5 pb-24">
      <ExplorerHeader count={data.count} season={data.season} />

      <div className="grid gap-4 lg:grid-cols-[236px_minmax(0,1fr)] xl:grid-cols-[248px_minmax(0,1fr)]">
        {/* ------------------------------------------------------- filter rail */}
        <aside className="space-y-3 lg:sticky lg:top-[76px] lg:self-start">
          <Panel title="Filters" accent="var(--signal)">
            <div className="space-y-3.5">
              <Field label="Search" htmlFor="explorer-search">
                <input
                  id="explorer-search"
                  type="search"
                  placeholder="Player name…"
                  value={search}
                  onChange={(event) => {
                    setSearch(event.target.value);
                    setVisibleCount(PAGE_SIZE);
                  }}
                  className="w-full rounded-md border border-line bg-panel2 px-2.5 py-1.5 text-sm text-foreground placeholder:text-faint focus:border-signal/60"
                />
              </Field>

              <Field label="Team" htmlFor="explorer-team">
                <select
                  id="explorer-team"
                  value={teamAbbr}
                  onChange={(event) => {
                    setTeamAbbr(event.target.value);
                    setVisibleCount(PAGE_SIZE);
                  }}
                  className="w-full rounded-md border border-line bg-panel2 px-2.5 py-1.5 text-sm text-foreground focus:border-signal/60"
                >
                  <option value="all">All teams</option>
                  {(teams ?? []).map((team) => (
                    <option key={team.id} value={team.abbreviation}>
                      {team.abbreviation} — {team.full_name}
                    </option>
                  ))}
                </select>
              </Field>

              <Field label="Position group" htmlFor="explorer-position">
                <select
                  id="explorer-position"
                  value={position}
                  onChange={(event) => {
                    setPosition(event.target.value as PositionGroup);
                    setVisibleCount(PAGE_SIZE);
                  }}
                  className="w-full rounded-md border border-line bg-panel2 px-2.5 py-1.5 text-sm text-foreground focus:border-signal/60"
                >
                  <option value="all">All positions</option>
                  <option value="Guards">Guards</option>
                  <option value="Wings">Wings</option>
                  <option value="Bigs">Bigs</option>
                </select>
              </Field>

              <Field label="Minimum games" htmlFor="explorer-min-games">
                <select
                  id="explorer-min-games"
                  value={String(minGames)}
                  onChange={(event) => {
                    setMinGames(Number(event.target.value));
                    setVisibleCount(PAGE_SIZE);
                  }}
                  className="w-full rounded-md border border-line bg-panel2 px-2.5 py-1.5 text-sm text-foreground focus:border-signal/60"
                >
                  <option value="0">All players</option>
                  <option value="5">5+ games</option>
                  <option value="15">15+ games</option>
                  <option value="30">30+ games</option>
                  <option value="58">58+ games (league-leader rule)</option>
                </select>
              </Field>

              <Field label="Sort by" htmlFor="explorer-sort">
                <div className="flex gap-1.5">
                  <select
                    id="explorer-sort"
                    value={sortKey}
                    onChange={(event) => {
                      setSortKey(event.target.value);
                      setSortDir("desc");
                    }}
                    className="min-w-0 flex-1 rounded-md border border-line bg-panel2 px-2.5 py-1.5 text-sm text-foreground focus:border-signal/60"
                  >
                    {ALL_COLUMNS.map((column) => (
                      <option key={column.key} value={column.key}>
                        {column.label}
                        {column.kind === "counting" ? modeSuffix : ""}
                      </option>
                    ))}
                  </select>
                  <button
                    type="button"
                    onClick={() => setSortDir((d) => (d === "desc" ? "asc" : "desc"))}
                    aria-label={`Sort direction: ${sortDir === "desc" ? "high to low" : "low to high"}`}
                    title={sortDir === "desc" ? "High → low" : "Low → high"}
                    className="shrink-0 rounded-md border border-line bg-panel2 px-2.5 text-sm text-muted transition-colors hover:border-signal/50 hover:text-foreground"
                  >
                    <span aria-hidden>{sortDir === "desc" ? "↓" : "↑"}</span>
                  </button>
                </div>
              </Field>

              {filtersActive && (
                <Button variant="ghost" size="sm" className="w-full" onClick={resetFilters}>
                  Reset filters
                </Button>
              )}
            </div>
          </Panel>

          <Panel title="Scale">
            <SegmentedControl
              ariaLabel="Stat display scale"
              value={mode}
              onChange={(value) => setMode(value as Mode)}
              options={[
                { value: "per_game", label: "Per game" },
                { value: "totals", label: "Season totals" },
              ]}
            />
            <p className="mt-2.5 text-[11px] leading-relaxed text-muted">
              {mode === "per_game" ? (
                <>
                  Showing <span className="text-foreground">per-game values</span>, derived by
                  dividing raw season totals by games played.
                </>
              ) : (
                <>
                  Showing <span className="text-foreground">raw season totals</span> exactly as
                  imported.
                </>
              )}{" "}
              The two scales are never mixed in one view. Shooting percentages are
              scale-independent and show the same value in both.
            </p>
          </Panel>

          <Panel title="Comparison">
            <p className="text-[11px] leading-relaxed text-muted">
              Tick up to {COMPARE_MAX} players to line their seasons up side by side. The comparison
              always uses the per-game line so the scales stay honest.
            </p>
            <div className="mt-2.5 flex items-center gap-2">
              <Badge status={selected.length >= COMPARE_MIN ? "info" : "unavailable"}>
                {selected.length} of {COMPARE_MAX} picked
              </Badge>
              {selected.length >= COMPARE_MIN && !compareOpen && (
                <Button size="sm" variant="signal" onClick={() => setCompareOpen(true)}>
                  Compare
                </Button>
              )}
            </div>
          </Panel>
        </aside>

        {/* ---------------------------------------------------------- results */}
        <div className="min-w-0 space-y-3">
          {compareOpen && selectedPlayers.length >= COMPARE_MIN && (
            <ComparePanel players={selectedPlayers} onClose={() => setCompareOpen(false)} />
          )}

          <Panel padded={false}>
            <header className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1 border-b border-hairline px-4 py-3">
              <div className="min-w-0">
                <h2 className="title-md whitespace-nowrap text-foreground">
                  Player directory · {data.season}
                </h2>
                <p className="mt-1 text-[11px] text-muted">
                  {filtered.length.toLocaleString()} of {data.count.toLocaleString()} imported
                  players · sorted by {sortColumn.label}
                  {sortColumn.kind === "counting" ? modeSuffix : ""} (
                  {sortDir === "desc" ? "high → low" : "low → high"})
                  {belowQualifier > 0 && (
                    <>
                      {" · "}
                      <span className="text-faint">
                        {belowQualifier.toLocaleString()} listed without a percentile (under{" "}
                        {QUALIFY_MIN} {sortColumn.kind === "rate" ? "attempts" : "games"})
                      </span>
                    </>
                  )}
                </p>
              </div>
              <span className="eyebrow text-right">
                bar = percentile among the {leagueValues.length.toLocaleString()} players with{" "}
                {QUALIFY_MIN}+ {sortColumn.kind === "rate" ? "attempts" : "games"}
              </span>
            </header>

            <div className="p-3">
              {filtered.length === 0 ? (
                <EmptyState
                  title="No players match those filters"
                  hint="Widen the search, clear the team filter, or switch the position group."
                  action={
                    <Button size="sm" onClick={resetFilters}>
                      Reset filters
                    </Button>
                  }
                />
              ) : (
                <>
                  <ColumnRail sortKey={sortKey} sortDir={sortDir} onSort={setSort} mode={mode} />
                  <ul className="space-y-1.5">
                    {visible.map((player, index) => (
                      <PlayerRow
                        key={player.player_id}
                        player={player}
                        rank={index + 1}
                        mode={mode}
                        sortKey={sortKey}
                        percentile={(() => {
                          if (!qualifies(player, sortColumn)) return null;
                          const value = statValue(player, sortColumn, mode);
                          return value === null ? null : percentileOf(leagueValues, value);
                        })()}
                        qualified={qualifies(player, sortColumn)}
                        qualifierLabel={
                          sortColumn.kind === "rate"
                            ? `${QUALIFY_MIN} attempts`
                            : `${QUALIFY_MIN} games`
                        }
                        selected={selected.includes(player.player_id)}
                        selectionFull={selected.length >= COMPARE_MAX}
                        onToggle={() => toggleSelected(player.player_id)}
                      />
                    ))}
                  </ul>

                  {filtered.length > visibleCount && (
                    <div className="mt-3 flex justify-center">
                      <Button onClick={() => setVisibleCount((count) => count + PAGE_SIZE * 3)}>
                        Show more · {(filtered.length - visibleCount).toLocaleString()} remaining
                      </Button>
                    </div>
                  )}
                </>
              )}

              <SourceRail
                source={data.source}
                retrievedAt={data.imported_at}
                extra={
                  <span>
                    · totals are raw as imported; per-game values are derived (totals ÷ GP)
                  </span>
                }
              />
            </div>
          </Panel>
        </div>
      </div>

      {/* --------------------------------------------------- selection tray */}
      {selected.length > 0 && (
        <div className="fixed inset-x-0 bottom-0 z-40 border-t border-hairline bg-court/95 backdrop-blur">
          <div className="mx-auto flex max-w-[1600px] flex-wrap items-center gap-3 px-4 py-2.5 lg:px-8">
            <div className="flex min-w-0 items-center gap-2" aria-live="polite">
              <span className="flex shrink-0 items-center gap-1.5">
                {selectedPlayers.map((player) => (
                  <PlayerPhoto
                    key={player.player_id}
                    nbaPlayerId={player.nba_player_id}
                    name={player.name}
                    size={28}
                  />
                ))}
              </span>
              <span className="min-w-0 truncate text-xs text-muted">
                {selected.length} of {COMPARE_MAX} selected
                {selected.length < COMPARE_MIN ? " — pick at least 2 to compare" : ""}
              </span>
            </div>
            <div className="ml-auto flex shrink-0 items-center gap-2">
              <Button size="sm" variant="ghost" onClick={clearSelection}>
                Clear
              </Button>
              <Button
                size="sm"
                variant="signal"
                disabled={selected.length < COMPARE_MIN}
                onClick={() => setCompareOpen(true)}
              >
                Compare {selected.length}
              </Button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

/* ------------------------------------------------------------------ header */

function ExplorerHeader({ count, season }: { count: number | null; season: string }) {
  return (
    <PageHeader
      eyebrow="Research"
      title="Player Explorer"
      lede="Every imported player line for the season — searchable, sortable, and set against the rest of the league. Pick two to four names to put their seasons side by side."
      meta={
        <>
          <Badge status="info">{season}</Badge>
          {count !== null && <span className="eyebrow">{count.toLocaleString()} players loaded</span>}
          {/* R7: "league percentiles from this same set" used to sit here and is now
              false — the percentile population is the qualified subset, not everyone
              loaded. It also said in a page header what the directory header says with
              the live count in it, so it is deleted rather than reworded. */}
        </>
      }
    />
  );
}

function Field({
  label,
  htmlFor,
  children,
}: {
  label: string;
  htmlFor: string;
  children: React.ReactNode;
}) {
  return (
    <div>
      <label htmlFor={htmlFor} className="eyebrow mb-1.5 block text-[0.5625rem]">
        {label}
      </label>
      {children}
    </div>
  );
}

/* -------------------------------------------------------------- directory */

/** Column headings for the wide layout; each one is also the sort control. */
function ColumnRail({
  sortKey,
  sortDir,
  onSort,
  mode,
}: {
  sortKey: string;
  sortDir: "desc" | "asc";
  onSort: (key: string) => void;
  mode: Mode;
}) {
  const suffix = mode === "per_game" ? "/g" : "";
  return (
    // Sticky so the column meaning survives a 573-row scroll; the nav is 56px tall.
    <div className="mb-1.5 hidden items-center gap-3 rounded-md bg-panel2/95 px-3 py-1.5 backdrop-blur xl:sticky xl:top-[56px] xl:z-10 xl:flex">
      <span className="w-4 shrink-0" aria-hidden />
      <span className="w-6 shrink-0" aria-hidden />
      <span className="eyebrow min-w-0 flex-1 text-[0.5625rem] xl:max-w-[340px]">Player</span>
      <span className="flex flex-1 items-center gap-x-2.5">
        <span className="eyebrow flex-1 text-right text-[0.5625rem]">GP</span>
        {ALL_COLUMNS.map((column) => {
          const active = column.key === sortKey;
          return (
            <button
              key={column.key}
              type="button"
              onClick={() => onSort(column.key)}
              aria-label={`Sort by ${column.label}${
                column.kind === "counting"
                  ? mode === "per_game"
                    ? " per game"
                    : " season total"
                  : ""
              }`}
              className={`eyebrow flex-1 whitespace-nowrap text-right text-[0.5625rem] transition-colors ${
                active ? "text-signal" : "hover:text-foreground"
              }`}
            >
              {column.label}
              {column.kind === "counting" ? suffix : ""}
              {active ? (sortDir === "desc" ? " ↓" : " ↑") : ""}
            </button>
          );
        })}
      </span>
    </div>
  );
}

function PlayerRow({
  player,
  rank,
  mode,
  sortKey,
  percentile,
  qualified,
  qualifierLabel,
  selected,
  selectionFull,
  onToggle,
}: {
  player: SeasonTotalsPlayer;
  rank: number;
  mode: Mode;
  sortKey: string;
  percentile: number | null;
  /** Whether this player's sample reaches `QUALIFY_MIN` on the sorted column. */
  qualified: boolean;
  qualifierLabel: string;
  selected: boolean;
  selectionFull: boolean;
  onToggle: () => void;
}) {
  const identity = teamIdentity(player.team_abbr);
  return (
    <li
      className={`flex flex-wrap items-center gap-x-3 gap-y-2 rounded-lg border px-3 py-2.5 transition-colors xl:flex-nowrap ${
        selected
          ? "border-signal/55 bg-signal/8"
          : "border-hairline bg-panel hover:border-signal/35 hover:bg-panel2"
      }`}
    >
      <input
        type="checkbox"
        checked={selected}
        disabled={!selected && selectionFull}
        onChange={onToggle}
        aria-label={`Select ${player.name} for comparison`}
        className="h-4 w-4 shrink-0 accent-[var(--signal)] disabled:opacity-30"
      />
      <span className="numeral w-6 shrink-0 text-right text-[13px] leading-none text-faint">
        {rank}
      </span>

      <span className="flex min-w-0 flex-1 items-center gap-2.5 xl:max-w-[340px]">
        <PlayerPhoto nbaPlayerId={player.nba_player_id} name={player.name} size={38} />
        <span className="min-w-0">
          <Link
            href={`/players/${player.player_id}`}
            className="block truncate text-sm font-medium text-foreground transition-colors hover:text-signal"
          >
            {player.name}
          </Link>
          <span className="mt-1 flex items-center gap-1.5">
            {player.team_abbr ? (
              <span
                className="inline-flex items-center gap-1 whitespace-nowrap rounded-full border px-1.5 py-[1px]"
                style={{ borderColor: `${identity.bright}55` }}
              >
                <TeamLogo abbreviation={player.team_abbr} size={13} decorative />
                <span className="numeral text-[11px] leading-none" style={{ color: identity.bright }}>
                  {player.team_abbr}
                </span>
              </span>
            ) : (
              <span className="eyebrow text-[0.5rem]">free agent</span>
            )}
            <span className="eyebrow truncate text-[0.5rem]">{player.position ?? "—"}</span>
          </span>
        </span>
      </span>

      {/* Below xl the stat line drops to its own row inside the card, with each
          figure carrying its own label; from xl it sits inline with the header rail. */}
      <span className="grid w-full grid-cols-5 gap-x-2 gap-y-2 sm:grid-cols-10 xl:flex xl:w-auto xl:flex-1 xl:items-start xl:gap-x-2.5">
        <StatCell label="GP" value={String(player.gp)} />
        {ALL_COLUMNS.map((column) => {
          const value = statValue(player, column, mode);
          const isSorted = column.key === sortKey;
          return (
            <StatCell
              key={column.key}
              label={`${column.label}${column.kind === "counting" && mode === "per_game" ? "/g" : ""}`}
              value={formatStat(value, column, mode)}
              emphasized={isSorted}
              meter={isSorted ? percentile : null}
              // No bar rather than a bar with nothing behind it. The tooltip says which
              // it is, so an absent meter reads as "not enough of a sample" rather than
              // as a rendering failure.
              meterLabel={
                !isSorted
                  ? undefined
                  : percentile !== null
                    ? `${ordinal(percentile)} percentile among qualified players`
                    : qualified
                      ? "no value for this stat"
                      : `fewer than ${qualifierLabel} — too small a sample for a percentile`
              }
            />
          );
        })}
      </span>
    </li>
  );
}

function StatCell({
  label,
  value,
  emphasized = false,
  meter = null,
  meterLabel,
}: {
  label: string;
  value: string;
  emphasized?: boolean;
  meter?: number | null;
  meterLabel?: string;
}) {
  return (
    <span className="block min-w-0 xl:flex-1" title={meterLabel}>
      <span className="eyebrow block text-right text-[0.5rem] xl:hidden">{label}</span>
      <span
        className={`data block text-right text-[13px] leading-none ${
          emphasized ? "font-semibold text-signal" : "text-muted"
        }`}
      >
        {value}
      </span>
      {meter !== null && (
        <MeterBar
          value={meter}
          max={100}
          color="var(--signal)"
          className="mt-1 !h-[3px]"
          label={meterLabel}
        />
      )}
    </span>
  );
}

/* ------------------------------------------------------------- comparison */

function ComparePanel({
  players,
  onClose,
}: {
  players: SeasonTotalsPlayer[];
  onClose: () => void;
}) {
  return (
    <Panel
      accent="var(--signal)"
      title={`Comparing ${players.length} players`}
      subtitle="Per-game line (derived using GP) and shooting percentages · best value in each row is highlighted"
      actions={
        <Button size="sm" variant="ghost" onClick={onClose} aria-label="Close comparison">
          Close
        </Button>
      }
    >
      <div className="scroll-thin overflow-x-auto">
        <table className="w-full min-w-[560px]">
          <caption className="sr-only">
            Per-game and rate comparison for the selected players
          </caption>
          <thead>
            <tr className="border-b border-line">
              <Th className="w-24">Stat</Th>
              {players.map((player) => {
                const identity = teamIdentity(player.team_abbr);
                return (
                  <Th key={player.player_id}>
                    <Link
                      href={`/players/${player.player_id}`}
                      className="flex items-center gap-2 normal-case tracking-normal transition-colors hover:text-signal"
                    >
                      <PlayerPhoto
                        nbaPlayerId={player.nba_player_id}
                        name={player.name}
                        size={34}
                        square
                      />
                      <span className="min-w-0">
                        <span className="block truncate text-[13px] font-semibold text-foreground">
                          {player.name}
                        </span>
                        <span
                          className="block whitespace-nowrap text-[10px]"
                          style={{ color: identity.bright }}
                        >
                          {player.team_abbr ?? "—"} · {player.position ?? "—"} · {player.gp} GP
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
              const values = players.map((player) => row.get(player));
              const present = values.filter((v): v is number => v !== null);
              const best = present.length
                ? row.better === "high"
                  ? Math.max(...present)
                  : Math.min(...present)
                : null;
              return (
                <tr key={row.label} className="border-b border-hairline">
                  <Td className="whitespace-nowrap text-muted">
                    {row.label}
                    {row.better === "low" && (
                      <span className="ml-1 text-[10px] text-faint">(lower better)</span>
                    )}
                  </Td>
                  {players.map((player, index) => {
                    const value = values[index];
                    const isBest = value !== null && best !== null && value === best;
                    return (
                      <Td
                        key={player.player_id}
                        numeric
                        className={
                          isBest ? "bg-legal/10 font-semibold !text-legal" : "text-foreground"
                        }
                      >
                        {value === null ? "—" : row.fmt(value)}
                        {isBest && <span className="sr-only"> — best in this row</span>}
                      </Td>
                    );
                  })}
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </Panel>
  );
}

/* --------------------------------------------------------------- loading */

function ExplorerSkeleton() {
  return (
    <div className="space-y-5" role="status" aria-label="Loading Player Explorer">
      <div className="space-y-3">
        <Skeleton className="h-3 w-24" />
        <Skeleton className="h-9 w-72 max-w-full" />
        <Skeleton className="h-4 w-full max-w-2xl" />
      </div>
      <div className="grid gap-4 lg:grid-cols-[236px_minmax(0,1fr)] xl:grid-cols-[248px_minmax(0,1fr)]">
        <div className="space-y-3">
          <Skeleton className="h-64" />
          <Skeleton className="h-36" />
          <Skeleton className="h-32" />
        </div>
        <div className="space-y-2">
          <Skeleton className="h-14" />
          <SkeletonRows rows={10} height="h-[62px]" />
        </div>
      </div>
    </div>
  );
}
