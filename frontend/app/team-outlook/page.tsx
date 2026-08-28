"use client";

/**
 * Team Outlook index — the league board.
 *
 * Thirty franchises grouped by conference, each card carrying its own color as a
 * left edge and a lit top edge. A name filter keeps the board usable without
 * turning it into a list.
 */

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { useMemo, useState } from "react";
import { api } from "@/lib/api";
import { count } from "@/lib/format";
import { teamIdentity } from "@/lib/teamIdentity";
import { useFavoriteTeam } from "@/lib/favoriteTeam";
import type { Team } from "@/lib/types";
import { TeamLogo } from "@/components/media";
import { EmptyState, ErrorState, PageHeader, Skeleton, SourceRail } from "@/components/ui";

type ConferenceKey = "East" | "West" | "Other";

const CONFERENCE_ORDER: ConferenceKey[] = ["East", "West", "Other"];

const CONFERENCE_LABEL: Record<ConferenceKey, string> = {
  East: "Eastern Conference",
  West: "Western Conference",
  Other: "Unclassified",
};

export default function TeamOutlookIndex() {
  const {
    data: teams,
    error,
    isLoading,
  } = useQuery({ queryKey: ["teams"], queryFn: () => api.get<Team[]>("/teams"), staleTime: 300_000 });

  const favorite = useFavoriteTeam();
  const [query, setQuery] = useState("");

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return teams ?? [];
    return (teams ?? []).filter(
      (team) =>
        team.full_name.toLowerCase().includes(q) ||
        team.city.toLowerCase().includes(q) ||
        team.abbreviation.toLowerCase().startsWith(q) ||
        (team.division ?? "").toLowerCase().includes(q),
    );
  }, [teams, query]);

  const byConference = useMemo(() => {
    const groups: Record<ConferenceKey, Team[]> = { East: [], West: [], Other: [] };
    for (const team of filtered) {
      const key: ConferenceKey =
        team.conference === "East" || team.conference === "West" ? team.conference : "Other";
      groups[key].push(team);
    }
    for (const key of CONFERENCE_ORDER) {
      groups[key].sort((a, b) => {
        const divisionOrder = (a.division ?? "").localeCompare(b.division ?? "");
        return divisionOrder !== 0 ? divisionOrder : a.full_name.localeCompare(b.full_name);
      });
    }
    return groups;
  }, [filtered]);

  const retrievedAt = teams?.[0]?.provenance?.source_retrieved_at ?? null;

  return (
    <div className="space-y-8">
      <PageHeader
        eyebrow="The league board"
        title="Team Outlook"
        lede="Every franchise, one board. Open a team for its roster, model-derived strengths and needs, competitive window and payroll picture — then start building."
        actions={
          <label className="flex items-center gap-2">
            <span className="eyebrow whitespace-nowrap">Find a team</span>
            <input
              type="search"
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="Celtics, BOS, Atlantic…"
              aria-label="Filter teams by name, abbreviation or division"
              className="w-48 rounded-md border border-line bg-panel2 px-3 py-1.5 text-sm text-foreground placeholder:text-faint focus:border-signal/60 sm:w-56"
            />
          </label>
        }
        meta={
          teams && (
            <span className="eyebrow">
              {filtered.length === teams.length
                ? count(teams.length, "franchise", "franchises")
                : `${filtered.length} of ${count(teams.length, "franchise", "franchises")}`}
            </span>
          )
        }
      />

      {error && <ErrorState message={`Could not load teams: ${String(error)}`} />}

      {isLoading && (
        <section>
          <ConferenceRail label="Eastern Conference" count={null} />
          <div className="grid grid-cols-1 gap-2.5 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 2xl:grid-cols-5">
            {Array.from({ length: 15 }).map((_, i) => (
              <Skeleton key={i} className="h-[76px]" />
            ))}
          </div>
        </section>
      )}

      {teams && filtered.length === 0 && (
        <EmptyState
          title="No franchise matches that search"
          hint="Try a city, a nickname, a three-letter abbreviation, or a division name."
          action={
            <button
              type="button"
              onClick={() => setQuery("")}
              className="rounded-md border border-line bg-panel2 px-4 py-2 text-sm text-foreground transition-colors hover:border-signal/50"
            >
              Clear the filter
            </button>
          }
        />
      )}

      {teams &&
        CONFERENCE_ORDER.filter((key) => byConference[key].length > 0).map((key) => (
          <section key={key}>
            <ConferenceRail label={CONFERENCE_LABEL[key]} count={byConference[key].length} />
            <div className="grid grid-cols-1 gap-2.5 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 2xl:grid-cols-5">
              {byConference[key].map((team) => (
                <TeamBoardCard
                  key={team.id}
                  team={team}
                  isFavorite={favorite?.id === team.id}
                />
              ))}
            </div>
          </section>
        ))}

      {teams && (
        <SourceRail source={teams[0]?.provenance?.upstream ?? "unknown source"} retrievedAt={retrievedAt} />
      )}
    </div>
  );
}

function ConferenceRail({ label, count }: { label: string; count: number | null }) {
  return (
    <div className="mb-3">
      <div className="h-px w-full bg-gradient-to-r from-signal/60 to-transparent" />
      <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1 pt-2.5">
        <h2 className="title-lg text-balance text-foreground">{label}</h2>
        {count !== null && (
          <span className="eyebrow">
            {count} {count === 1 ? "team" : "teams"}
          </span>
        )}
      </div>
    </div>
  );
}

function TeamBoardCard({ team, isFavorite }: { team: Team; isFavorite: boolean }) {
  const identity = teamIdentity(team.abbreviation);
  return (
    <Link
      href={`/team-outlook/${team.id}`}
      className="panel group relative flex items-center gap-3 overflow-hidden py-3 pl-4 pr-3 transition-colors hover:border-signal/45"
      style={{ "--edge": identity.bright } as React.CSSProperties}
    >
      <span
        aria-hidden
        className="absolute inset-y-0 left-0 w-[3px]"
        style={{ background: identity.primary }}
      />
      <TeamLogo abbreviation={team.abbreviation} name={team.full_name} size={38} decorative />
      <span className="min-w-0 flex-1">
        <span className="title-md block truncate text-foreground transition-colors group-hover:text-signal">
          {team.nickname ?? team.full_name}
        </span>
        <span className="eyebrow mt-1 block truncate text-[0.5625rem]">
          {team.city} · {team.division ?? "—"}
        </span>
      </span>
      <span className="flex shrink-0 flex-col items-end gap-1">
        <span
          className="numeral text-[15px] leading-none"
          style={{ color: identity.bright }}
        >
          {team.abbreviation}
        </span>
        {isFavorite && (
          <span className="eyebrow whitespace-nowrap text-[0.5rem] text-signal">Your team</span>
        )}
      </span>
    </Link>
  );
}
