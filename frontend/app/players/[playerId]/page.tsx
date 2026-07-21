"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { use, useState } from "react";
import { api } from "@/lib/api";
import { formatDate, height, money, pct, tei } from "@/lib/format";
import type { Team } from "@/lib/types";
import {
  Badge,
  Card,
  ErrorState,
  PlayerAvatar,
  SourceLine,
  Spinner,
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
  comparables: { player_id: string; name: string; tei: number; archetype: string }[];
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
  years?: { season: string; salary: number; player_option: boolean | null; team_option: boolean | null }[];
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
  if (!data) return <Spinner label="Loading player…" />;

  const p = data.player;
  const age = p.birth_date
    ? Math.floor((now - new Date(p.birth_date).getTime()) / (365.25 * 24 * 3600 * 1000))
    : null;

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-4">
        <PlayerAvatar name={p.full_name} size={56} />
        <div>
          <h1 className="text-2xl font-bold">{p.full_name}</h1>
          <p className="text-sm text-muted">
            {p.position ?? "—"} · {height(p.height_inches)} · {p.weight_lbs ?? "—"} lbs · age{" "}
            {age ?? "—"} · {p.years_experience ?? "—"} yrs exp
            {p.current_team && (
              <>
                {" · "}
                <Link className="text-accent underline" href={`/teams/${p.current_team.id}`}>
                  {p.current_team.full_name}
                </Link>
              </>
            )}
          </p>
          <SourceLine className="mt-1" retrievedAt={p.provenance?.source_retrieved_at} />
        </div>
        <div className="ml-auto flex gap-2">
          {data.archetype && <Badge status="info">{data.archetype.label}</Badge>}
          {!p.is_active && <Badge status="unavailable">not active</Badge>}
        </div>
      </div>

      <div className="grid gap-4 md:grid-cols-3">
        <Card title="TradeLab Estimated Impact" subtitle={data.impact.model ?? undefined}>
          {data.impact.tei !== undefined ? (
            <div>
              <div className="text-4xl font-bold">{tei(data.impact.tei)}</div>
              <div className="mt-1 text-xs text-muted">
                10th–90th pct: {data.impact.tei_range_10_90 ? `${tei(data.impact.tei_range_10_90[0])} to ${tei(data.impact.tei_range_10_90[1])}` : "—"}
              </div>
              <div className="mt-3 grid grid-cols-2 gap-2 text-sm">
                <div>
                  <div className="text-[11px] text-muted">Offense</div>
                  <div className="font-mono">{tei(data.impact.tei_offense)}</div>
                </div>
                <div>
                  <div className="text-[11px] text-muted">Defense</div>
                  <div className="font-mono">{tei(data.impact.tei_defense)}</div>
                </div>
                <div>
                  <div className="text-[11px] text-muted">Availability (hist.)</div>
                  <div className="font-mono">{pct(data.impact.availability)}</div>
                </div>
                <div>
                  <div className="text-[11px] text-muted">Minutes est.</div>
                  <div className="font-mono">{data.impact.minutes_estimate?.toFixed(1) ?? "—"}</div>
                </div>
              </div>
              <p className="mt-3 text-[11px] text-muted">{data.impact.note}</p>
            </div>
          ) : (
            <UnavailableNotice reason={data.impact.note} />
          )}
        </Card>

        <Card title="Contract">
          {!contract ? (
            <Spinner />
          ) : contract.available ? (
            <div className="space-y-2 text-sm">
              <div className="flex items-center gap-2">
                <Badge status="info">{contract.contract_type}</Badge>
                {contract.no_trade_clause && <Badge status="warning">no-trade clause</Badge>}
              </div>
              <table className="w-full">
                <thead>
                  <tr>
                    <Th>Season</Th>
                    <Th className="text-right">Salary</Th>
                    <Th>Options</Th>
                  </tr>
                </thead>
                <tbody>
                  {contract.years?.map((y) => (
                    <tr key={y.season} className="border-t border-line/50">
                      <Td>{y.season}</Td>
                      <Td className="text-right font-mono">{money(y.salary)}</Td>
                      <Td className="text-xs text-muted">
                        {y.player_option ? "PO" : y.team_option ? "TO" : "—"}
                      </Td>
                    </tr>
                  ))}
                </tbody>
              </table>
              <p className="text-[11px] text-muted">
                Source: {contract.source_name} ({formatDate(contract.source_date)}). {contract.note}
              </p>
            </div>
          ) : (
            <UnavailableNotice reason={contract.reason ?? "Contract data unavailable."} />
          )}
        </Card>

        <Card title="Comparable players" subtitle="same archetype cluster, nearest TEI">
          {data.comparables.length === 0 ? (
            <p className="text-sm text-muted">No comparables (archetype not assigned).</p>
          ) : (
            <ul className="space-y-1.5">
              {data.comparables.map((c) => (
                <li key={c.player_id} className="flex items-center justify-between text-sm">
                  <Link href={`/players/${c.player_id}`} className="hover:text-accent">
                    {c.name}
                  </Link>
                  <span className="font-mono text-muted">{tei(c.tei)}</span>
                </li>
              ))}
            </ul>
          )}
        </Card>
      </div>

      <Card title="Recent seasons" subtitle={stats?.source}>
        {!stats ? (
          <Spinner />
        ) : (
          <div className="scroll-thin overflow-x-auto">
            <table className="w-full min-w-[720px]">
              <thead>
                <tr className="border-b border-line">
                  <Th>Season</Th>
                  <Th className="text-right">GP</Th>
                  <Th className="text-right">MIN</Th>
                  <Th className="text-right">PTS</Th>
                  <Th className="text-right">REB</Th>
                  <Th className="text-right">AST</Th>
                  <Th className="text-right">TS%</Th>
                  <Th className="text-right">USG%</Th>
                  <Th className="text-right">Net rtg</Th>
                </tr>
              </thead>
              <tbody>
                {stats.seasons.map((s) => (
                  <tr key={s.season} className="border-b border-line/50">
                    <Td>{s.season}</Td>
                    <Td className="text-right font-mono">{s.base?.GP ?? "—"}</Td>
                    <Td className="text-right font-mono">{s.base?.MIN?.toFixed(1) ?? "—"}</Td>
                    <Td className="text-right font-mono">{s.base?.PTS?.toFixed(1) ?? "—"}</Td>
                    <Td className="text-right font-mono">{s.base?.REB?.toFixed(1) ?? "—"}</Td>
                    <Td className="text-right font-mono">{s.base?.AST?.toFixed(1) ?? "—"}</Td>
                    <Td className="text-right font-mono">
                      {s.advanced?.TS_PCT !== undefined ? pct(s.advanced.TS_PCT, 1) : "—"}
                    </Td>
                    <Td className="text-right font-mono">
                      {s.advanced?.USG_PCT !== undefined ? pct(s.advanced.USG_PCT, 1) : "—"}
                    </Td>
                    <Td className="text-right font-mono">
                      {s.advanced?.NET_RATING?.toFixed(1) ?? "—"}
                    </Td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>
    </div>
  );
}
