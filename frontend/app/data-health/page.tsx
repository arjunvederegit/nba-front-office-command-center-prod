"use client";

/**
 * Data Health — what is powering RosterLab right now, and what to plug in next.
 *
 * The honesty rule is structural here: the summary strip counts critical sources
 * that are missing, so a page carrying an unconfigured contract provider can
 * never read as all-green. Full technical detail stays behind one expander.
 */

import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { dataHealthSchema } from "@/lib/schemas";
import { formatDate } from "@/lib/format";
import type { DataHealth, SourceCard } from "@/lib/types";
import {
  Badge,
  Button,
  EmptyState,
  ErrorState,
  MeterBar,
  PageHeader,
  Panel,
  Skeleton,
  SourceRail,
  StatBlock,
  Td,
  Th,
} from "@/components/ui";

const CARD_BADGE_STATUS: Record<SourceCard["status"], string> = {
  fresh: "pass",
  derived: "derived",
  stale: "stale",
  incomplete: "warning",
  unavailable: "unavailable",
  failed: "fail",
};

const CARD_BADGE_LABEL: Record<SourceCard["status"], string> = {
  fresh: "fresh",
  derived: "derived",
  stale: "stale",
  incomplete: "incomplete",
  unavailable: "not configured",
  failed: "failed",
};

const CARD_EDGE: Record<SourceCard["status"], string> = {
  fresh: "var(--legal)",
  derived: "var(--signal)",
  stale: "var(--conditional)",
  incomplete: "var(--conditional)",
  unavailable: "var(--unknown)",
  failed: "var(--illegal)",
};

/** Sources the product refuses to work around: without them, whole rules go dark. */
const CRITICAL_KEYS = new Set(["contracts"]);

/** Pull a leading percentage out of the backend's own coverage sentence, if present. */
function coveragePercent(coverage: string): number | null {
  const match = coverage.match(/(\d+(?:\.\d+)?)\s*%/);
  if (!match) return null;
  const value = Number(match[1]);
  return Number.isFinite(value) ? Math.max(0, Math.min(100, value)) : null;
}

/** "30/30 teams" style ratios also deserve a meter. */
function coverageRatio(coverage: string): number | null {
  const match = coverage.match(/\b(\d+)\s*\/\s*(\d+)\b/);
  if (!match) return null;
  const [, a, b] = match;
  const denominator = Number(b);
  if (!denominator) return null;
  return Math.max(0, Math.min(100, (Number(a) / denominator) * 100));
}

