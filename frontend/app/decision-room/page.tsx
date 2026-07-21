"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useState } from "react";
import { api } from "@/lib/api";
import { COMPONENT_LABEL, NEED_LABEL, formatDate } from "@/lib/format";
import type { RosterResponse, Scenario, Team, TeamNeedItem } from "@/lib/types";
import {
  Badge,
  Card,
  EmptyState,
  ErrorState,
  MeterBar,
  SourceLine,
  Spinner,
} from "@/components/ui";

const STRATEGIES = [
  ["contend", "Contend now"],
  ["improve", "Improve without sacrificing flexibility"],
  ["retool", "Re-tool around current core"],
  ["rebuild", "Rebuild"],
  ["youth", "Acquire young upside"],
  ["cap_relief", "Reduce salary or tax"],
  ["custom", "Custom"],
] as const;

const WEIGHT_KEYS = ["performance", "fit", "contract", "timeline", "assets", "risk"] as const;

export default function DecisionRoomPage() {
  const queryClient = useQueryClient();
  const { data: teams, error: teamsError } = useQuery({
    queryKey: ["teams"],
    queryFn: () => api.get<Team[]>("/teams"),
  });
  const { data: scenarios } = useQuery({
    queryKey: ["scenarios"],
    queryFn: () => api.get<Scenario[]>("/scenarios"),
  });

  const [teamId, setTeamId] = useState<string>("");
  const [name, setName] = useState("");
  const [strategy, setStrategy] = useState<string>("contend");
  const [horizon, setHorizon] = useState(1);
  const [risk, setRisk] = useState("balanced");
  const [weights, setWeights] = useState<Record<string, number>>({
    performance: 22, fit: 18, contract: 14, timeline: 16, assets: 15, risk: 15,
  });
  const [untouchables, setUntouchables] = useState<string[]>([]);
  const [preferredOut, setPreferredOut] = useState<string[]>([]);

  const selectedTeam = teams?.find((t) => t.id === teamId) ?? null;

  const { data: roster } = useQuery({
    queryKey: ["roster", teamId],
    queryFn: () => api.get<RosterResponse>(`/teams/${teamId}/roster`),
    enabled: !!teamId,
  });

  const create = useMutation({
    mutationFn: () =>
      api.post<Scenario>("/scenarios", {
        name: name || `${selectedTeam?.abbreviation} — ${strategy}`,
        focal_team_id: teamId,
        strategy,
        horizon_years: horizon,
        risk_tolerance: risk,
        untouchable_player_ids: untouchables,
        preferred_outgoing_player_ids: preferredOut,
        weights: Object.fromEntries(
          WEIGHT_KEYS.map((k) => [k, (weights[k] ?? 0) / 100]),
        ),
      }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["scenarios"] }),
  });

  const weightTotal = WEIGHT_KEYS.reduce((sum, k) => sum + (weights[k] ?? 0), 0);

  if (teamsError) return <ErrorState message={`Could not load teams: ${String(teamsError)}`} />;
  if (!teams) return <Spinner label="Loading teams…" />;

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold">Decision Room</h1>
        <p className="mt-1 text-sm text-muted">
          Define the strategic frame first — the same trade can be right for a contender and wrong
          for a rebuild.
        </p>
      </div>

      <div className="grid gap-4 lg:grid-cols-[380px_1fr]">
        <Card title="1 · Scenario setup" subtitle="Persisted; drives evaluation weights">
          <div className="space-y-4">
            <label className="block text-sm">
              <span className="text-muted">Focal team</span>
              <select
                value={teamId}
                onChange={(e) => setTeamId(e.target.value)}
                className="mt-1 w-full rounded-md border border-line bg-panel2 px-2 py-1.5"
              >
                <option value="">Select a team…</option>
                {teams.map((t) => (
                  <option key={t.id} value={t.id}>
                    {t.full_name}
                  </option>
                ))}
              </select>
            </label>
            <label className="block text-sm">
              <span className="text-muted">Scenario name</span>
              <input
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="e.g. Deadline 2027 — win-now push"
                className="mt-1 w-full rounded-md border border-line bg-panel2 px-2 py-1.5"
              />
            </label>
            <label className="block text-sm">
              <span className="text-muted">Strategy</span>
              <select
                value={strategy}
                onChange={(e) => setStrategy(e.target.value)}
                className="mt-1 w-full rounded-md border border-line bg-panel2 px-2 py-1.5"
              >
                {STRATEGIES.map(([value, label]) => (
                  <option key={value} value={value}>
                    {label}
                  </option>
                ))}
              </select>
            </label>
            <div className="grid grid-cols-2 gap-3">
              <label className="block text-sm">
                <span className="text-muted">Horizon</span>
                <select
                  value={horizon}
                  onChange={(e) => setHorizon(Number(e.target.value))}
                  className="mt-1 w-full rounded-md border border-line bg-panel2 px-2 py-1.5"
                >
                  {[1, 2, 3, 5].map((y) => (
                    <option key={y} value={y}>
                      {y === 1 ? "Current season" : `${y} years`}
                    </option>
                  ))}
                </select>
              </label>
              <label className="block text-sm">
                <span className="text-muted">Risk tolerance</span>
                <select
                  value={risk}
                  onChange={(e) => setRisk(e.target.value)}
                  className="mt-1 w-full rounded-md border border-line bg-panel2 px-2 py-1.5"
                >
                  {["conservative", "balanced", "aggressive"].map((r) => (
                    <option key={r} value={r}>
                      {r}
                    </option>
                  ))}
                </select>
              </label>
            </div>

            <fieldset>
              <legend className="text-sm text-muted">
                Importance weights{" "}
                <span className={weightTotal === 100 ? "text-pass" : "text-warn"}>
                  (total {weightTotal} — normalized to 100%)
                </span>
              </legend>
              <div className="mt-2 space-y-2">
                {WEIGHT_KEYS.map((key) => (
                  <label key={key} className="flex items-center gap-2 text-xs">
                    <span className="w-24 text-muted">{COMPONENT_LABEL[key]}</span>
                    <input
                      type="range"
                      min={0}
                      max={40}
                      value={weights[key] ?? 0}
                      onChange={(e) =>
                        setWeights((w) => ({ ...w, [key]: Number(e.target.value) }))
                      }
                      className="flex-1 accent-sky-400"
                      aria-label={`${COMPONENT_LABEL[key]} weight`}
                    />
                    <span className="w-8 text-right font-mono">{weights[key] ?? 0}</span>
                  </label>
                ))}
              </div>
            </fieldset>

            {roster && (
              <fieldset>
                <legend className="text-sm text-muted">Untouchables / preferred outgoing</legend>
                <div className="scroll-thin mt-2 max-h-44 space-y-1 overflow-y-auto pr-1">
                  {roster.roster.map((p) => (
                    <div key={p.player_id} className="flex items-center gap-2 text-xs">
                      <span className="flex-1 truncate">{p.name}</span>
                      <button
                        type="button"
                        onClick={() =>
                          setUntouchables((u) =>
                            u.includes(p.player_id)
                              ? u.filter((x) => x !== p.player_id)
                              : [...u, p.player_id],
                          )
                        }
                        className={`rounded border px-1.5 py-0.5 ${
                          untouchables.includes(p.player_id)
                            ? "border-fail/50 bg-fail/15 text-fail"
                            : "border-line text-muted hover:text-foreground"
                        }`}
                      >
                        untouchable
                      </button>
                      <button
                        type="button"
                        onClick={() =>
                          setPreferredOut((u) =>
                            u.includes(p.player_id)
                              ? u.filter((x) => x !== p.player_id)
                              : [...u, p.player_id],
                          )
                        }
                        className={`rounded border px-1.5 py-0.5 ${
                          preferredOut.includes(p.player_id)
                            ? "border-warn/50 bg-warn/15 text-warn"
                            : "border-line text-muted hover:text-foreground"
                        }`}
                      >
                        shop
                      </button>
                    </div>
                  ))}
                </div>
              </fieldset>
            )}

            <button
              type="button"
              disabled={!teamId || create.isPending}
              onClick={() => create.mutate()}
              className="w-full rounded-md bg-accent px-4 py-2 text-sm font-semibold text-background transition hover:brightness-110 disabled:opacity-40"
            >
              {create.isPending ? "Saving…" : "Save scenario"}
            </button>
            {create.isSuccess && (
              <p className="text-xs text-pass">
                Scenario saved. Open the{" "}
                <Link className="underline" href="/trade-builder">
                  trade builder
                </Link>{" "}
                to construct alternatives.
              </p>
            )}
            {create.isError && <ErrorState message={String(create.error)} />}
          </div>
        </Card>

        <div className="space-y-4">
          {selectedTeam ? (
            <TeamDiagnosis teamId={selectedTeam.id} />
          ) : (
            <EmptyState
              title="Select a focal team to see its roster diagnosis"
              hint="Standings, statistical profile, computed needs, payroll status and freshness."
            />
          )}

          <Card title="Saved scenarios">
            {scenarios && scenarios.length > 0 ? (
              <ul className="divide-y divide-line">
                {scenarios.map((s) => (
                  <li key={s.id} className="flex items-center gap-3 py-2 text-sm">
                    <Badge status="info">{s.focal_team.abbreviation}</Badge>
                    <span className="flex-1">{s.name}</span>
                    <span className="text-xs text-muted">{s.strategy}</span>
                    <span className="text-xs text-muted">{formatDate(s.created_at)}</span>
                    <Link
                      href={`/trade-builder?scenario=${s.id}`}
                      className="text-xs text-accent underline"
                    >
                      build trades →
                    </Link>
                  </li>
                ))}
              </ul>
            ) : (
              <EmptyState title="No scenarios yet" hint="Save one on the left to get started." />
            )}
          </Card>
        </div>
      </div>
    </div>
  );
}

