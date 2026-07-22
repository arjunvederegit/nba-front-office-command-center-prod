"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { formatDate } from "@/lib/format";
import { getFavoriteTeam, setFavoriteTeam, teamTheme } from "@/lib/teamTheme";
import type { DataHealth, Scenario, Team, TradeSummary } from "@/lib/types";
import { CourtLines } from "@/components/brand";
import { TeamLogo } from "@/components/media";
import { Badge } from "@/components/ui";
import { useToast } from "@/components/toast";

const TOOLS: {
  title: string;
  href: string | null;
  status: "available" | "partial" | "soon";
  body: string;
}[] = [
  { title: "Trade Machine", href: "/trade-machine", status: "available",
    body: "Build 2–3 team trades with live rules checks, projections and risk analysis." },
  { title: "Team Hub", href: "/team-hub", status: "available",
    body: "Roster, strengths & weaknesses, needs and competitive window for all 30 teams." },
  { title: "Compare Deals", href: "/compare", status: "available",
    body: "Stack saved deals side by side, with tradeoffs and rank stability — not just a winner." },
  { title: "Player Lab", href: "/player-lab", status: "available",
    body: "Explore every rostered player: photos, season totals, per-game stats, impact and comps." },
  { title: "Cap Lab", href: "/cap-lab", status: "partial",
    body: "Payroll by season, expiring money and cap position — activates fully once contract data is imported." },
  { title: "Salary Predictor", href: null, status: "soon",
    body: "Market-value modeling needs historical contract data before we'll ship it. No fake numbers." },
];

