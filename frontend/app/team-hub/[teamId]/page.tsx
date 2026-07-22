"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { use, useState } from "react";
import { api } from "@/lib/api";
import { COMPONENT_LABEL, NEED_LABEL, height, money, pct, tei } from "@/lib/format";
import { teamTheme, teamThemeVars } from "@/lib/teamTheme";
import type {
  PayrollResponse,
  RosterPlayer,
  RosterResponse,
  Scenario,
  Team,
  TeamNeedItem,
} from "@/lib/types";
import { PlayerPhoto, TeamLogo } from "@/components/media";
import { useToast } from "@/components/toast";
import {
  Badge,
  Card,
  EmptyState,
  ErrorState,
  MeterBar,
  SourceLine,
  Spinner,
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
  ["contend", "Contend now"],
  ["improve", "Improve, keep flexibility"],
  ["retool", "Re-tool around the core"],
  ["rebuild", "Rebuild"],
  ["youth", "Chase young upside"],
  ["cap_relief", "Cut salary / tax"],
] as const;

function positionGroup(position: string | null): "Guards" | "Wings" | "Bigs" {
  // Official position strings (G, G-F, F, F-C, C, …) grouped for scanning;
  // the exact designation stays visible on each row.
  const p = (position ?? "").toUpperCase();
  if (p.includes("C")) return "Bigs";
  if (p.includes("G") && !p.includes("F")) return "Guards";
  return "Wings";
}

function windowLabel(avgAge: number | null): { label: string; hint: string } {
  if (avgAge === null) return { label: "Unknown", hint: "Roster ages unavailable." };
  if (avgAge < 25.5) return { label: "Ascending", hint: "Young core — the window is opening." };
  if (avgAge < 28.5) return { label: "Open now", hint: "Prime-age core — win-now moves fit." };
  return { label: "Closing", hint: "Veteran core — weigh future flexibility carefully." };
}

