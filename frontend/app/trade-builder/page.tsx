"use client";

import { DndContext, DragOverlay, useDraggable, useDroppable } from "@dnd-kit/core";
import type { DragEndEvent, DragStartEvent } from "@dnd-kit/core";
import { useMutation, useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useMemo, useState } from "react";
import { api } from "@/lib/api";
import { LEGALITY_LABEL, money, tei } from "@/lib/format";
import type {
  GeneratedCandidate,
  LegalityResponse,
  PickMove,
  PlayerMove,
  RosterResponse,
  Scenario,
  Team,
  TradeDetail,
} from "@/lib/types";
import {
  Badge,
  Card,
  EmptyState,
  ErrorState,
  PlayerAvatar,
  Spinner,
} from "@/components/ui";

export default function TradeBuilderPage() {
  return (
    <Suspense fallback={<Spinner label="Loading builder…" />}>
      <TradeBuilder />
    </Suspense>
  );
}

function TradeBuilder() {
  const searchParams = useSearchParams();
  const router = useRouter();
  const scenarioId = searchParams.get("scenario");
  const loadTradeId = searchParams.get("load");

  const { data: teams } = useQuery({ queryKey: ["teams"], queryFn: () => api.get<Team[]>("/teams") });
  const { data: scenario } = useQuery({
    queryKey: ["scenario", scenarioId],
    queryFn: () => api.get<Scenario>(`/scenarios/${scenarioId}`),
    enabled: !!scenarioId,
  });

  const [teamIds, setTeamIds] = useState<string[]>([]);
  // moves: player_id -> destination team_id (origin derived from roster)
  const [moves, setMoves] = useState<Record<string, string>>({});
  const [picks, setPicks] = useState<PickMove[]>([]);
  const [tradeName, setTradeName] = useState("");
  const [activeDrag, setActiveDrag] = useState<{ id: string; name: string } | null>(null);

  // Preload from a saved trade (clone & modify) — render-phase state adjustment
  const { data: loadedTrade } = useQuery({
    queryKey: ["trade", loadTradeId],
    queryFn: () => api.get<TradeDetail>(`/trades/${loadTradeId}`),
    enabled: !!loadTradeId,
  });
  const [appliedTradeId, setAppliedTradeId] = useState<string | null>(null);
  if (loadedTrade && loadedTrade.id !== appliedTradeId) {
    setAppliedTradeId(loadedTrade.id);
    setTeamIds(loadedTrade.teams.map((t) => t.team_id));
    const nextMoves: Record<string, string> = {};
    const nextPicks: PickMove[] = [];
    for (const asset of loadedTrade.assets) {
      if (asset.asset_type === "player" && asset.player_id) {
        nextMoves[asset.player_id] = asset.to_team_id;
      } else if (asset.asset_type === "pick" && asset.draft_year && asset.round_number) {
        nextPicks.push({
          from_team_id: asset.from_team_id,
          to_team_id: asset.to_team_id,
          draft_year: asset.draft_year,
          round_number: asset.round_number,
          protections: asset.protections,
          is_hypothetical: true,
        });
      }
    }
    setMoves(nextMoves);
    setPicks(nextPicks);
    setTradeName(`${loadedTrade.name} (copy)`);
  }

  const [appliedScenarioTeam, setAppliedScenarioTeam] = useState<string | null>(null);
  if (scenario && teamIds.length === 0 && appliedScenarioTeam !== scenario.id) {
    setAppliedScenarioTeam(scenario.id);
    setTeamIds([scenario.focal_team_id]);
  }

  const rosters = useQuery({
    queryKey: ["rosters", teamIds],
    queryFn: async () => {
      const result: Record<string, RosterResponse> = {};
      await Promise.all(
        teamIds.map(async (id) => {
          result[id] = await api.get<RosterResponse>(`/teams/${id}/roster`);
        }),
      );
      return result;
    },
    enabled: teamIds.length > 0,
  });

  const originOf = useMemo(() => {
    const map: Record<string, string> = {};
    if (rosters.data) {
      for (const [tid, roster] of Object.entries(rosters.data)) {
        for (const p of roster.roster) map[p.player_id] = tid;
      }
    }
    return map;
  }, [rosters.data]);

  const playerMoves: PlayerMove[] = useMemo(
    () =>
      Object.entries(moves)
        .filter(([pid, to]) => originOf[pid] && originOf[pid] !== to)
        .map(([pid, to]) => ({ player_id: pid, from_team_id: originOf[pid], to_team_id: to })),
    [moves, originOf],
  );

  // Live backend validation (the frontend never decides legality)
  const [validation, setValidation] = useState<LegalityResponse | null>(null);
  const [validating, setValidating] = useState(false);
  useEffect(() => {
    const handle = setTimeout(async () => {
      if (teamIds.length < 2 || playerMoves.length === 0) {
        setValidation(null);
        return;
      }
      setValidating(true);
      try {
        const result = await api.post<LegalityResponse>("/trades/validate", {
          team_ids: teamIds,
          player_moves: playerMoves,
          pick_moves: picks,
        });
        setValidation(result);
      } catch {
        setValidation(null);
      } finally {
        setValidating(false);
      }
    }, 500);
    return () => clearTimeout(handle);
  }, [teamIds, playerMoves, picks]);

  const saveTrade = useMutation({
    mutationFn: () =>
      api.post<TradeDetail>("/trades", {
        name: tradeName || "Untitled trade",
        scenario_id: scenarioId,
        team_ids: teamIds,
        player_moves: playerMoves,
        pick_moves: picks,
      }),
    onSuccess: (trade) => router.push(`/trades/${trade.id}`),
  });

  const generate = useMutation({
    mutationFn: () =>
      api.post<{ candidates: GeneratedCandidate[]; note: string; target_needs: string[] }>(
        "/trades/generate",
        scenarioId
          ? { scenario_id: scenarioId, max_candidates: 6 }
          : { focal_team_id: teamIds[0], max_candidates: 6 },
      ),
  });

  function addTeam(id: string) {
    if (id && !teamIds.includes(id) && teamIds.length < 3) setTeamIds([...teamIds, id]);
  }
  function removeTeam(id: string) {
    setTeamIds(teamIds.filter((t) => t !== id));
    setMoves((m) =>
      Object.fromEntries(Object.entries(m).filter(([pid, to]) => to !== id && originOf[pid] !== id)),
    );
    setPicks((p) => p.filter((x) => x.from_team_id !== id && x.to_team_id !== id));
  }
  function movePlayer(playerId: string, toTeamId: string) {
    setMoves((m) => {
      const origin = originOf[playerId];
      if (origin === toTeamId) {
        const rest = { ...m };
        delete rest[playerId];
        return rest;
      }
      return { ...m, [playerId]: toTeamId };
    });
  }

  function onDragStart(event: DragStartEvent) {
    const data = event.active.data.current as { name?: string } | undefined;
    setActiveDrag({ id: String(event.active.id), name: data?.name ?? "" });
  }
  function onDragEnd(event: DragEndEvent) {
    setActiveDrag(null);
    const playerId = String(event.active.id);
    const over = event.over?.id;
    if (over) movePlayer(playerId, String(over));
  }

  const loaded = teams ?? [];

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold">Trade Builder</h1>
          <p className="text-sm text-muted">
            Drag players between teams (or use the per-player buttons). Legality is checked by the
            backend as you build{scenario ? ` · scenario: ${scenario.name}` : ""}.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <select
            aria-label="Add team to trade"
            className="rounded-md border border-line bg-panel2 px-2 py-1.5 text-sm"
            value=""
            onChange={(e) => addTeam(e.target.value)}
          >
            <option value="">{teamIds.length >= 3 ? "Max 3 teams" : "+ Add team…"}</option>
            {loaded
              .filter((t) => !teamIds.includes(t.id))
              .map((t) => (
                <option key={t.id} value={t.id}>
                  {t.full_name}
                </option>
              ))}
          </select>
          <button
            type="button"
            onClick={() => generate.mutate()}
            disabled={generate.isPending || (teamIds.length === 0 && !scenarioId)}
            className="rounded-md border border-line px-3 py-1.5 text-sm hover:bg-panel disabled:opacity-40"
          >
            {generate.isPending ? "Searching…" : "Generate ideas"}
          </button>
        </div>
      </div>

      {generate.data && (
        <Card title="Generated candidates" subtitle={generate.data.note}>
          {generate.data.candidates.length === 0 ? (
            <EmptyState title="No candidates cleared the constraints" hint="Loosen untouchables or run `make score`." />
          ) : (
            <div className="grid gap-2 md:grid-cols-2">
              {generate.data.candidates.map((c, i) => (
                <div key={i} className="rounded-md border border-line bg-panel2 p-3 text-sm">
                  <div className="flex items-center justify-between">
                    <span className="font-semibold">vs {c.counterparty.abbreviation}</span>
                    <div className="flex gap-1">
                      <Badge status={c.legality_status}>{LEGALITY_LABEL[c.legality_status]}</Badge>
                      <Badge status="info">you {c.focal_utility.toFixed(0)} · them {c.counterparty_utility.toFixed(0)}</Badge>
                    </div>
                  </div>
                  <p className="mt-1 text-xs text-muted">
                    Out: {c.outgoing.map((p) => p.name).join(", ")} · In:{" "}
                    {c.incoming.map((p) => p.name).join(", ")}
                  </p>
                  <p className="mt-1 text-[11px] text-muted">{c.rationale}</p>
                  <button
                    type="button"
                    className="mt-2 text-xs text-accent underline"
                    onClick={() => {
                      addTeam(c.counterparty.team_id);
                      const next: Record<string, string> = {};
                      for (const p of c.outgoing) next[p.player_id] = c.counterparty.team_id;
                      for (const p of c.incoming) next[p.player_id] = teamIds[0];
                      setMoves(next);
                    }}
                  >
                    load into builder
                  </button>
                </div>
              ))}
            </div>
          )}
        </Card>
      )}

      {teamIds.length === 0 && (
        <EmptyState
          title="Add 2–3 teams to start constructing a trade"
          hint="Tip: open the Decision Room first to set a scenario, then come back."
        />
      )}

      <DndContext onDragStart={onDragStart} onDragEnd={onDragEnd}>
        <div className={`grid gap-4 ${teamIds.length === 3 ? "lg:grid-cols-3" : "lg:grid-cols-2"}`}>
          {teamIds.map((tid) => (
            <TeamColumn
              key={tid}
              teamId={tid}
              teams={loaded}
              teamIds={teamIds}
              roster={rosters.data?.[tid]}
              moves={moves}
              originOf={originOf}
              validation={validation}
              onRemove={() => removeTeam(tid)}
              onMove={movePlayer}
              picks={picks}
              setPicks={setPicks}
            />
          ))}
        </div>
        <DragOverlay>
          {activeDrag && (
            <div className="flex items-center gap-2 rounded-md border border-accent bg-panel px-2 py-1 text-sm shadow-lg">
              <PlayerAvatar name={activeDrag.name} size={22} />
              {activeDrag.name}
            </div>
          )}
        </DragOverlay>
      </DndContext>

      {teamIds.length >= 2 && (
        <div className="grid gap-4 lg:grid-cols-[1fr_320px]">
          <Card
            title="Legality (backend-authoritative)"
            subtitle={validating ? "checking…" : validation ? `league year ${validation.league_year} · cap: ${validation.cap_parameters_source}` : "make a move to validate"}
          >
            {!validation ? (
              <EmptyState title="No validation yet" hint="Move at least one player between teams." />
            ) : (
              <div className="space-y-3">
                <div className="flex flex-wrap items-center gap-2">
                  <Badge status={validation.overall_status} className="text-sm">
                    {LEGALITY_LABEL[validation.overall_status]}
                  </Badge>
                  {!validation.contract_provider_configured && (
                    <span className="text-xs text-unavail">
                      No contract provider configured — salary rules report “unavailable” and the
                      result can be at best conditionally valid.
                    </span>
                  )}
                </div>
                <ul className="space-y-1.5">
                  {validation.rule_results.map((r, i) => (
                    <li key={i} className="flex items-start gap-2 text-sm">
                      <Badge status={r.status} className="mt-0.5 shrink-0">
                        {r.status}
                      </Badge>
                      <span className="font-mono text-[11px] text-muted shrink-0 mt-1">
                        {r.rule_code}
                      </span>
                      <span className="text-xs leading-relaxed">{r.message}</span>
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </Card>

          <Card title="Save alternative">
            <div className="space-y-3">
              <input
                value={tradeName}
                onChange={(e) => setTradeName(e.target.value)}
                placeholder="Name this alternative…"
                className="w-full rounded-md border border-line bg-panel2 px-2 py-1.5 text-sm"
                aria-label="Trade name"
              />
              <button
                type="button"
                disabled={playerMoves.length === 0 || saveTrade.isPending}
                onClick={() => saveTrade.mutate()}
                className="w-full rounded-md bg-accent px-4 py-2 text-sm font-semibold text-background hover:brightness-110 disabled:opacity-40"
              >
                {saveTrade.isPending ? "Saving…" : "Save & open full evaluation"}
              </button>
              {saveTrade.isError && <ErrorState message={String(saveTrade.error)} />}
              <p className="text-[11px] text-muted">
                Saved alternatives appear in{" "}
                <Link href="/compare" className="underline">
                  Compare
                </Link>{" "}
                and can be cloned via “load” on their detail page.
              </p>
            </div>
          </Card>
        </div>
      )}
    </div>
  );
}

function TeamColumn({
  teamId,
  teams,
  teamIds,
  roster,
  moves,
  originOf,
  validation,
  onRemove,
  onMove,
  picks,
  setPicks,
}: {
  teamId: string;
  teams: Team[];
  teamIds: string[];
  roster?: RosterResponse;
  moves: Record<string, string>;
  originOf: Record<string, string>;
  validation: LegalityResponse | null;
  onRemove: () => void;
  onMove: (playerId: string, toTeamId: string) => void;
  picks: PickMove[];
  setPicks: React.Dispatch<React.SetStateAction<PickMove[]>>;
}) {
  const team = teams.find((t) => t.id === teamId);
  const { setNodeRef, isOver } = useDroppable({ id: teamId });
  const teamLegality = validation?.teams[teamId];

  const staying = roster?.roster.filter((p) => (moves[p.player_id] ?? teamId) === teamId) ?? [];
  const incoming = Object.entries(moves)
    .filter(([pid, to]) => to === teamId && originOf[pid] !== teamId)
    .map(([pid]) => pid);
  const outgoing = roster?.roster.filter((p) => moves[p.player_id] && moves[p.player_id] !== teamId) ?? [];

  const [pickYear, setPickYear] = useState(2027);
  const [pickTo, setPickTo] = useState("");

  return (
    <div
      ref={setNodeRef}
      className={`rounded-lg border bg-panel transition-colors ${isOver ? "border-accent" : "border-line"}`}
    >
      <header className="flex items-center justify-between border-b border-line px-3 py-2">
        <div className="flex items-center gap-2">
          <span className="rounded bg-panel2 px-1.5 py-0.5 font-mono text-xs">{team?.abbreviation}</span>
          <span className="text-sm font-semibold">{team?.nickname ?? team?.full_name}</span>
        </div>
        <div className="flex items-center gap-2">
          {teamLegality && (
            <span className="text-[11px] text-muted">
              roster {teamLegality.roster_before}→{teamLegality.roster_after} · in{" "}
              {money(teamLegality.incoming_salary)} / out {money(teamLegality.outgoing_salary)}
            </span>
          )}
          <button
            type="button"
            onClick={onRemove}
            aria-label={`Remove ${team?.full_name} from trade`}
            className="rounded px-1.5 text-muted hover:bg-panel2 hover:text-fail"
          >
            ×
          </button>
        </div>
      </header>

      {incoming.length > 0 && (
        <div className="border-b border-line bg-pass/5 px-3 py-2">
          <div className="text-[11px] font-semibold uppercase tracking-wide text-pass">Incoming</div>
          {incoming.map((pid) => (
            <IncomingChip key={pid} playerId={pid} onReturn={() => onMove(pid, originOf[pid])} />
          ))}
        </div>
      )}
      {outgoing.length > 0 && (
        <div className="border-b border-line bg-fail/5 px-3 py-2">
          <div className="text-[11px] font-semibold uppercase tracking-wide text-fail">Outgoing</div>
          {outgoing.map((p) => (
            <div key={p.player_id} className="flex items-center justify-between py-0.5 text-sm">
              <span className="text-muted line-through">{p.name}</span>
              <button
                type="button"
                onClick={() => onMove(p.player_id, teamId)}
                className="text-xs text-accent underline"
              >
                undo
              </button>
            </div>
          ))}
        </div>
      )}

      <div className="scroll-thin max-h-[420px] overflow-y-auto p-2">
        {!roster ? (
          <Spinner label="Loading roster…" />
        ) : (
          staying.map((p) => (
            <DraggablePlayer
              key={p.player_id}
              player={p}
              destinations={teamIds.filter((t) => t !== teamId).map((t) => ({
                id: t,
                abbr: teams.find((x) => x.id === t)?.abbreviation ?? "?",
              }))}
              onMove={onMove}
            />
          ))
        )}
      </div>

      <div className="border-t border-line px-3 py-2">
        <details>
          <summary className="cursor-pointer text-xs text-muted hover:text-foreground">
            Add hypothetical pick (labeled — ownership unverified)
          </summary>
          <div className="mt-2 flex items-center gap-2 text-xs">
            <select
              value={pickYear}
              onChange={(e) => setPickYear(Number(e.target.value))}
              className="rounded border border-line bg-panel2 px-1.5 py-1"
              aria-label="Draft year"
            >
              {[2027, 2028, 2029, 2030, 2031].map((y) => (
                <option key={y}>{y}</option>
              ))}
            </select>
            <span>1st →</span>
            <select
              value={pickTo}
              onChange={(e) => setPickTo(e.target.value)}
              className="rounded border border-line bg-panel2 px-1.5 py-1"
              aria-label="Pick destination"
            >
              <option value="">to…</option>
              {teamIds
                .filter((t) => t !== teamId)
                .map((t) => (
                  <option key={t} value={t}>
                    {teams.find((x) => x.id === t)?.abbreviation}
                  </option>
                ))}
            </select>
            <button
              type="button"
              disabled={!pickTo}
              onClick={() =>
                setPicks((prev) => [
                  ...prev,
                  {
                    from_team_id: teamId,
                    to_team_id: pickTo,
                    draft_year: pickYear,
                    round_number: 1,
                    is_hypothetical: true,
                  },
                ])
              }
              className="rounded border border-line px-2 py-1 hover:bg-panel2 disabled:opacity-40"
            >
              add
            </button>
          </div>
          <ul className="mt-1 space-y-0.5">
            {picks
              .filter((p) => p.from_team_id === teamId)
              .map((p, i) => (
                <li key={i} className="flex items-center justify-between text-[11px] text-muted">
                  <span>
                    {p.draft_year} R{p.round_number} →{" "}
                    {teams.find((x) => x.id === p.to_team_id)?.abbreviation}{" "}
                    <Badge status="unavailable">hypothetical</Badge>
                  </span>
                  <button
                    type="button"
                    className="text-fail underline"
                    onClick={() => setPicks((prev) => prev.filter((x) => x !== p))}
                  >
                    remove
                  </button>
                </li>
              ))}
          </ul>
        </details>
      </div>
    </div>
  );
}

function DraggablePlayer({
  player,
  destinations,
  onMove,
}: {
  player: { player_id: string; name: string; position: string | null; tei: number | null };
  destinations: { id: string; abbr: string }[];
  onMove: (playerId: string, toTeamId: string) => void;
}) {
  const { attributes, listeners, setNodeRef, isDragging } = useDraggable({
    id: player.player_id,
    data: { name: player.name },
  });
  return (
    <div
      ref={setNodeRef}
      className={`group flex items-center gap-2 rounded-md px-2 py-1 ${
        isDragging ? "opacity-30" : "hover:bg-panel2"
      }`}
    >
      <button
        type="button"
        {...listeners}
        {...attributes}
        aria-label={`Drag ${player.name}`}
        className="cursor-grab touch-none text-muted hover:text-foreground"
      >
        ⠿
      </button>
      <PlayerAvatar name={player.name} size={24} />
      <span className="flex-1 truncate text-sm">{player.name}</span>
      <span className="text-[11px] text-muted">{player.position ?? ""}</span>
      <span className="font-mono text-xs text-muted">{tei(player.tei)}</span>
      <span className="hidden gap-1 group-hover:flex">
        {destinations.map((d) => (
          <button
            key={d.id}
            type="button"
            onClick={() => onMove(player.player_id, d.id)}
            className="rounded border border-line px-1 text-[10px] text-muted hover:border-accent hover:text-accent"
            aria-label={`Send ${player.name} to ${d.abbr}`}
          >
            →{d.abbr}
          </button>
        ))}
      </span>
    </div>
  );
}

function IncomingChip({
  playerId,
  onReturn,
}: {
  playerId: string;
  onReturn: () => void;
}) {
  const { data } = useQuery({
    queryKey: ["player-mini", playerId],
    queryFn: () =>
      api.get<{ player: { full_name: string } }>(`/players/${playerId}`),
  });
  return (
    <div className="flex items-center justify-between py-0.5 text-sm">
      <span>{data?.player.full_name ?? "…"}</span>
      <button type="button" onClick={onReturn} className="text-xs text-accent underline">
        undo
      </button>
    </div>
  );
}
