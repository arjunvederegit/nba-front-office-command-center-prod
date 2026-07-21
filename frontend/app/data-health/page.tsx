"use client";

import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { formatDate } from "@/lib/format";
import type { DataHealth } from "@/lib/types";
import { Badge, Card, EmptyState, ErrorState, Spinner, Td, Th } from "@/components/ui";

export default function DataHealthPage() {
  const { data, error, refetch, isFetching } = useQuery({
    queryKey: ["data-health"],
    queryFn: () => api.get<DataHealth>("/data-health"),
  });

  if (error) return <ErrorState message={`Could not load data health: ${String(error)}`} />;
  if (!data) return <Spinner label="Loading data health…" />;

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">Data health</h1>
          <p className="mt-1 text-sm text-muted">
            Season {data.current_season} · cap league year {data.cap_league_year} · cache:{" "}
            {data.cache_backend} · generated {formatDate(data.generated_at)}
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
                <li key={i} className="flex items-center gap-2 text-sm">
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
            <p className="text-sm text-pass">No open issues from the latest validation pass.</p>
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
      </Card>

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
  );
}