export default function DataHealthPage() {
  const { data, error, refetch, isFetching } = useQuery({
    queryKey: ["data-health"],
    queryFn: () => api.get<DataHealth>("/data-health", dataHealthSchema),
  });

  if (error) return <ErrorState message={`Could not load data health: ${String(error)}`} />;

  if (!data) {
    return (
      <div className="space-y-5">
        <PageHeader
          eyebrow="Provenance"
          title="Data Health"
          lede="What's powering RosterLab right now — and what to plug in next."
        />
        <Skeleton className="h-24" />
        <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
          {Array.from({ length: 6 }).map((_, i) => (
            <Skeleton key={i} className="h-52" />
          ))}
        </div>
      </div>
    );
  }

  const cards = data.source_cards ?? [];
  const criticalMissing = cards.filter(
    (card) =>
      CRITICAL_KEYS.has(card.key) && (card.status === "unavailable" || card.status === "failed"),
  );
  const attention = cards.filter(
    (card) => card.status === "unavailable" || card.status === "failed" || card.status === "stale",
  );
  const healthy = cards.filter((card) => card.status === "fresh" || card.status === "derived");
  const nextSteps = cards.filter((card) => card.action);

  const headline =
    criticalMissing.length > 0
      ? {
          status: "warning",
          text: `${criticalMissing.length} critical source${
            criticalMissing.length === 1 ? "" : "s"
          } missing`,
        }
      : attention.length > 0
        ? {
            status: "warning",
            text: `${attention.length} source${attention.length === 1 ? "" : "s"} need attention`,
          }
        : { status: "pass", text: "All sources healthy" };

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="Provenance"
        title="Data Health"
        lede="Every screen in RosterLab traces to one of these sources. When a source is missing, the product says so instead of estimating around it."
        actions={
          <Button variant="secondary" onClick={() => refetch()} disabled={isFetching}>
            {isFetching ? "Refreshing…" : "Refresh"}
          </Button>
        }
        meta={
          <>
            <Badge status={headline.status}>{headline.text}</Badge>
            <span className="eyebrow">{data.current_season} season</span>
            <span className="eyebrow">cap year {data.cap_league_year}</span>
            <span className="text-[11px] text-faint">
              generated {formatDate(data.generated_at)}
            </span>
          </>
        }
      />

      {/* -------------------------------------------------------- summary strip */}
      <Panel
        className={criticalMissing.length > 0 ? "border-conditional/35" : undefined}
        accent={criticalMissing.length > 0 ? "var(--conditional)" : "var(--legal)"}
        padded={false}
      >
        <div className="grid gap-x-6 gap-y-4 px-5 py-4 sm:grid-cols-2 lg:grid-cols-4">
          <StatBlock
            label="Sources reporting"
            value={cards.length}
            note="listed below with coverage"
            size="sm"
          />
          <StatBlock
            label="Healthy"
            value={healthy.length}
            note="fresh or derived from a live source"
            size="sm"
            accent="var(--legal)"
          />
          <StatBlock
            label="Need attention"
            value={attention.length}
            note="stale, failed or not configured"
            size="sm"
            accent={attention.length > 0 ? "var(--conditional)" : "var(--chalk-dim)"}
          />
          <StatBlock
            label="Critical missing"
            value={criticalMissing.length}
            note={
              criticalMissing.length > 0
                ? "salary rules report unavailable until fixed"
                : "no blocking gaps"
            }
            size="sm"
            accent={criticalMissing.length > 0 ? "var(--illegal)" : "var(--legal)"}
          />
        </div>
        {criticalMissing.length > 0 && (
          <div className="border-t border-hairline px-5 py-3">
            <p className="flex flex-wrap items-baseline gap-x-2 gap-y-1 text-sm text-muted">
              <span aria-hidden className="font-mono text-conditional">
                !
              </span>
              <span className="font-semibold text-foreground">
                {criticalMissing.map((card) => card.title).join(", ")} not configured.
              </span>
              <span>
                Salary matching, apron limits and payroll stay <em>unavailable</em> product-wide —
                no trade will ever be reported as legal from partial checks.
              </span>
            </p>
          </div>
        )}
      </Panel>

      {/* --------------------------------------------------------- source cards */}
      <section>
        <SectionRail
          title="Sources"
          aside={
            nextSteps.length > 0
              ? nextSteps.length === 1
                ? "1 source carries a next step"
                : `${nextSteps.length} sources carry a next step`
              : "No action required"
          }
        />
        {cards.length === 0 ? (
          <EmptyState
            title="No source summary available"
            hint="The backend did not return source cards. The technical details below still show table counts, sync runs and provider configuration."
          />
        ) : (
          <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
            {cards.map((card) => {
              const percent = coveragePercent(card.coverage) ?? coverageRatio(card.coverage);
              const missing = card.status === "unavailable" || card.status === "failed";
              return (
                // The panel surface with a manual body so the provenance rail can be
                // pinned to the bottom edge of every card in an equal-height row.
                <article
                  key={card.key}
                  className="panel flex min-w-0 flex-col"
                  style={
                    { "--edge": CARD_EDGE[card.status] ?? "var(--signal)" } as React.CSSProperties
                  }
                >
                  <header className="flex items-start justify-between gap-x-3 gap-y-2 border-b border-hairline px-4 py-3">
                    <h3 className="title-md truncate text-foreground">{card.title}</h3>
                    <Badge status={CARD_BADGE_STATUS[card.status] ?? "info"}>
                      {CARD_BADGE_LABEL[card.status] ?? card.status}
                    </Badge>
                  </header>

                  <div className="flex flex-1 flex-col p-4">
                    <div className="min-w-0">
                      <div className="eyebrow text-[0.5625rem]">Coverage</div>
                      <p className="mt-1 text-sm leading-snug text-foreground">{card.coverage}</p>
                      {percent !== null && (
                        <MeterBar
                          value={percent}
                          max={100}
                          color={missing ? "var(--unknown)" : CARD_EDGE[card.status]}
                          className="mt-2"
                          label={`${card.title} coverage ${percent.toFixed(0)} percent`}
                        />
                      )}
                    </div>

                    {card.action && (
                      <div className="mt-3 rounded-md border border-conditional/40 bg-conditional/10 px-3 py-2">
                        <div className="eyebrow text-conditional">Next step</div>
                        <p className="mt-1 text-[12px] leading-relaxed text-conditional/95">
                          {card.action}
                        </p>
                      </div>
                    )}

                    <SourceRail
                      className="mt-auto"
                      source={card.source}
                      retrievedAt={card.last_update}
                    />
                  </div>
                </article>
              );
            })}
          </div>
        )}
      </section>

      {/* ----------------------------------------------------- technical detail */}
      <section>
        <SectionRail title="Under the hood" aside="Row counts, sync runs, models and endpoints" />
        <details className="panel group" >
          <summary className="flex cursor-pointer select-none items-center justify-between gap-3 px-4 py-3">
            <span className="title-md whitespace-nowrap text-foreground">Technical details</span>
            <span className="eyebrow text-signal">
              <span className="group-open:hidden">Show</span>
              <span className="hidden group-open:inline">Hide</span>
            </span>
          </summary>
          <div className="space-y-4 border-t border-hairline p-4">
            <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
              {Object.entries(data.providers).map(([name, provider]) => {
                const ok = provider.configured ?? provider.enabled ?? false;
                return (
                  <Panel
                    key={name}
                    accent={ok ? "var(--legal)" : "var(--unknown)"}
                    padded={false}
                    className="px-4 py-3"
                  >
                    <div className="flex items-start justify-between gap-2">
                      <span className="title-md truncate text-foreground">
                        {name.replace(/_/g, " ")}
                      </span>
                      <Badge status={ok ? "pass" : "unavailable"}>
                        {ok ? "configured" : "not configured"}
                      </Badge>
                    </div>
                    {provider.package_version && (
                      <p className="data mt-2 text-[11px] text-muted">
                        {provider.upstream} · v{provider.package_version}
                      </p>
                    )}
                    {provider.provider && (
                      <p className="data mt-1 text-[11px] text-muted">
                        provider: {provider.provider}
                      </p>
                    )}
                    {provider.note && (
                      <p className="mt-1.5 text-[11px] leading-relaxed text-unavail">
                        {provider.note}
                      </p>
                    )}
                  </Panel>
                );
              })}
            </div>

            <Panel
              title="Tables"
              subtitle={`Last successful sync ${formatDate(
                data.last_successful_sync,
              )} · cap parameters loaded for ${data.cap_parameter_years.join(", ") || "—"}`}
            >
              <div className="scroll-thin overflow-x-auto">
                <table className="w-full min-w-[560px]">
                  <thead>
                    <tr className="border-b border-line">
                      <Th>Table</Th>
                      <Th numeric>Rows</Th>
                      <Th>Last retrieved</Th>
                      <Th>Freshness</Th>
                    </tr>
                  </thead>
                  <tbody>
                    {Object.entries(data.tables).map(([name, table]) => (
                      <tr key={name} className="border-b border-hairline">
                        <Td className="data whitespace-nowrap text-xs">{name}</Td>
                        <Td numeric>{table.rows.toLocaleString()}</Td>
                        <Td className="whitespace-nowrap text-xs text-muted">
                          {formatDate(table.last_retrieved_at)}
                        </Td>
                        <Td>
                          {/* Emptiness is checked first. An empty table has no maximum
                              retrieval time, so `stale === null`, and testing that
                              first labelled every empty table "derived" — `contracts`
                              at 0 rows read as a derived source rather than an empty
                              one. */}
                          {table.rows === 0 ? (
                            <Badge status="unavailable">empty</Badge>
                          ) : table.stale === null ? (
                            <Badge status="derived">derived</Badge>
                          ) : table.stale ? (
                            <Badge status="stale">stale</Badge>
                          ) : (
                            <Badge status="pass">fresh</Badge>
                          )}
                        </Td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </Panel>

            <div className="grid gap-3 lg:grid-cols-2">
              <Panel title="Recent sync runs">
                {data.recent_sync_runs.length === 0 ? (
                  <EmptyState
                    title="No sync runs recorded"
                    hint="Run `make sync-data` to pull a fresh snapshot from NBA.com."
                  />
                ) : (
                  <ul className="scroll-thin max-h-80 space-y-1.5 overflow-y-auto pr-1">
                    {data.recent_sync_runs.map((run, index) => (
                      <li key={index} className="flex flex-wrap items-center gap-2 text-sm">
                        <Badge status={run.status}>{run.status}</Badge>
                        <span className="data truncate text-xs">{run.job}</span>
                        <span className="data text-xs text-muted">{run.rows} rows</span>
                        <span className="ml-auto whitespace-nowrap text-[11px] text-faint">
                          {formatDate(run.finished_at ?? run.started_at)}
                        </span>
                        {run.error && (
                          <span className="w-full truncate text-[11px] text-illegal" title={run.error}>
                            {run.error}
                          </span>
                        )}
                      </li>
                    ))}
                  </ul>
                )}
              </Panel>

              <Panel
                title="Open data-quality issues"
                subtitle={
                  data.open_quality_issue_total > 0
                    ? `${data.open_quality_issue_total.toLocaleString()} open · showing the ${data.open_quality_issues.length} most recent`
                    : undefined
                }
              >
                {data.open_quality_issues.length === 0 ? (
                  <p className="text-sm text-muted">
                    No open issues from the latest validation pass.
                  </p>
                ) : (
                  <>
                    {/* The list is capped, so without the totals the real backlog is
                        unknowable from the page — 562 open rows rendered as 50 with no
                        indication that 512 were missing. */}
                    {Object.keys(data.open_quality_issue_counts ?? {}).length > 0 && (
                      <ul className="mb-3 flex flex-wrap gap-x-4 gap-y-1 border-b border-hairline pb-2.5 text-[11px]">
                        {Object.entries(data.open_quality_issue_counts).map(([check, count]) => (
                          <li key={check} className="whitespace-nowrap text-muted">
                            <span className="data text-foreground">{count.toLocaleString()}</span>{" "}
                            {check}
                          </li>
                        ))}
                      </ul>
                    )}
                    <ul className="scroll-thin max-h-80 space-y-2 overflow-y-auto pr-1">
                      {data.open_quality_issues.map((issue, index) => (
                        <li key={index} className="flex items-start gap-2 text-sm">
                          <Badge status={issue.severity === "error" ? "fail" : "warning"}>
                            {issue.severity}
                          </Badge>
                          <span className="min-w-0">
                            <span className="data block text-xs text-foreground">{issue.check}</span>
                            <span className="block text-xs leading-relaxed text-muted">
                              {issue.message}
                            </span>
                          </span>
                        </li>
                      ))}
                    </ul>
                    {data.open_quality_issues_truncated && (
                      <p className="mt-2 border-t border-hairline pt-2 text-[11px] text-unavail">
                        {(
                          data.open_quality_issue_total - data.open_quality_issues.length
                        ).toLocaleString()}{" "}
                        further open issues are not listed here.
                      </p>
                    )}
                  </>
                )}
              </Panel>
            </div>

            <Panel title="Active models" subtitle="Validation numbers as reported by the backend">
              {data.active_models.length === 0 ? (
                <EmptyState
                  title="No active models"
                  hint="Run `make train && make score` to fit and publish the impact model."
                />
              ) : (
                <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
                  {data.active_models.map((model) => (
                    <div
                      key={model.name}
                      className="rounded-lg border border-hairline bg-panel2 p-3"
                    >
                      <div className="title-md truncate text-foreground">{model.name}</div>
                      <div className="data mt-1 text-[11px] leading-relaxed text-muted">
                        {model.algorithm} · {model.version}
                      </div>
                      <div className="text-[11px] text-faint">
                        trained {formatDate(model.trained_at)}
                      </div>
                      <pre className="scroll-thin mt-2 max-h-40 overflow-auto rounded-md bg-court p-2 text-[10px] leading-relaxed text-muted">
                        {JSON.stringify(model.validation, null, 1)}
                      </pre>
                    </div>
                  ))}
                </div>
              )}
            </Panel>

            {data.asset_coverage && Object.keys(data.asset_coverage).length > 0 && (
              <Panel title="Asset coverage (raw)">
                <ul className="grid gap-x-6 gap-y-1 sm:grid-cols-2 lg:grid-cols-3">
                  {Object.entries(data.asset_coverage).map(([key, value]) => (
                    <li
                      key={key}
                      className="flex items-baseline justify-between gap-3 border-b border-hairline py-1"
                    >
                      <span className="data truncate text-xs text-muted">{key}</span>
                      <span className="data shrink-0 text-xs text-foreground">
                        {Number.isInteger(value) ? value : value.toFixed(3)}
                      </span>
                    </li>
                  ))}
                </ul>
              </Panel>
            )}

            {data.providers.nba_api?.endpoints && data.providers.nba_api.endpoints.length > 0 && (
              <Panel title="nba_api endpoint health" subtitle="This backend process only">
                <div className="scroll-thin overflow-x-auto">
                  <table className="w-full min-w-[640px]">
                    <thead>
                      <tr className="border-b border-line">
                        <Th>Endpoint</Th>
                        <Th numeric>OK</Th>
                        <Th numeric>Failed</Th>
                        <Th numeric>Last latency</Th>
                        <Th>Last error</Th>
                      </tr>
                    </thead>
                    <tbody>
                      {data.providers.nba_api.endpoints.map((endpoint) => (
                        <tr key={endpoint.endpoint} className="border-b border-hairline">
                          <Td className="data whitespace-nowrap text-xs">{endpoint.endpoint}</Td>
                          <Td numeric>{endpoint.successes}</Td>
                          <Td numeric>{endpoint.failures}</Td>
                          <Td numeric>
                            {endpoint.last_latency_ms
                              ? `${endpoint.last_latency_ms.toFixed(0)}ms`
                              : "—"}
                          </Td>
                          <Td className="text-[11px] text-illegal">{endpoint.last_error ?? "—"}</Td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </Panel>
            )}
          </div>
        </details>
      </section>
    </div>
  );
}

function SectionRail({ title, aside }: { title: string; aside?: string }) {
  return (
    <div className="mb-3">
      <div className="h-px w-full bg-gradient-to-r from-signal/60 to-transparent" />
      <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1 pt-2.5">
        <h2 className="title-lg whitespace-nowrap text-foreground">{title}</h2>
        {aside && <p className="text-[11px] text-faint">{aside}</p>}
      </div>
    </div>
  );
}
