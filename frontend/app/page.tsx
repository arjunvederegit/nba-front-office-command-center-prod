"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { api } from "@/lib/api";
import { dataHealthSchema } from "@/lib/schemas";
import { formatDate } from "@/lib/format";
import { setFavoriteTeam, useFavoriteTeam } from "@/lib/teamTheme";
import { teamIdentity, teamVars } from "@/lib/teamIdentity";
import type { DataHealth, Scenario, Team, TradeSummary } from "@/lib/types";
import { BallGlyph, HalfCourt, ShotChartMotif, TransactionLane } from "@/components/court";
import { TeamCrest, TeamLogo } from "@/components/media";
import { useToast } from "@/components/toast";
import { Badge, ButtonLink, Panel, Skeleton, StatBlock } from "@/components/ui";

/* --------------------------------------------------------------- tool data */

interface Tool {
  title: string;
  href: string;
  blurb: string;
  status: "ready" | "needs-import";
  art: React.ReactNode;
}

const TOOLS: Tool[] = [
  {
    title: "Trade Evaluator",
    href: "/trade-evaluator",
    blurb: "Build a two- or three-team deal and get a live rules check with projected impact.",
    status: "ready",
    art: <TransactionLane className="h-10 w-28" active />,
  },
  {
    title: "Strategy Lab",
    href: "/strategy-lab",
    blurb: "Put saved deals side by side and see which one survives your priorities.",
    status: "ready",
    art: (
      <svg viewBox="0 0 112 40" className="h-10 w-28" aria-hidden fill="none">
        <rect x="2" y="14" width="26" height="24" rx="3" stroke="var(--hairline)" />
        <rect x="34" y="6" width="26" height="32" rx="3" stroke="var(--signal)" />
        <rect x="66" y="20" width="26" height="18" rx="3" stroke="var(--hairline)" />
        <circle cx="47" cy="3" r="2.5" fill="var(--signal)" />
      </svg>
    ),
  },
  {
    title: "Player Explorer",
    href: "/player-explorer",
    blurb: "Search every rostered player, compare season lines, and read league context.",
    status: "ready",
    art: <ShotChartMotif className="h-10 w-28 text-signal" />,
  },
  {
    title: "Salary-Cap Center",
    href: "/salary-cap-center",
    blurb: "Payroll by season, expiring money and commitments — once contracts are imported.",
    status: "needs-import",
    art: (
      <svg viewBox="0 0 112 40" className="h-10 w-28" aria-hidden fill="none">
        {[6, 26, 46, 66, 86].map((x, i) => (
          <rect
            key={x}
            x={x}
            y={38 - [26, 20, 14, 9, 5][i]}
            width="14"
            height={[26, 20, 14, 9, 5][i]}
            rx="2"
            fill="var(--leather)"
            fillOpacity={0.25 + i * 0.05}
          />
        ))}
        <line x1="0" y1="12" x2="112" y2="12" stroke="var(--conditional)" strokeDasharray="3 3" />
      </svg>
    ),
  },
];

const ROADMAP = [
  { title: "Contract Predictor", need: "Needs imported contract history before a model can be validated" },
  { title: "Free Agency Planner", need: "Planned once cap holds and exceptions are modeled" },
  { title: "Draft Fit", need: "Planned once verified pick ownership is available" },
];

const CAPABILITIES = [
  ["Real NBA data", "Rosters and stats from NBA.com, never invented"],
  ["Salary-cap validation", "2023 CBA matching bands and apron limits"],
  ["Player-impact modeling", "Validated against a persistence baseline"],
  ["Scenario comparison", "Rank deals under your own priorities"],
  ["Uncertainty analysis", "Ranges and probabilities, not false precision"],
  ["Transparent methodology", "Every number traces to a documented calculation"],
];

/* -------------------------------------------------------------------- page */

