"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { use } from "react";
import { api } from "@/lib/api";
import { NEED_LABEL, height, money, pct, tei } from "@/lib/format";
import type { PayrollResponse, RosterResponse, Team, TeamNeedItem } from "@/lib/types";
import {
  Badge,
  Card,
  EmptyState,
  ErrorState,
  MeterBar,
  PlayerAvatar,
  SourceLine,
  Spinner,
  Td,
  Th,
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

export default function TeamPage({ params }: { params: Promise<{ teamId: string }> }) {
  const { teamId } = use(params);
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

  if (error) return <ErrorState message={`Could not load team: ${String(error)}`} />;
  if (!detail) return <Spinner label="Loading team…" />;

  const adv = detail.stats.advanced ?? {};
  const base = detail.stats.base ?? {};

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold">{detail.team.full_name}</h1>
          <p className="text-sm text-muted">
            {detail.team.conference} Conference{detail.team.division ? ` · ${detail.team.division}` : ""} ·
            season {detail.season}
          </p>
        </div>
        {detail.standing && (
          <div className="text-right">
            <div className="text-3xl font-bold">
              {detail.standing.wins}–{detail.standing.losses}
            </div>
            <div className="text-xs text-muted">
              {pct(detail.standing.win_pct, 1)} · #{detail.standing.playoff_rank ?? "—"} in{" "}
              {detail.standing.conference}
            </div>
          </div>
        )}
      </div>

      <div className="grid gap-4 md:grid-cols-4">
        {[
          ["Off. rating", adv.OFF_RATING, ""],
          ["Def. rating", adv.DEF_RATING, ""],
          ["Net rating", adv.NET_RATING, ""],
          ["Pace", adv.PACE, ""],
        ].map(([label, value]) => (
          <div key={String(label)} className="rounded-lg border border-line bg-panel p-4">
            <div className="text-xs text-muted">{label}</div>
            <div className="mt-1 text-2xl font-semibold">
              {value !== undefined ? Number(value).toFixed(1) : "—"}
            </div>
          </div>
        ))}
      </div>
      <SourceLine retrievedAt={detail.stats_retrieved_at} />

      <div className="grid gap-4 lg:grid-cols-[1fr_360px]">
        <Card
          title={`Roster (${roster?.roster.length ?? "…"})`}
          subtitle={roster && <SourceLine retrievedAt={roster.source_retrieved_at} source={roster.source} />}
        >
          {!roster ? (
            <Spinner />
          ) : (
            <div className="scroll-thin overflow-x-auto">
              <table className="w-full min-w-[640px]">
                <thead>
                  <tr className="border-b border-line">
                    <Th>Player</Th>
                    <Th>Pos</Th>
                    <Th>Age</Th>
                    <Th>Ht</Th>
                    <Th>Exp</Th>
                    <Th className="text-right">TEI</Th>
                    <Th>Archetype</Th>
                    <Th className="text-right">Avail.</Th>
                  </tr>
                </thead>
                <tbody>
                  {roster.roster
                    .slice()
                    .sort((a, b) => (b.tei ?? -99) - (a.tei ?? -99))
                    .map((p) => (
                      <tr key={p.player_id} className="border-b border-line/50 hover:bg-panel2">
                        <Td>
                          <Link
                            href={`/players/${p.player_id}`}
                            className="flex items-center gap-2 hover:text-accent"
                          >
                            <PlayerAvatar name={p.name} size={26} />
                            {p.name}
                          </Link>
                        </Td>
                        <Td>{p.position ?? "—"}</Td>
                        <Td>{p.age?.toFixed(0) ?? "—"}</Td>
                        <Td>{height(p.height_inches)}</Td>
                        <Td>{p.years_experience ?? "—"}</Td>
                        <Td className="text-right font-mono">{tei(p.tei)}</Td>
                        <Td className="text-xs text-muted">{p.archetype ?? "—"}</Td>
                        <Td className="text-right font-mono">{pct(p.availability)}</Td>
                      </tr>
                    ))}
                </tbody>
              </table>
            </div>
          )}
        </Card>

        <div className="space-y-4">
          <Card title="Needs profile">
            {!needs ? (
              <Spinner />
            ) : needs.needs.length === 0 ? (
              <EmptyState title="Not computed" hint={needs.note ?? undefined} />
            ) : (
              <div className="space-y-2">
                {needs.needs.slice(0, 8).map((n) => (
                  <div key={n.need_key} title={n.explanation}>
                    <div className="flex justify-between text-xs">
                      <span>{NEED_LABEL[n.need_key] ?? n.need_key}</span>
                      <span className="text-muted">
                        {n.percentile ? `${n.percentile.toFixed(0)}th pct` : ""}
                      </span>
                    </div>
                    <MeterBar
                      value={n.severity}
                      color={n.severity > 0.5 ? "var(--fail)" : n.severity > 0.25 ? "var(--warn)" : "var(--pass)"}
                      className="mt-1"
                    />
                  </div>
                ))}
              </div>
            )}
          </Card>

          <Card title="Payroll & cap status" subtitle={payroll ? `league year ${payroll.league_year}` : undefined}>
            {!payroll ? (
              <Spinner />
            ) : payroll.payroll_available ? (
              <div className="space-y-2 text-sm">
                <div className="flex justify-between">
                  <span className="text-muted">Team payroll</span>
                  <span className="font-mono">{money(payroll.payroll)}</span>
                </div>
                {payroll.cap_context && (
                  <>
                    <div className="flex justify-between">
                      <span className="text-muted">Luxury tax line</span>
                      <span className="font-mono">{money(payroll.cap_context.luxury_tax)}</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-muted">Room below tax</span>
                      <span className="font-mono">{money(payroll.cap_context.room_below_tax)}</span>
                    </div>
                    <p className="text-[11px] text-muted">Cap source: {payroll.cap_context.cap_source}</p>
                  </>
                )}
              </div>
            ) : (
              <UnavailableNotice reason={payroll.unavailable_reason ?? "Contract data unavailable."} />
            )}
          </Card>

          {detail.standing?.details && (
            <Card title="Season detail">
              <dl className="grid grid-cols-2 gap-2 text-sm">
                {Object.entries(detail.standing.details).map(([key, value]) => (
                  <div key={key}>
                    <dt className="text-[11px] uppercase tracking-wide text-muted">{key}</dt>
                    <dd className="font-mono">{String(value ?? "—")}</dd>
                  </div>
                ))}
              </dl>
              <SourceLine className="mt-3" retrievedAt={detail.standing.source_retrieved_at} />
            </Card>
          )}

          <div className="text-xs text-muted">
            <Badge status="info">PPG {base.PTS !== undefined ? Number(base.PTS).toFixed(1) : "—"}</Badge>{" "}
            <Badge status="info">3PA {base.FG3A !== undefined ? Number(base.FG3A).toFixed(1) : "—"}</Badge>{" "}
            <Badge status="info">TS% {adv.TS_PCT !== undefined ? pct(Number(adv.TS_PCT), 1) : "—"}</Badge>{" "}
            · <Link href="/data-health" className="underline">data health</Link>
          </div>
        </div>
      </div>
    </div>
  );
}