function TeamDiagnosis({ teamId }: { teamId: string }) {
  const { data: needs } = useQuery({
    queryKey: ["needs", teamId],
    queryFn: () =>
      api.get<{ computed: boolean; note: string | null; needs: TeamNeedItem[]; method: string }>(
        `/teams/${teamId}/needs`,
      ),
  });
  const { data: roster } = useQuery({
    queryKey: ["roster", teamId],
    queryFn: () => api.get<RosterResponse>(`/teams/${teamId}/roster`),
  });

  return (
    <Card
      title="2 · Roster diagnosis"
      subtitle={
        roster ? (
          <SourceLine retrievedAt={roster.source_retrieved_at} source={roster.source} />
        ) : undefined
      }
      actions={
        <Link href={`/teams/${teamId}`} className="text-xs text-accent underline">
          full team page →
        </Link>
      }
    >
      {!needs ? (
        <Spinner />
      ) : needs.needs.length === 0 ? (
        <EmptyState
          title="Team needs not computed yet"
          hint={needs.note ?? "Run `make score` on the backend."}
        />
      ) : (
        <div className="grid gap-x-8 gap-y-2 sm:grid-cols-2">
          {needs.needs.slice(0, 10).map((n) => (
            <div key={n.need_key} title={n.explanation}>
              <div className="flex justify-between text-xs">
                <span>{NEED_LABEL[n.need_key] ?? n.need_key}</span>
                <span className="text-muted">severity {(n.severity * 100).toFixed(0)}</span>
              </div>
              <MeterBar
                value={n.severity}
                color={n.severity > 0.5 ? "var(--fail)" : n.severity > 0.25 ? "var(--warn)" : "var(--pass)"}
                className="mt-1"
              />
            </div>
          ))}
          <p className="text-[11px] text-muted sm:col-span-2">
            Needs are computed from transparent percentile rules over real team statistics — hover
            for the explanation. No LLM involvement.
          </p>
        </div>
      )}
    </Card>
  );
}