export default function OverviewPage() {
  const toast = useToast();
  const favorite = useFavoriteTeam();

  const { data: teams } = useQuery({ queryKey: ["teams"], queryFn: () => api.get<Team[]>("/teams") });
  const { data: health } = useQuery({
    queryKey: ["data-health"],
    queryFn: () => api.get<DataHealth>("/data-health", dataHealthSchema),
  });
  const { data: trades } = useQuery({
    queryKey: ["trades"],
    queryFn: () => api.get<TradeSummary[]>("/trades"),
  });
  const { data: scenarios } = useQuery({
    queryKey: ["scenarios"],
    queryFn: () => api.get<Scenario[]>("/scenarios"),
  });

  const favoriteTeam = teams?.find((t) => t.id === favorite?.id) ?? null;
  const identity = teamIdentity(favorite?.abbreviation);
  const rosterSpots = health?.tables?.rosters?.rows ?? null;
  const photoCoverage = health?.asset_coverage?.player_photo_coverage ?? null;

  return (
    <div className="space-y-10">
      {/* ---------------------------------------------------------- hero */}
      <section
        className="panel relative overflow-hidden"
        style={{ ...teamVars(favorite?.abbreviation), "--edge": identity.bright } as React.CSSProperties}
      >
        <div
          aria-hidden
          className="pointer-events-none absolute inset-0 opacity-[0.55]"
          style={{
            background: `radial-gradient(680px 320px at 88% 8%, ${identity.primary}33, transparent 70%)`,
          }}
        />
        <div className="relative grid gap-8 p-6 md:p-9 lg:grid-cols-[minmax(0,1fr)_340px] lg:items-center">
          <div className="min-w-0">
            <div className="eyebrow flex flex-wrap items-center gap-x-2.5 gap-y-1">
              <span className="flex items-center gap-1.5 text-signal">
                <BallGlyph size={13} />
                RosterLab
              </span>
              <span aria-hidden className="hidden text-faint sm:inline">
                /
              </span>
              <span className="hidden sm:inline">Basketball Decision Intelligence</span>
              {health && (
                <>
                  <span aria-hidden className="text-faint">
                    /
                  </span>
                  <span>{health.current_season} season</span>
                </>
              )}
            </div>

            <h1 className="title-xl mt-3 text-foreground">
              Build the next move.
            </h1>
            <p className="mt-3 max-w-xl text-[15px] leading-relaxed text-muted">
              Evaluate trades, compare roster strategies, and understand the decisions shaping an
              NBA team — on live data, with a rules check that never guesses.
            </p>

            <div className="mt-6 flex flex-wrap items-center gap-3">
              <ButtonLink
                href={favorite ? `/trade-evaluator?team=${favorite.id}` : "/trade-evaluator"}
                variant="primary"
              >
                Open the Trade Evaluator
              </ButtonLink>
              <ButtonLink href="/player-explorer" variant="secondary">
                Explore the platform
              </ButtonLink>
            </div>

            <dl className="mt-7 flex flex-wrap gap-x-8 gap-y-3 border-t border-hairline pt-4">
              <div>
                <dt className="eyebrow text-[0.5625rem]">Teams</dt>
                <dd className="numeral text-xl leading-none">{teams?.length ?? "—"}</dd>
              </div>
              <div>
                <dt className="eyebrow text-[0.5625rem]">Roster spots</dt>
                <dd className="numeral text-xl leading-none">{rosterSpots ?? "—"}</dd>
              </div>
              <div>
                <dt className="eyebrow text-[0.5625rem]">Saved deals</dt>
                <dd className="numeral text-xl leading-none">{trades?.length ?? "—"}</dd>
              </div>
              <div className="min-w-0">
                <dt className="eyebrow text-[0.5625rem]">Data synced</dt>
                <dd className="text-sm leading-tight text-muted">
                  {health ? formatDate(health.last_successful_sync) : "—"}
                </dd>
              </div>
            </dl>
          </div>

          {/* The floor: your franchise standing at the top of the key. */}
          <div className="relative mx-auto w-full max-w-[340px]">
            <div className="relative aspect-[50/47] w-full">
              <HalfCourt className="absolute inset-0 h-full w-full text-signal/30" />
              <ShotChartMotif className="absolute inset-0 h-full w-full text-signal/25" />
              <div className="absolute inset-x-0 top-[14%] flex flex-col items-center px-4 text-center">
                {favoriteTeam ? (
                  <>
                    <TeamCrest
                      abbreviation={favoriteTeam.abbreviation}
                      name={favoriteTeam.full_name}
                      size={72}
                    />
                    <div className="display mt-2 max-w-full truncate text-lg leading-tight text-foreground">
                      {favoriteTeam.nickname ?? favoriteTeam.full_name}
                    </div>
                    <div className="eyebrow mt-0.5 text-[0.5625rem]">Your team</div>
                    <div className="mt-3 flex flex-wrap justify-center gap-2">
                      <ButtonLink href={`/team-outlook/${favoriteTeam.id}`} size="sm">
                        Team Outlook
                      </ButtonLink>
                      <ButtonLink
                        href={`/trade-evaluator?team=${favoriteTeam.id}`}
                        size="sm"
                        variant="signal"
                      >
                        Trade
                      </ButtonLink>
                    </div>
                  </>
                ) : (
                  <>
                    <span
                      aria-hidden
                      className="flex h-[72px] w-[72px] items-center justify-center rounded-full border border-dashed border-line text-signal/70"
                    >
                      <BallGlyph size={30} />
                    </span>
                    <div className="display mt-2 text-lg leading-tight text-foreground">
                      Pick your team
                    </div>
                    <p className="mt-1 text-[12px] leading-snug text-muted">
                      Choose a franchise below — RosterLab defaults to it everywhere.
                    </p>
                  </>
                )}
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* ------------------------------------------------------ tool launcher */}
      <section>
        <SectionHead
          eyebrow="The platform"
          title="Front-office tools"
          aside="Every active tool is one click from here"
        />
        <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
          {TOOLS.map((tool) => (
            <Link
              key={tool.title}
              href={tool.href}
              className="panel group flex flex-col p-4 transition-colors hover:border-signal/45"
            >
              <div className="flex items-start justify-between gap-2">
                <h3 className="title-md whitespace-nowrap text-foreground group-hover:text-signal">
                  {tool.title}
                </h3>
                {tool.status === "ready" ? (
                  <Badge status="pass">ready</Badge>
                ) : (
                  <Badge status="warning">needs import</Badge>
                )}
              </div>
              <p className="mt-2 flex-1 text-[13px] leading-relaxed text-muted">{tool.blurb}</p>
              <div className="mt-3 flex items-end justify-between">
                <span className="text-muted/80">{tool.art}</span>
                <span className="eyebrow text-signal opacity-0 transition-opacity group-hover:opacity-100">
                  Open →
                </span>
              </div>
            </Link>
          ))}
        </div>

        <div className="mt-3 rounded-lg border border-dashed border-line px-4 py-3">
          <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
            <span className="eyebrow">On the roadmap</span>
            <span className="text-[11px] text-faint">
              Not shipped, not clickable — RosterLab won&apos;t fake a model it can&apos;t validate.
            </span>
          </div>
          <ul className="mt-2 flex flex-wrap gap-x-6 gap-y-1.5">
            {ROADMAP.map((item) => (
              <li key={item.title} className="text-[13px]">
                <span className="text-muted">{item.title}</span>{" "}
                <span className="text-faint">— {item.need}</span>
              </li>
            ))}
          </ul>
        </div>
      </section>

      {/* -------------------------------------------------- team picker strip */}
      <section>
        <SectionHead
          eyebrow="Set your context"
          title="Pick your team"
          aside="Sets the default across every tool"
        />
        {!teams ? (
          <div className="grid grid-cols-5 gap-2 md:grid-cols-10">
            {Array.from({ length: 30 }).map((_, i) => (
              <Skeleton key={i} className="h-[74px]" />
            ))}
          </div>
        ) : (
          <div className="grid grid-cols-5 gap-2 sm:grid-cols-6 md:grid-cols-10">
            {teams.map((team) => {
              const chosen = favorite?.id === team.id;
              const teamColors = teamIdentity(team.abbreviation);
              return (
                <button
                  key={team.id}
                  type="button"
                  aria-pressed={chosen}
                  title={`Set ${team.full_name} as your team`}
                  onClick={() => {
                    setFavoriteTeam({ id: team.id, abbreviation: team.abbreviation });
                    toast("success", `${team.full_name} is now your team.`);
                  }}
                  className={`flex flex-col items-center gap-1.5 rounded-lg border px-1 py-2.5 transition-colors ${
                    chosen ? "bg-panel2" : "border-hairline bg-panel hover:bg-panel2"
                  }`}
                  style={chosen ? { borderColor: teamColors.bright } : undefined}
                >
                  <TeamLogo abbreviation={team.abbreviation} name={team.full_name} size={34} decorative />
                  <span
                    className="numeral text-[13px] leading-none"
                    style={{ color: chosen ? teamColors.bright : undefined }}
                  >
                    {team.abbreviation}
                  </span>
                </button>
              );
            })}
          </div>
        )}
      </section>

      {/* -------------------------------------------------- front-office snapshot */}
      <section>
        <SectionHead eyebrow="Your work" title="Front-office snapshot" />
        <div className="grid gap-3 lg:grid-cols-2">
          <Panel title="Recent deals" actions={<Link className="eyebrow text-signal" href="/strategy-lab">Compare →</Link>}>
            {!trades ? (
              <div className="space-y-2">
                {Array.from({ length: 4 }).map((_, i) => (
                  <Skeleton key={i} className="h-9" />
                ))}
              </div>
            ) : trades.length === 0 ? (
              <SnapshotEmpty
                title="No deals saved yet"
                body="Build one in the Trade Evaluator and it will show up here for comparison."
                href="/trade-evaluator"
                cta="Open the Trade Evaluator"
              />
            ) : (
              <ul className="divide-y divide-hairline">
                {trades.slice(0, 5).map((trade) => (
                  <li key={trade.id}>
                    <Link
                      href={`/trades/${trade.id}`}
                      className="flex items-center gap-3 py-2 transition-colors hover:text-signal"
                    >
                      <span className="min-w-0 flex-1 truncate text-sm">{trade.name}</span>
                      <span className="flex shrink-0 items-center gap-1">
                        {trade.teams.map((abbr) => (
                          <TeamLogo key={abbr} abbreviation={abbr} size={18} decorative />
                        ))}
                      </span>
                      <span className="hidden shrink-0 text-[11px] text-faint sm:inline">
                        {formatDate(trade.created_at)}
                      </span>
                    </Link>
                  </li>
                ))}
              </ul>
            )}
          </Panel>

          <Panel
            title="Saved strategies"
            actions={<Link className="eyebrow text-signal" href="/team-outlook">Team Outlook →</Link>}
          >
            {!scenarios ? (
              <div className="space-y-2">
                {Array.from({ length: 4 }).map((_, i) => (
                  <Skeleton key={i} className="h-9" />
                ))}
              </div>
            ) : scenarios.length === 0 ? (
              <SnapshotEmpty
                title="No strategies yet"
                body="Choose how a team should build in Team Outlook — it sets how every deal is scored."
                href="/team-outlook"
                cta="Choose a strategy"
              />
            ) : (
              <ul className="divide-y divide-hairline">
                {scenarios.slice(0, 5).map((scenario) => (
                  <li key={scenario.id} className="flex items-center gap-3 py-2 text-sm">
                    <TeamLogo abbreviation={scenario.focal_team.abbreviation} size={20} decorative />
                    <span className="min-w-0 flex-1 truncate">{scenario.name}</span>
                    <Badge status="info">{scenario.strategy.replace("_", " ")}</Badge>
                    <Link
                      href={`/trade-evaluator?scenario=${scenario.id}`}
                      className="eyebrow shrink-0 text-signal"
                    >
                      Build →
                    </Link>
                  </li>
                ))}
              </ul>
            )}
          </Panel>
        </div>

        {health && (
          <div className="mt-3 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            <Panel padded={false} className="px-4 py-3">
              <StatBlock
                label="Live NBA data"
                value={health.last_successful_sync ? "Synced" : "None"}
                note={formatDate(health.last_successful_sync)}
                size="sm"
                accent="var(--legal)"
              />
            </Panel>
            <Panel padded={false} className="px-4 py-3">
              <StatBlock
                label="Contracts"
                value={health.providers.contracts?.configured ? "Imported" : "Not imported"}
                note="Salary rules stay unavailable until imported"
                size="sm"
                accent={health.providers.contracts?.configured ? "var(--legal)" : "var(--unknown)"}
              />
            </Panel>
            <Panel padded={false} className="px-4 py-3">
              <StatBlock
                label="Player photos"
                value={photoCoverage !== null ? `${Math.round(photoCoverage * 100)}%` : "—"}
                note="of rostered players matched"
                size="sm"
                accent="var(--signal)"
              />
            </Panel>
            <Panel padded={false} className="px-4 py-3">
              <StatBlock
                label="Active models"
                value={health.active_models?.length ?? 0}
                note="validation shown in Data Health"
                size="sm"
                accent="var(--signal)"
              />
            </Panel>
          </div>
        )}
      </section>

      {/* --------------------------------------------------- capability strip */}
      <section className="hardwood rounded-xl border border-hairline px-5 py-5">
        <SectionHead eyebrow="What it does" title="Built for defensible decisions" />
        <ul className="grid gap-x-6 gap-y-3 sm:grid-cols-2 lg:grid-cols-3">
          {CAPABILITIES.map(([title, body]) => (
            <li key={title} className="flex gap-2.5">
              <span aria-hidden className="mt-1 text-signal">
                <BallGlyph size={13} />
              </span>
              <span className="min-w-0">
                <span className="block whitespace-nowrap text-sm font-semibold text-foreground">
                  {title}
                </span>
                <span className="block text-[12px] leading-snug text-muted">{body}</span>
              </span>
            </li>
          ))}
        </ul>
      </section>
    </div>
  );
}

/* ------------------------------------------------------------------ pieces */

function SectionHead({
  eyebrow,
  title,
  aside,
}: {
  eyebrow: string;
  title: string;
  aside?: string;
}) {
  return (
    <div className="mb-3">
      <div className="h-px w-full bg-gradient-to-r from-signal/60 to-transparent" />
      <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1 pt-2.5">
        <div>
          <div className="eyebrow">{eyebrow}</div>
          <h2 className="title-lg mt-1 whitespace-nowrap text-foreground">{title}</h2>
        </div>
        {aside && <p className="text-[11px] text-faint">{aside}</p>}
      </div>
    </div>
  );
}

function SnapshotEmpty({
  title,
  body,
  href,
  cta,
}: {
  title: string;
  body: string;
  href: string;
  cta: string;
}) {
  return (
    <div className="court-grid rounded-lg border border-dashed border-line px-4 py-6 text-center">
      <p className="title-md text-foreground">{title}</p>
      <p className="mx-auto mt-1 max-w-sm text-[13px] leading-relaxed text-muted">{body}</p>
      <ButtonLink href={href} size="sm" className="mt-3">
        {cta}
      </ButtonLink>
    </div>
  );
}
