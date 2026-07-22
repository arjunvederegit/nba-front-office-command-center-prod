"use client";

/**
 * Global shell pieces: primary navigation with active states, compact data-status
 * chip, and a global player/team search. Fan-facing labels; technical detail lives
 * behind Data Status and Methodology.
 */

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { api } from "@/lib/api";
import type { DataHealth, Team } from "@/lib/types";
import { BrandMark, BrandWordmark } from "@/components/brand";
import { TeamLogo } from "@/components/media";

const NAV = [
  { href: "/", label: "Home", exact: true },
  { href: "/team-hub", label: "Team Hub" },
  { href: "/trade-machine", label: "Trade Machine" },
  { href: "/compare", label: "Compare Deals" },
  { href: "/player-lab", label: "Player Lab" },
  { href: "/cap-lab", label: "Cap Lab" },
  { href: "/methodology", label: "Methodology" },
  { href: "/data-status", label: "Data Status" },
];

function DataStatusChip() {
  const { data } = useQuery({
    queryKey: ["data-health"],
    queryFn: () => api.get<DataHealth>("/data-health"),
    staleTime: 120_000,
  });
  const [now] = useState(() => Date.now());
  if (!data) return null;
  const synced = !!data.last_successful_sync;
  const ageHours = synced
    ? (now - new Date(data.last_successful_sync as string).getTime()) / 3_600_000
    : Infinity;
  const fresh = ageHours < 48;
  return (
    <Link
      href="/data-status"
      className="hidden items-center gap-1.5 rounded-full border border-line px-2.5 py-1 text-[11px] text-muted transition hover:text-foreground xl:flex"
      title="Open Data Status"
    >
      <span
        className={`h-2 w-2 rounded-full ${fresh ? "bg-pass" : synced ? "bg-warn" : "bg-unavail"}`}
        aria-hidden
      />
      {fresh ? "Live data synced" : synced ? "Data getting stale" : "No data synced"}
    </Link>
  );
}

interface SearchTeam {
  kind: "team";
  team: Team;
}
interface SearchPlayer {
  kind: "player";
  id: string;
  name: string;
  nba_player_id: number;
  team_abbr: string | null;
}

function GlobalSearch() {
  const router = useRouter();
  const [query, setQuery] = useState("");
  const [open, setOpen] = useState(false);
  const boxRef = useRef<HTMLDivElement>(null);
  const { data: teams } = useQuery({
    queryKey: ["teams"],
    queryFn: () => api.get<Team[]>("/teams"),
    staleTime: 300_000,
  });
  const { data: playerHits } = useQuery({
    queryKey: ["search-players", query],
    queryFn: () =>
      api.get<{
        players: {
          id: string;
          full_name: string;
          nba_player_id: number;
          current_team: Team | null;
        }[];
      }>(`/players?q=${encodeURIComponent(query)}&rostered_only=true&limit=6`),
    enabled: query.trim().length >= 2,
    staleTime: 60_000,
  });

  useEffect(() => {
    function onClick(event: MouseEvent) {
      if (boxRef.current && !boxRef.current.contains(event.target as Node)) setOpen(false);
    }
    document.addEventListener("mousedown", onClick);
    return () => document.removeEventListener("mousedown", onClick);
  }, []);

  const q = query.trim().toLowerCase();
  const teamHits: SearchTeam[] = q.length >= 2 && teams
    ? teams
        .filter(
          (t) =>
            t.full_name.toLowerCase().includes(q) || t.abbreviation.toLowerCase().startsWith(q),
        )
        .slice(0, 4)
        .map((team) => ({ kind: "team", team }))
    : [];
  const players: SearchPlayer[] = (playerHits?.players ?? []).map((p) => ({
    kind: "player",
    id: p.id,
    name: p.full_name,
    nba_player_id: p.nba_player_id,
    team_abbr: p.current_team?.abbreviation ?? null,
  }));
  const results = [...teamHits, ...players];

  function go(result: SearchTeam | SearchPlayer) {
    setOpen(false);
    setQuery("");
    if (result.kind === "team") router.push(`/team-hub/${result.team.id}`);
    else router.push(`/players/${result.id}`);
  }

  return (
    <div ref={boxRef} className="relative hidden md:block">
      <input
        type="search"
        role="combobox"
        aria-expanded={open && results.length > 0}
        aria-controls="global-search-results"
        aria-label="Search players and teams"
        placeholder="Search players & teams…"
        value={query}
        onChange={(e) => {
          setQuery(e.target.value);
          setOpen(true);
        }}
        onFocus={() => setOpen(true)}
        className="w-52 rounded-full border border-line bg-panel2 px-3.5 py-1.5 text-sm placeholder:text-muted/70 focus:w-64 focus:border-brand/60 transition-all"
      />
      {open && results.length > 0 && (
        <ul
          id="global-search-results"
          role="listbox"
          className="absolute right-0 top-10 z-50 w-72 overflow-hidden rounded-lg border border-line bg-panel shadow-xl"
        >
          {results.map((result, i) => (
            <li key={i}>
              <button
                type="button"
                onClick={() => go(result)}
                className="flex w-full items-center gap-2 px-3 py-2 text-left text-sm hover:bg-panel2"
              >
                {result.kind === "team" ? (
                  <>
                    <TeamLogo
                      abbreviation={result.team.abbreviation}
                      name={result.team.full_name}
                      size={22}
                    />
                    <span className="flex-1">{result.team.full_name}</span>
                    <span className="text-[10px] uppercase text-muted">team</span>
                  </>
                ) : (
                  <>
                    <span className="w-[22px] text-center text-xs text-muted">👤</span>
                    <span className="flex-1">{result.name}</span>
                    <span className="text-[10px] text-muted">{result.team_abbr ?? ""}</span>
                  </>
                )}
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

export function AppNav() {
  const pathname = usePathname();
  return (
    <header className="sticky top-0 z-40 border-b border-line bg-background/92 backdrop-blur">
      <div className="mx-auto flex max-w-7xl items-center gap-4 px-4 py-2.5">
        <Link href="/" className="flex items-center gap-2.5" aria-label="RosterLab home">
          <BrandMark size={30} />
          <BrandWordmark />
        </Link>
        <nav className="ml-auto flex flex-wrap items-center gap-0.5" aria-label="Primary">
          {NAV.map((item) => {
            const active = item.exact ? pathname === item.href : pathname.startsWith(item.href);
            return (
              <Link
                key={item.href}
                href={item.href}
                aria-current={active ? "page" : undefined}
                className={`rounded-md px-2.5 py-1.5 text-[13px] transition-colors ${
                  active
                    ? "bg-panel2 font-semibold text-foreground shadow-[inset_0_-2px_0_var(--brand)]"
                    : "text-muted hover:bg-panel hover:text-foreground"
                }`}
              >
                {item.label}
              </Link>
            );
          })}
        </nav>
        <GlobalSearch />
        <DataStatusChip />
      </div>
    </header>
  );
}
