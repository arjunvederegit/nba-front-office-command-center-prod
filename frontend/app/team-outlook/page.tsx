"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { api } from "@/lib/api";
import { teamTheme } from "@/lib/teamTheme";
import type { Team } from "@/lib/types";
import { TeamLogo } from "@/components/media";

export default function TeamHubIndex() {
  const { data: teams } = useQuery({ queryKey: ["teams"], queryFn: () => api.get<Team[]>("/teams") });

  const byConference: Record<string, Team[]> = { East: [], West: [], Other: [] };
  for (const team of teams ?? []) {
    const conf = team.conference === "East" || team.conference === "West" ? team.conference : "Other";
    byConference[conf].push(team);
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold">Team Hub</h1>
        <p className="mt-1 text-sm text-muted">
          Pick a franchise to see its roster, strengths and weaknesses, payroll picture and
          competitive window — then start building.
        </p>
      </div>
      {!teams ? (
        <div className="grid grid-cols-2 gap-3 md:grid-cols-5">
          {Array.from({ length: 30 }).map((_, i) => (
            <div key={i} className="skeleton h-24" />
          ))}
        </div>
      ) : (
        (["East", "West", "Other"] as const)
          .filter((conf) => byConference[conf].length > 0)
          .map((conf) => (
            <section key={conf}>
              <h2 className="mb-2 text-sm font-semibold uppercase tracking-wider text-muted">
                {conf === "Other" ? "Teams" : `${conf}ern Conference`}
              </h2>
              <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 md:grid-cols-5">
                {byConference[conf].map((team) => {
                  const theme = teamTheme(team.abbreviation);
                  return (
                    <Link
                      key={team.id}
                      href={`/team-hub/${team.id}`}
                      className="group flex items-center gap-3 rounded-lg border border-line bg-panel p-3 transition hover:bg-panel2"
                      style={{ borderLeft: `3px solid ${theme.primary}` }}
                    >
                      <TeamLogo abbreviation={team.abbreviation} name={team.full_name} size={40} />
                      <div className="min-w-0">
                        <div className="truncate text-sm font-semibold group-hover:text-brand">
                          {team.nickname ?? team.full_name}
                        </div>
                        <div className="text-[11px] text-muted">
                          {team.city} · {team.abbreviation}
                        </div>
                      </div>
                    </Link>
                  );
                })}
              </div>
            </section>
          ))
      )}
    </div>
  );
}
