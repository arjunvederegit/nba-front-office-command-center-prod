"use client";

/**
 * Data Status — fan-readable source cards up top (what's powering the product,
 * what to plug in next), a one-line summary strip, and the full technical
 * detail (tables, sync runs, quality issues, models, endpoint health) behind a
 * <details> expander. Honesty rule: when a critical source (contracts) is not
 * configured, the page never claims "all healthy".
 */

import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { formatDate } from "@/lib/format";
import type { DataHealth, SourceCard } from "@/lib/types";
import { Badge, Card, EmptyState, ErrorState, Spinner, Td, Th } from "@/components/ui";

const CARD_BADGE_STATUS: Record<SourceCard["status"], string> = {
  fresh: "pass",
  derived: "info",
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

export default function DataStatusPage() {
  const { data, error, refetch, isFetching } = useQuery({
    queryKey: ["data-health"],
    queryFn: () => api.get<DataHealth>("/data-health"),
  });

  if (error) return <ErrorState message={`Could not load data status: ${String(error)}`} />;
  if (!data) return <Spinner label="Loading data status…" />;

  const cards = data.source_cards ?? [];
  const contractsDown = cards.some(
    (c) => c.key === "contracts" && (c.status === "unavailable" || c.status === "failed"),
  );
  const attention = cards.filter(
    (c) => c.status === "unavailable" || c.status === "failed" || c.status === "stale",
  ).length;

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <h1 className="text-2xl font-bold">Data status</h1>
          <p className="mt-1 text-sm text-muted">
            What&apos;s powering RosterLab right now — and what to plug in next.
          </p>
        </div>
        <button
          type="button"
          onClick={() => refetch()}
          className="rounded-md border border-line px-3 py-1.5 text-sm hover:bg-panel"
        >
          {isFetching ? "Refreshing…" : "Refresh"}
        </button>
      </div>

      <div className="flex flex-wrap items-center gap-x-3 gap-y-1 rounded-lg border border-line bg-panel px-4 py-2.5 text-sm">
        <span>
          Season <span className="font-semibold">{data.current_season}</span>
        </span>
        <span aria-hidden className="text-muted">
          ·
        </span>
        <span>
          Cap year <span className="font-semibold">{data.cap_league_year}</span>
        </span>
        <span aria-hidden className="text-muted">
          ·
        </span>
        <span>
          Cache <span className="font-mono text-xs">{data.cache_backend}</span>
        </span>
        <span aria-hidden className="text-muted">
          ·
        </span>
        {contractsDown ? (
          <span className="font-medium text-warn">1 critical source not configured</span>
        ) : attention > 0 ? (
          <span className="font-medium text-warn">
            {attention} source{attention === 1 ? "" : "s"} need{attention === 1 ? "s" : ""}{" "}
            attention
          </span>
        ) : (
          <span className="font-medium text-pass">All sources healthy</span>
        )}
        <span className="ml-auto text-[11px] text-muted">
          generated {formatDate(data.generated_at)}
        </span>
      </div>

      {cards.length === 0 ? (
        <EmptyState
          title="No source summary available"
          hint="The backend did not return source cards; see technical details below."
        />
      ) : (
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
          {cards.map((card) => (
            <Card
              key={card.key}
              title={card.title}
              actions={
                <Badge status={CARD_BADGE_STATUS[card.status] ?? "info"}>
                  {CARD_BADGE_LABEL[card.status] ?? card.status}
                </Badge>
              }
            >
              <div className="space-y-2 text-sm">
                <p>{card.coverage}</p>
                <p className="text-xs text-muted">Source: {card.source}</p>
                <p className="text-xs text-muted">Last update: {formatDate(card.last_update)}</p>
                {card.action && (
                  <div className="rounded-md border border-warn/40 bg-warn/10 px-3 py-2 text-xs leading-relaxed text-warn">
                    <span className="font-semibold">Next step:</span> {card.action}
                  </div>
                )}
              </div>
            </Card>
          ))}
        </div>
      )}

      <details className="rounded-lg border border-line bg-panel">
        <summary className="cursor-pointer select-none px-4 py-3 text-sm font-semibold tracking-wide hover:bg-panel2">
          Technical details
        </summary>
        <div className="space-y-4 border-t border-line p-4">
          <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
            {Object.entries(data.providers).map(([name, p]) => {
              const ok = p.configured ?? p.enabled ?? false;
              return (
                <Card key={name} title={name.replace("_", " ")}>
                  <div className="space-y-2 text-sm">
                    <Badge status={ok ? "pass" : "unavailable"}>
                      {ok ? "configured" : "not configured"}
                    </Badge>
                    {p.package_version && (
                      <p className="text-xs text-muted">
                        {p.upstream} · v{p.package_version}
                      </p>
                    )}
                    {p.provider && <p className="text-xs text-muted">provider: {p.provider}</p>}
                    {p.note && <p className="text-xs leading-relaxed text-unavail">{p.note}</p>}
                  </div>
                </Card>
              );
            })}
          </div>

          <Card
            title="Tables"
            subtitle={`last successful sync: ${formatDate(data.last_successful_sync)} · cap parameters loaded: ${data.cap_parameter_years.join(", ")}`}
          >
            <div className="scroll-thin overflow-x-auto">
              <table className="w-full min-w-[560px]">
                <thead>
                  <tr className="border-b border-line">
                    <Th>Table</Th>
                    <Th className="text-right">Rows</Th>
                    <Th>Last retrieved</Th>
                    <Th>Freshness</Th>
                  </tr>
                </thead>
                <tbody>
                  {Object.entries(data.tables).map(([name, t]) => (
                    <tr key={name} className="border-b border-line/50">
                      <Td className="font-mono text-xs">{name}</Td>
                      <Td className="text-right font-mono">{t.rows.toLocaleString()}</Td>
                      <Td className="text-xs text-muted">{formatDate(t.last_retrieved_at)}</Td>
                      <Td>
                        {t.stale === null ? (
                          <Badge status="info">derived</Badge>
                        ) : t.rows === 0 ? (
                          <Badge status="unavailable">empty</Badge>
                        ) : t.stale ? (
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
          </Card>

          <div className="grid gap-4 lg:grid-cols-2">
            <Card title="Recent sync runs">
              {data.recent_sync_runs.length === 0 ? (
                <EmptyState title="No sync runs recorded" hint="Run `make sync-data`." />
              ) : (
                <ul className="scroll-thin max-h-80 space-y-1.5 overflow-y-auto pr-1">
                  {data.recent_sync_runs.map((run, i) => (
                    <li key={i} className="flex flex-wrap items-center gap-2 text-sm">
                      <Badge status={run.status}>{run.status}</Badge>
                      <span className="font-mono text-xs">{run.job}</span>
                      <span className="text-xs text-muted">{run.rows} rows</span>
                      <span className="ml-auto text-[11px] text-muted">
                        {formatDate(run.finished_at ?? run.started_at)}
                      </span>
                      {run.error && (
                        <span className="w-full truncate text-[11px] text-fail" title={run.error}>
                          {run.error}
                        </span>
                      )}
                    </li>
                  ))}
                </ul>
              )}
            </Card>

            <Card title="Open data-quality issues">
              {data.open_quality_issues.length === 0 ? (
                <p className="text-sm text-muted">No open issues from the latest validation pass.</p>
              ) : (
                <ul className="scroll-thin max-h-80 space-y-1.5 overflow-y-auto pr-1">
                  {data.open_quality_issues.map((issue, i) => (
                    <li key={i} className="flex items-start gap-2 text-sm">
                      <Badge status={issue.severity === "error" ? "fail" : "warning"}>
                        {issue.severity}
                      </Badge>
                      <div>
                        <span className="font-mono text-xs">{issue.check}</span>
                        <p className="text-xs text-muted">{issue.message}</p>
                      </div>
                    </li>
                  ))}
                </ul>
              )}
            </Card>
          </div>

          <Card title="Active models">
            {data.active_models.length === 0 ? (
              <EmptyState title="No active models" hint="Run `make train && make score`." />
            ) : (
              <div className="grid gap-3 md:grid-cols-3">
                {data.active_models.map((m) => (
                  <div key={m.name} className="rounded-md border border-line bg-panel2 p-3 text-sm">
                    <div className="font-semibold">{m.name}</div>
                    <div className="text-xs text-muted">
                      {m.algorithm} · {m.version} · trained {formatDate(m.trained_at)}
                    </div>
                    <pre className="scroll-thin mt-2 max-h-40 overflow-auto rounded bg-background p-2 text-[10px] leading-relaxed text-muted">
                      {JSON.stringify(m.validation, null, 1)}
                    </pre>
                  </div>
                ))}
              </div>
            )}
          </Card>

          {data.asset_coverage && Object.keys(data.asset_coverage).length > 0 && (
            <Card title="Asset coverage (raw)">
              <ul className="grid gap-x-6 gap-y-1 text-sm sm:grid-cols-2 lg:grid-cols-3">
                {Object.entries(data.asset_coverage).map(([key, value]) => (
                  <li key={key} className="flex justify-between gap-3">
                    <span className="font-mono text-xs text-muted">{key}</span>
                    <span className="font-mono text-xs">
                      {Number.isInteger(value) ? value : value.toFixed(3)}
                    </span>
                  </li>
                ))}
              </ul>
            </Card>
          )}

          {data.providers.nba_api?.endpoints && data.providers.nba_api.endpoints.length > 0 && (
            <Card title="nba_api endpoint health (this process)">
              <div className="scroll-thin overflow-x-auto">
                <table className="w-full min-w-[560px]">
                  <thead>
                    <tr className="border-b border-line">
                      <Th>Endpoint</Th>
                      <Th className="text-right">OK</Th>
                      <Th className="text-right">Failed</Th>
                      <Th className="text-right">Last latency</Th>
                      <Th>Last error</Th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.providers.nba_api.endpoints.map((e) => (
                      <tr key={e.endpoint} className="border-b border-line/50">
                        <Td className="font-mono text-xs">{e.endpoint}</Td>
                        <Td className="text-right font-mono">{e.successes}</Td>
                        <Td className="text-right font-mono">{e.failures}</Td>
                        <Td className="text-right font-mono">
                          {e.last_latency_ms ? `${e.last_latency_ms.toFixed(0)}ms` : "—"}
                        </Td>
                        <Td className="text-[11px] text-fail">{e.last_error ?? "—"}</Td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </Card>
          )}
        </div>
      </details>
    </div>
  );
}