export default function TeamHubPage({ params }: { params: Promise<{ teamId: string }> }) {
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
    queryFn: () =>
      api.get<{ needs: TeamNeedItem[]; note: string | null }>(`/teams/${teamId}/needs`),
  });
  const { data: payroll } = useQuery({
    queryKey: ["payroll", teamId],
    queryFn: () => api.get<PayrollResponse>(`/teams/${teamId}/payroll`),
  });

  const [strategy, setStrategy] = useState<string>("contend");
  const saveStrategy = useMutation({
    mutationFn: () =>
      api.post<Scenario>("/scenarios", {
        name: `${detail?.team.abbreviation} — ${STRATEGIES.find(([v]) => v === strategy)?.[1]}`,
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
  if (!detail) return <Spinner label="Loading team…" />;

  const theme = teamTheme(detail.team.abbreviation);
  const adv = detail.stats.advanced ?? {};
  const rosterPlayers = roster?.roster ?? [];
  const ages = rosterPlayers.map((p) => p.age).filter((a): a is number => a !== null);
  const topRotation = [...rosterPlayers].sort((a, b) => (b.tei ?? -99) - (a.tei ?? -99)).slice(0, 8);
  const rotationAges = topRotation.map((p) => p.age).filter((a): a is number => a !== null);
  const avgRotationAge = rotationAges.length
    ? rotationAges.reduce((s, a) => s + a, 0) / rotationAges.length
    : null;
  const competitiveWindow = windowLabel(avgRotationAge);

  const sortedNeeds = needs?.needs ?? [];
  const weaknesses = sortedNeeds.filter((n) => n.severity >= 0.35).slice(0, 4);
  const strengths = sortedNeeds
    .filter((n) => n.severity === 0 && n.percentile !== null && (n.percentile ?? 0) >= 65)
    .slice(0, 4);

  const groups: Record<string, RosterPlayer[]> = { Guards: [], Wings: [], Bigs: [] };
  for (const player of rosterPlayers) groups[positionGroup(player.position)].push(player);
  for (const key of Object.keys(groups))
    groups[key].sort((a, b) => (b.tei ?? -99) - (a.tei ?? -99));

  return (
    <div className="space-y-4" style={teamThemeVars(detail.team.abbreviation)}>
      {/* Team header with color treatment */}
      <section
        className="relative overflow-hidden rounded-xl border border-line p-5"
        style={{
          background: `linear-gradient(115deg, ${theme.primary}33 0%, var(--panel) 55%)`,
          borderColor: `${theme.bright}44`,
        }}
      >
        <div className="flex flex-wrap items-center gap-4">
          <TeamLogo abbreviation={detail.team.abbreviation} name={detail.team.full_name} size={72} />
          <div className="min-w-0 flex-1">
            <h1 className="text-2xl font-bold">{detail.team.full_name}</h1>
            <p className="text-sm text-muted">
              {detail.team.conference} Conference
              {detail.team.division ? ` · ${detail.team.division}` : ""} · season {detail.season}
            </p>
            <div className="mt-1.5 flex flex-wrap gap-2 text-xs">
              <Badge status="info">
                window: {competitiveWindow.label}
              </Badge>
              <span className="text-muted">{competitiveWindow.hint}</span>
            </div>
          </div>
          {detail.standing && (
            <div className="text-right">
              <div className="text-4xl font-bold" style={{ color: theme.bright }}>
                {detail.standing.wins}–{detail.standing.losses}
              </div>
              <div className="text-xs text-muted">
                {pct(detail.standing.win_pct, 1)} · #{detail.standing.playoff_rank ?? "—"} in{" "}
                {detail.standing.conference}
              </div>
            </div>
          )}
          <div className="flex w-full gap-2 pt-1 sm:w-auto sm:flex-col lg:w-auto lg:flex-row">
            <Link
              href={`/trade-machine?team=${teamId}`}
              className="rounded-md bg-brand px-4 py-2 text-center text-sm font-semibold text-background hover:brightness-110"
            >
              Start a trade
            </Link>
            <Link
              href={`/player-lab?team=${teamId}`}
              className="rounded-md border border-line px-4 py-2 text-center text-sm hover:bg-panel2"
            >
              Compare players
            </Link>
            <Link
              href={`/cap-lab?team=${teamId}`}
              className="rounded-md border border-line px-4 py-2 text-center text-sm hover:bg-panel2"
            >
              Open Cap Lab
            </Link>
          </div>
        </div>
      </section>

      <div className="grid gap-4 md:grid-cols-4">
        {[
          ["Offense", adv.OFF_RATING, "points scored per 100 possessions"],
          ["Defense", adv.DEF_RATING, "points allowed per 100 possessions (lower is better)"],
          ["Net rating", adv.NET_RATING, "scoring margin per 100 possessions"],
          ["Avg roster age", ages.length ? ages.reduce((s, a) => s + a, 0) / ages.length : undefined, "simple average of roster ages"],
        ].map(([label, value, hint]) => (
          <div
            key={String(label)}
            className="rounded-lg border border-line bg-panel p-4"
            title={String(hint)}
          >
            <div className="text-xs text-muted">{label}</div>
            <div className="mt-1 text-2xl font-semibold">
              {value !== undefined && value !== null ? Number(value).toFixed(1) : "—"}
            </div>
          </div>
        ))}
      </div>

      <div className="grid gap-4 lg:grid-cols-[1fr_340px]">
        {/* Roster grouped by position */}
        <Card
          title={`Roster (${rosterPlayers.length})`}
          subtitle={
            roster ? (
              <SourceLine retrievedAt={roster.source_retrieved_at} source="NBA.com via nba_api" />
            ) : undefined
          }
        >
          {!roster ? (
            <div className="space-y-2">
              {Array.from({ length: 8 }).map((_, i) => (
                <div key={i} className="skeleton h-11" />
              ))}
            </div>
          ) : (
            <div className="space-y-4">
              {(["Guards", "Wings", "Bigs"] as const).map((group) =>
                groups[group].length === 0 ? null : (
                  <div key={group}>
                    <h3 className="mb-1.5 text-[11px] font-semibold uppercase tracking-wider text-muted">
                      {group}
                    </h3>
                    <ul className="divide-y divide-line/60">
                      {groups[group].map((player) => (
                        <li key={player.player_id}>
                          <Link
                            href={`/players/${player.player_id}`}
                            className="flex items-center gap-3 rounded-md px-1 py-1.5 hover:bg-panel2"
                          >
                            <PlayerPhoto
                              nbaPlayerId={player.nba_player_id}
                              name={player.name}
                              size={34}
                            />
                            <span className="min-w-0 flex-1">
                              <span className="block truncate text-sm">{player.name}</span>
                              <span className="text-[11px] text-muted">
                                {player.position ?? "—"} · age {player.age?.toFixed(0) ?? "—"} ·{" "}
                                {height(player.height_inches)}
                              </span>
                            </span>
                            {player.archetype && (
                              <span className="hidden text-[11px] text-muted md:inline">
                                {player.archetype}
                              </span>
                            )}
                            <span
                              className="w-14 text-right font-mono text-sm"
                              title="Estimated player impact (per-100 index) — see Methodology"
                            >
                              {tei(player.tei)}
                            </span>
                          </Link>
                        </li>
                      ))}
                    </ul>
                  </div>
                ),
              )}
            </div>
          )}
        </Card>

        <div className="space-y-4">
          {/* Strategy */}
          <Card
            title="Choose your team strategy"
            subtitle="Drives how trades are scored for this team"
          >
            <div className="space-y-2">
              {STRATEGIES.map(([value, label]) => (
                <label key={value} className="flex cursor-pointer items-center gap-2 text-sm">
                  <input
                    type="radio"
                    name="strategy"
                    checked={strategy === value}
                    onChange={() => setStrategy(value)}
                    className="accent-orange-500"
                  />
                  {label}
                </label>
              ))}
              <button
                type="button"
                disabled={saveStrategy.isPending}
                onClick={() => saveStrategy.mutate()}
                className="mt-1 w-full rounded-md bg-brand px-3 py-2 text-sm font-semibold text-background hover:brightness-110 disabled:opacity-40"
              >
                {saveStrategy.isPending ? "Saving…" : "Save strategy"}
              </button>
              <p className="text-[11px] text-muted">
                Fine-grained weights and untouchables live in the Trade Machine.{" "}
                <Link href="/methodology#weights" className="underline">
                  How weights work
                </Link>
              </p>
            </div>
          </Card>

          {/* Strengths & weaknesses */}
          <Card
            title="Strengths & weaknesses"
            subtitle="Model-derived from real team stats — not scouting"
          >
            {!needs ? (
              <Spinner />
            ) : sortedNeeds.length === 0 ? (
              <EmptyState title="Not computed yet" hint="Run `make score` on the backend." />
            ) : (
              <div className="space-y-3">
                {strengths.length > 0 && (
                  <div>
                    <h4 className="text-[11px] font-semibold uppercase tracking-wider text-pass">
                      Strengths
                    </h4>
                    <ul className="mt-1 space-y-0.5 text-sm">
                      {strengths.map((n) => (
                        <li key={n.need_key} title={n.explanation}>
                          ✓ {NEED_LABEL[n.need_key] ?? n.need_key}{" "}
                          <span className="text-[11px] text-muted">
                            ({n.percentile?.toFixed(0)}th pct)
                          </span>
                        </li>
                      ))}
                    </ul>
                  </div>
                )}
                <div>
                  <h4 className="text-[11px] font-semibold uppercase tracking-wider text-fail">
                    Needs
                  </h4>
                  <div className="mt-1 space-y-1.5">
                    {(weaknesses.length ? weaknesses : sortedNeeds.slice(0, 4)).map((n) => (
                      <div key={n.need_key} title={n.explanation}>
                        <div className="flex justify-between text-xs">
                          <span>{NEED_LABEL[n.need_key] ?? n.need_key}</span>
                          <span className="text-muted">
                            {n.percentile !== null ? `${n.percentile.toFixed(0)}th pct` : ""}
                          </span>
                        </div>
                        <MeterBar
                          value={n.severity}
                          color={n.severity > 0.5 ? "var(--fail)" : "var(--warn)"}
                          className="mt-0.5"
                        />
                      </div>
                    ))}
                  </div>
                </div>
                <p className="text-[11px] text-muted">
                  Percentile rules over league stats.{" "}
                  <Link href="/methodology#needs" className="underline">
                    How is this calculated?
                  </Link>
                </p>
              </div>
            )}
          </Card>

          {/* Payroll */}
          <Card title="Payroll & cap status">
            {!payroll ? (
              <Spinner />
            ) : payroll.payroll_available ? (
              <div className="space-y-1.5 text-sm">
                <div className="flex justify-between">
                  <span className="text-muted">Payroll ({payroll.league_year})</span>
                  <span className="font-mono">{money(payroll.payroll)}</span>
                </div>
                {payroll.cap_context && (
                  <>
                    <div className="flex justify-between">
                      <span className="text-muted">Luxury-tax line</span>
                      <span className="font-mono">{money(payroll.cap_context.luxury_tax)}</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-muted">Room below tax</span>
                      <span className="font-mono">{money(payroll.cap_context.room_below_tax)}</span>
                    </div>
                  </>
                )}
                <Link href={`/cap-lab?team=${teamId}`} className="text-xs text-brand underline">
                  full picture in Cap Lab →
                </Link>
              </div>
            ) : (
              <UnavailableNotice
                reason={
                  payroll.unavailable_reason ??
                  "Contract data hasn't been imported, so payroll can't be computed."
                }
              />
            )}
          </Card>

          {/* Draft assets: honest state */}
          <Card title="Draft capital">
            <UnavailableNotice reason="Verified draft-pick ownership isn't configured — RosterLab won't guess. Hypothetical picks can still be added inside a trade, clearly labeled." />
          </Card>
        </div>
      </div>
    </div>
  );
}