export default function HomePage() {
  const toast = useToast();
  const { data: teams } = useQuery({ queryKey: ["teams"], queryFn: () => api.get<Team[]>("/teams") });
  const { data: health } = useQuery({
    queryKey: ["data-health"],
    queryFn: () => api.get<DataHealth>("/data-health"),
  });
  const { data: trades } = useQuery({
    queryKey: ["trades"],
    queryFn: () => api.get<TradeSummary[]>("/trades"),
  });
  const { data: scenarios } = useQuery({
    queryKey: ["scenarios"],
    queryFn: () => api.get<Scenario[]>("/scenarios"),
  });

  const [favorite, setFavorite] = useState<{ id: string; abbreviation: string } | null>(null);
  useEffect(() => {
    setFavorite(getFavoriteTeam());
  }, []);

  function pickFavorite(team: Team) {
    const value = { id: team.id, abbreviation: team.abbreviation };
    setFavoriteTeam(value);
    setFavorite(value);
    toast("success", `${team.full_name} set as your team.`);
  }

  const favoriteTheme = teamTheme(favorite?.abbreviation);

  return (
    <div className="space-y-8">
      {/* Hero */}
      <section
        className="relative overflow-hidden rounded-2xl border border-line bg-panel"
        style={{
          background: `linear-gradient(120deg, var(--panel) 55%, ${favoriteTheme.primary}22 100%)`,
        }}
      >
        <CourtLines className="pointer-events-none absolute bottom-0 right-0 h-48 w-[420px] text-line" />
        <div className="relative grid gap-6 p-8 md:grid-cols-[1fr_300px] md:p-10">
          <div>
            <h1 className="max-w-xl text-3xl font-bold tracking-tight md:text-4xl">
              Run your front office.{" "}
              <span className="text-brand">Real data, honest rules, explainable calls.</span>
            </h1>
            <p className="mt-3 max-w-xl text-sm leading-relaxed text-muted">
              RosterLab is an NBA front-office simulator: construct trades against live rosters,
              get an instant trade-rules check, and see projected impact with uncertainty — every
              number traceable to its source.
            </p>
            <div className="mt-5 flex flex-wrap gap-3">
              <Link
                href={favorite ? `/trade-machine?team=${favorite.id}` : "/trade-machine"}
                className="rounded-md bg-brand px-5 py-2.5 text-sm font-semibold text-background transition hover:brightness-110"
              >
                Start a trade
              </Link>
              <Link
                href="/team-hub"
                className="rounded-md border border-line px-5 py-2.5 text-sm transition hover:bg-panel2"
              >
                Choose your team
              </Link>
            </div>
            {health && (
              <div className="mt-5 flex flex-wrap items-center gap-2 text-xs">
                <Badge status={health.last_successful_sync ? "pass" : "unavailable"}>
                  {health.last_successful_sync
                    ? `NBA data synced ${formatDate(health.last_successful_sync)}`
                    : "no data synced yet"}
                </Badge>
                <Badge status="info">season {health.current_season}</Badge>
                <Badge status={health.providers.contracts?.configured ? "pass" : "unavailable"}>
                  contracts {health.providers.contracts?.configured ? "imported" : "not imported"}
                </Badge>
                <Link href="/data-status" className="text-muted underline hover:text-foreground">
                  data status →
                </Link>
              </div>
            )}
          </div>
          {favorite && teams && (
            <FavoriteCard
              team={teams.find((t) => t.id === favorite.id)}
              onClear={() => {
                setFavoriteTeam(null);
                setFavorite(null);
              }}
            />
          )}
        </div>
      </section>

      {/* Team picker grid */}
      <section>
        <div className="mb-3 flex items-baseline justify-between">
          <h2 className="text-lg font-semibold">Pick your team</h2>
          <p className="text-xs text-muted">Sets your default across the whole product</p>
        </div>
        {!teams ? (
          <div className="grid grid-cols-5 gap-2 md:grid-cols-10">
            {Array.from({ length: 30 }).map((_, i) => (
              <div key={i} className="skeleton h-20" />
            ))}
          </div>
        ) : (
          <div className="grid grid-cols-3 gap-2 sm:grid-cols-5 md:grid-cols-6 lg:grid-cols-10">
            {teams.map((team) => {
              const theme = teamTheme(team.abbreviation);
              const isFavorite = favorite?.id === team.id;
              return (
                <button
                  key={team.id}
                  type="button"
                  onClick={() => pickFavorite(team)}
                  aria-pressed={isFavorite}
                  title={`${team.full_name} — set as your team`}
                  className={`group flex flex-col items-center gap-1.5 rounded-lg border p-2.5 transition ${
                    isFavorite
                      ? "border-brand bg-panel2"
                      : "border-line bg-panel hover:border-line hover:bg-panel2"
                  }`}
                  style={isFavorite ? { borderColor: theme.bright } : undefined}
                >
                  <TeamLogo abbreviation={team.abbreviation} name={team.full_name} size={38} />
                  <span className="text-[11px] font-semibold" style={{ color: theme.bright }}>
                    {team.abbreviation}
                  </span>
                </button>
              );
            })}
          </div>
        )}
      </section>

      {/* Tool suite */}
      <section>
        <h2 className="mb-3 text-lg font-semibold">Front-office tools</h2>
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {TOOLS.map((tool) => {
            const inner = (
              <div
                className={`h-full rounded-lg border p-4 transition ${
                  tool.href
                    ? "border-line bg-panel hover:border-brand/50 hover:bg-panel2"
                    : "border-dashed border-line bg-panel/60"
                }`}
              >
                <div className="flex items-center justify-between">
                  <h3 className="font-semibold">{tool.title}</h3>
                  {tool.status === "available" && <Badge status="pass">available</Badge>}
                  {tool.status === "partial" && <Badge status="warning">needs data import</Badge>}
                  {tool.status === "soon" && <Badge status="unavailable">coming soon</Badge>}
                </div>
                <p className="mt-2 text-sm leading-relaxed text-muted">{tool.body}</p>
              </div>
            );
            return tool.href ? (
              <Link key={tool.title} href={tool.href}>
                {inner}
              </Link>
            ) : (
              <div key={tool.title}>{inner}</div>
            );
          })}
        </div>
      </section>

      {/* Recent activity */}
      <section className="grid gap-4 lg:grid-cols-2">
        <div className="rounded-lg border border-line bg-panel p-4">
          <div className="mb-2 flex items-baseline justify-between">
            <h2 className="font-semibold">Recent saved deals</h2>
            <Link href="/compare" className="text-xs text-brand underline">
              compare →
            </Link>
          </div>
          {!trades ? (
            <div className="space-y-2">
              {Array.from({ length: 3 }).map((_, i) => (
                <div key={i} className="skeleton h-9" />
              ))}
            </div>
          ) : trades.length === 0 ? (
            <p className="py-4 text-sm text-muted">
              No saved deals yet —{" "}
              <Link className="text-brand underline" href="/trade-machine">
                build your first trade
              </Link>
              .
            </p>
          ) : (
            <ul className="divide-y divide-line">
              {trades.slice(0, 5).map((trade) => (
                <li key={trade.id}>
                  <Link
                    href={`/trades/${trade.id}`}
                    className="flex items-center gap-3 py-2 text-sm hover:text-brand"
                  >
                    <span className="flex-1 truncate">{trade.name}</span>
                    <span className="font-mono text-xs text-muted">{trade.teams.join(" ↔ ")}</span>
                    <span className="text-[11px] text-muted">{formatDate(trade.created_at)}</span>
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </div>
        <div className="rounded-lg border border-line bg-panel p-4">
          <div className="mb-2 flex items-baseline justify-between">
            <h2 className="font-semibold">Saved strategies</h2>
            <Link href="/team-hub" className="text-xs text-brand underline">
              team hub →
            </Link>
          </div>
          {!scenarios ? (
            <div className="space-y-2">
              {Array.from({ length: 3 }).map((_, i) => (
                <div key={i} className="skeleton h-9" />
              ))}
            </div>
          ) : scenarios.length === 0 ? (
            <p className="py-4 text-sm text-muted">
              No strategies yet — pick a team in the{" "}
              <Link className="text-brand underline" href="/team-hub">
                Team Hub
              </Link>{" "}
              and choose how you want to build.
            </p>
          ) : (
            <ul className="divide-y divide-line">
              {scenarios.slice(0, 5).map((scenario) => (
                <li key={scenario.id} className="flex items-center gap-3 py-2 text-sm">
                  <Badge status="info">{scenario.focal_team.abbreviation}</Badge>
                  <span className="flex-1 truncate">{scenario.name}</span>
                  <span className="text-xs text-muted">{scenario.strategy}</span>
                  <Link
                    href={`/trade-machine?scenario=${scenario.id}`}
                    className="text-xs text-brand underline"
                  >
                    build →
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </div>
      </section>
    </div>
  );
}

function FavoriteCard({ team, onClear }: { team: Team | undefined; onClear: () => void }) {
  if (!team) return null;
  const theme = teamTheme(team.abbreviation);
  return (
    <div
      className="flex flex-col items-center justify-center gap-2 rounded-xl border p-5"
      style={{
        borderColor: `${theme.bright}55`,
        background: `linear-gradient(160deg, ${theme.primary}33, transparent 70%)`,
      }}
    >
      <TeamLogo abbreviation={team.abbreviation} name={team.full_name} size={72} />
      <div className="text-center">
        <div className="text-sm font-semibold">{team.full_name}</div>
        <div className="text-[11px] text-muted">your team</div>
      </div>
      <div className="flex gap-2">
        <Link
          href={`/team-hub/${team.id}`}
          className="rounded-md border border-line px-3 py-1 text-xs hover:bg-panel2"
        >
          Team Hub
        </Link>
        <button
          type="button"
          onClick={onClear}
          className="rounded-md border border-line px-3 py-1 text-xs text-muted hover:bg-panel2"
        >
          change
        </button>
      </div>
    </div>
  );
}
