"use client";

import { DndContext, DragOverlay, useDraggable, useDroppable } from "@dnd-kit/core";
import type { DragEndEvent, DragStartEvent } from "@dnd-kit/core";
import { useMutation, useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useMemo, useState } from "react";
import { api } from "@/lib/api";
import {
  COMPONENT_EXPLAIN,
  COMPONENT_LABEL,
  LEGALITY_EXPLAIN,
  LEGALITY_LABEL,
  VERDICT_LABEL,
  fanVerdict,
  money,
  tei,
} from "@/lib/format";
import { getFavoriteTeam, teamTheme } from "@/lib/teamTheme";
import type {
  GeneratedCandidate,
  LegalityResponse,
  PickMove,
  PlayerMove,
  RosterPlayer,
  RosterResponse,
  Scenario,
  Team,
  TeamEvaluation,
  TradeDetail,
} from "@/lib/types";
import { ComponentBars, TornadoChart, UncertaintyStrip } from "@/components/charts";
import { PlayerPhoto, TeamLogo } from "@/components/media";
import { useToast } from "@/components/toast";
import { Badge, Card, EmptyState, Spinner } from "@/components/ui";

export default function TradeMachinePage() {
  return (
    <Suspense fallback={<Spinner label="Loading the Trade Machine…" />}>
      <TradeMachine />
    </Suspense>
  );
}

/** Serializable builder state for share links (?state=base64url json). */
interface ShareState {
  teamIds: string[];
  moves: Record<string, string>;
  picks: PickMove[];
  name?: string;
}

function encodeShareState(state: ShareState): string {
  return btoa(unescape(encodeURIComponent(JSON.stringify(state))))
    .replaceAll("+", "-")
    .replaceAll("/", "_")
    .replace(/=+$/, "");
}

function decodeShareState(raw: string): ShareState | null {
  try {
    const b64 = raw.replaceAll("-", "+").replaceAll("_", "/");
    return JSON.parse(decodeURIComponent(escape(atob(b64)))) as ShareState;
  } catch {
    return null;
  }
}

function TradeMachine() {
  const searchParams = useSearchParams();
  const router = useRouter();
  const toast = useToast();
  const scenarioId = searchParams.get("scenario");
  const loadTradeId = searchParams.get("load");
  const initialTeamId = searchParams.get("team");
  const sharedState = searchParams.get("state");

  const { data: teams } = useQuery({ queryKey: ["teams"], queryFn: () => api.get<Team[]>("/teams") });
  const { data: scenario } = useQuery({
    queryKey: ["scenario", scenarioId],
    queryFn: () => api.get<Scenario>(`/scenarios/${scenarioId}`),
    enabled: !!scenarioId,
  });

  const [teamIds, setTeamIds] = useState<string[]>([]);
  const [moves, setMoves] = useState<Record<string, string>>({});
  const [picks, setPicks] = useState<PickMove[]>([]);
  const [tradeName, setTradeName] = useState("");
  const [activeDrag, setActiveDrag] = useState<{ id: string; name: string } | null>(null);
  const [drawerPlayer, setDrawerPlayer] = useState<{ id: string; name: string } | null>(null);
  const [evaluation, setEvaluation] = useState<{
    legality: LegalityResponse;
    evaluations: Record<string, TeamEvaluation>;
  } | null>(null);

  // ---- state seeding (render-phase adjustments, no setState-in-effect) ----
  const [seeded, setSeeded] = useState(false);
  if (!seeded && teams) {
    setSeeded(true);
    const shared = sharedState ? decodeShareState(sharedState) : null;
    if (shared) {
      setTeamIds(shared.teamIds.filter((id) => teams.some((t) => t.id === id)).slice(0, 3));
      setMoves(shared.moves);
      setPicks(shared.picks ?? []);
      if (shared.name) setTradeName(shared.name);
    } else if (initialTeamId && teams.some((t) => t.id === initialTeamId)) {
      setTeamIds([initialTeamId]);
    } else {
      const favorite = getFavoriteTeam();
      if (favorite && teams.some((t) => t.id === favorite.id)) setTeamIds([favorite.id]);
    }
  }

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
      if (asset.asset_type === "player" && asset.player_id) nextMoves[asset.player_id] = asset.to_team_id;
      else if (asset.asset_type === "pick" && asset.draft_year && asset.round_number)
        nextPicks.push({
          from_team_id: asset.from_team_id,
          to_team_id: asset.to_team_id,
          draft_year: asset.draft_year,
          round_number: asset.round_number,
          protections: asset.protections,
          is_hypothetical: true,
        });
    }
    setMoves(nextMoves);
    setPicks(nextPicks);
    setTradeName(`${loadedTrade.name} (copy)`);
  }

  const [appliedScenario, setAppliedScenario] = useState<string | null>(null);
  if (scenario && teamIds.length === 0 && appliedScenario !== scenario.id) {
    setAppliedScenario(scenario.id);
    setTeamIds([scenario.focal_team_id]);
  }

  // ---- rosters ----
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
    if (rosters.data)
      for (const [tid, r] of Object.entries(rosters.data))
        for (const p of r.roster) map[p.player_id] = tid;
    return map;
  }, [rosters.data]);

  const playerMoves: PlayerMove[] = useMemo(
    () =>
      Object.entries(moves)
        .filter(([pid, to]) => originOf[pid] && originOf[pid] !== to)
        .map(([pid, to]) => ({ player_id: pid, from_team_id: originOf[pid], to_team_id: to })),
    [moves, originOf],
  );

  // ---- live rules check (backend-authoritative; debounced) ----
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
    }, 450);
    return () => clearTimeout(handle);
  }, [teamIds, playerMoves, picks]);

  const evaluate = useMutation({
    mutationFn: () =>
      api.post<{ legality: LegalityResponse; evaluations: Record<string, TeamEvaluation> }>(
        "/trades/evaluate",
        {
          team_ids: teamIds,
          player_moves: playerMoves,
          pick_moves: picks,
          scenario_id: scenarioId,
          strategy: scenario?.strategy ?? "custom",
        },
      ),
    onSuccess: setEvaluation,
    onError: (e) => toast("error", `Evaluation failed: ${String(e)}`),
  });

  const saveTrade = useMutation({
    mutationFn: () =>
      api.post<TradeDetail>("/trades", {
        name: tradeName || "Untitled deal",
        scenario_id: scenarioId,
        team_ids: teamIds,
        player_moves: playerMoves,
        pick_moves: picks,
      }),
    onSuccess: (trade) => {
      toast("success", `Saved "${trade.name}" — opening the full report.`);
      router.push(`/trades/${trade.id}`);
    },
    onError: (e) => toast("error", `Could not save: ${String(e)}`),
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
    setEvaluation(null);
  }
  function movePlayer(playerId: string, toTeamId: string) {
    setEvaluation(null);
    setMoves((m) => {
      if (originOf[playerId] === toTeamId) {
        const rest = { ...m };
        delete rest[playerId];
        return rest;
      }
      return { ...m, [playerId]: toTeamId };
    });
  }

  function copyShareLink() {
    const state = encodeShareState({ teamIds, moves, picks, name: tradeName || undefined });
    const url = `${window.location.origin}/trade-machine?state=${state}`;
    navigator.clipboard
      .writeText(url)
      .then(() => toast("success", "Share link copied — it reopens this exact deal."))
      .catch(() => toast("error", "Could not copy the link."));
  }

  function onDragStart(event: DragStartEvent) {
    const data = event.active.data.current as { name?: string } | undefined;
    setActiveDrag({ id: String(event.active.id), name: data?.name ?? "" });
  }
  function onDragEnd(event: DragEndEvent) {
    setActiveDrag(null);
    if (event.over) movePlayer(String(event.active.id), String(event.over.id));
  }

  const generate = useMutation({
    mutationFn: () =>
      api.post<{ candidates: GeneratedCandidate[]; note: string }>(
        "/trades/generate",
        scenarioId
          ? { scenario_id: scenarioId, max_candidates: 6 }
          : { focal_team_id: teamIds[0], max_candidates: 6 },
      ),
    onError: (e) => toast("error", `Idea generation failed: ${String(e)}`),
  });

  const loaded = teams ?? [];

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold">Trade Machine</h1>
          <p className="text-sm text-muted">
            Drag players between teams or use the add buttons — the rules check runs live on the
            backend{scenario ? ` · strategy: ${scenario.name}` : ""}.
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
            title="Model-generated deal ideas under your constraints — explorations, not predictions"
          >
            {generate.isPending ? "Searching…" : "Suggest deals"}
          </button>
        </div>
      </div>

      {generate.data && (
        <Card title="Suggested deals" subtitle={generate.data.note}>
          {generate.data.candidates.length === 0 ? (
            <EmptyState title="No candidates cleared the constraints" />
          ) : (
            <div className="grid gap-2 md:grid-cols-2">
              {generate.data.candidates.map((candidate, i) => (
                <div key={i} className="rounded-md border border-line bg-panel2 p-3 text-sm">
                  <div className="flex items-center justify-between">
                    <span className="flex items-center gap-2 font-semibold">
                      <TeamLogo abbreviation={candidate.counterparty.abbreviation} size={20} />
                      vs {candidate.counterparty.abbreviation}
                    </span>
                    <Badge status={candidate.legality_status}>
                      {LEGALITY_LABEL[candidate.legality_status]}
                    </Badge>
                  </div>
                  <p className="mt-1 text-xs text-muted">
                    Out: {candidate.outgoing.map((p) => p.name).join(", ")} · In:{" "}
                    {candidate.incoming.map((p) => p.name).join(", ")}
                  </p>
                  <button
                    type="button"
                    className="mt-2 text-xs text-brand underline"
                    onClick={() => {
                      addTeam(candidate.counterparty.team_id);
                      const next: Record<string, string> = {};
                      for (const p of candidate.outgoing) next[p.player_id] = candidate.counterparty.team_id;
                      for (const p of candidate.incoming) next[p.player_id] = teamIds[0];
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
          title="Add two teams to start building"
          hint="Tip: set your team on Home and it will be pre-selected here."
        />
      )}

      <DndContext onDragStart={onDragStart} onDragEnd={onDragEnd}>
        <div className={`grid gap-4 ${teamIds.length === 3 ? "xl:grid-cols-3" : "lg:grid-cols-2"}`}>
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
              onInspect={(p) => setDrawerPlayer({ id: p.player_id, name: p.name })}
              picks={picks}
              setPicks={setPicks}
            />
          ))}
        </div>
        <DragOverlay>
          {activeDrag && (
            <div className="flex items-center gap-2 rounded-md border border-brand bg-panel px-2 py-1 text-sm shadow-lg">
              {activeDrag.name}
            </div>
          )}
        </DragOverlay>
      </DndContext>

      {teamIds.length >= 2 && (
        <div className="grid gap-4 lg:grid-cols-[1fr_300px]">
          <RulesPanel validation={validation} validating={validating} />
          <Card title="Save & share">
            <div className="space-y-2.5">
              <input
                value={tradeName}
                onChange={(e) => setTradeName(e.target.value)}
                placeholder="Name this deal…"
                className="w-full rounded-md border border-line bg-panel2 px-2 py-1.5 text-sm"
                aria-label="Deal name"
              />
              <button
                type="button"
                disabled={playerMoves.length === 0 || evaluate.isPending}
                onClick={() => evaluate.mutate()}
                className="w-full rounded-md bg-brand px-4 py-2 text-sm font-semibold text-background hover:brightness-110 disabled:opacity-40"
              >
                {evaluate.isPending ? "Evaluating…" : "Evaluate this deal"}
              </button>
              <div className="flex gap-2">
                <button
                  type="button"
                  disabled={playerMoves.length === 0 || saveTrade.isPending}
                  onClick={() => saveTrade.mutate()}
                  className="flex-1 rounded-md border border-line px-3 py-2 text-sm hover:bg-panel2 disabled:opacity-40"
                >
                  {saveTrade.isPending ? "Saving…" : "Save deal"}
                </button>
                <button
                  type="button"
                  disabled={playerMoves.length === 0}
                  onClick={copyShareLink}
                  className="flex-1 rounded-md border border-line px-3 py-2 text-sm hover:bg-panel2 disabled:opacity-40"
                >
                  Copy share link
                </button>
              </div>
              <p className="text-[11px] text-muted">
                Saved deals appear in{" "}
                <Link href="/compare" className="underline">
                  Compare Deals
                </Link>
                .
              </p>
            </div>
          </Card>
        </div>
      )}

      {evaluation && teams && (
        <EvaluationPanel evaluation={evaluation} teams={teams} teamIds={teamIds} />
      )}

      {drawerPlayer && <PlayerDrawer player={drawerPlayer} onClose={() => setDrawerPlayer(null)} />}
    </div>
  );
}

/* ------------------------------------------------------------------ columns */

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
  onInspect,
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
  onInspect: (player: RosterPlayer) => void;
  picks: PickMove[];
  setPicks: React.Dispatch<React.SetStateAction<PickMove[]>>;
}) {
  const team = teams.find((t) => t.id === teamId);
  const theme = teamTheme(team?.abbreviation);
  const { setNodeRef, isOver } = useDroppable({ id: teamId });
  const teamLegality = validation?.teams[teamId];

  const [query, setQuery] = useState("");
  const [positionFilter, setPositionFilter] = useState("");
  const [sort, setSort] = useState<"tei" | "age" | "name">("tei");

  const staying = (roster?.roster ?? [])
    .filter((p) => (moves[p.player_id] ?? teamId) === teamId)
    .filter((p) => !query || p.name.toLowerCase().includes(query.toLowerCase()))
    .filter((p) => !positionFilter || (p.position ?? "").toUpperCase().includes(positionFilter))
    .sort((a, b) =>
      sort === "tei"
        ? (b.tei ?? -99) - (a.tei ?? -99)
        : sort === "age"
          ? (a.age ?? 99) - (b.age ?? 99)
          : a.name.localeCompare(b.name),
    );
  const incomingIds = Object.entries(moves)
    .filter(([pid, to]) => to === teamId && originOf[pid] !== teamId)
    .map(([pid]) => pid);
  const outgoing = (roster?.roster ?? []).filter(
    (p) => moves[p.player_id] && moves[p.player_id] !== teamId,
  );

  const [pickYear, setPickYear] = useState(2027);
  const [pickTo, setPickTo] = useState("");

  return (
    <div
      ref={setNodeRef}
      className={`rounded-xl border bg-panel transition-colors ${isOver ? "" : "border-line"}`}
      style={{
        borderColor: isOver ? theme.bright : undefined,
        borderTop: `3px solid ${theme.primary}`,
      }}
    >
      <header
        className="flex items-center justify-between gap-2 border-b border-line px-3 py-2"
        style={{ background: `linear-gradient(90deg, ${theme.primary}22, transparent 65%)` }}
      >
        <div className="flex min-w-0 items-center gap-2">
          <TeamLogo abbreviation={team?.abbreviation} name={team?.full_name} size={30} />
          <div className="min-w-0">
            <div className="truncate text-sm font-semibold">{team?.full_name}</div>
            {teamLegality && (
              <div className="text-[10px] text-muted">
                roster {teamLegality.roster_before}→{teamLegality.roster_after} · in{" "}
                {money(teamLegality.incoming_salary)} · out {money(teamLegality.outgoing_salary)}
              </div>
            )}
          </div>
        </div>
        <button
          type="button"
          onClick={onRemove}
          aria-label={`Remove ${team?.full_name} from trade`}
          className="rounded px-1.5 text-muted hover:bg-panel2 hover:text-fail"
        >
          ×
        </button>
      </header>

      {incomingIds.length > 0 && (
        <div className="border-b border-line bg-pass/5 px-3 py-2">
          <div className="text-[10px] font-semibold uppercase tracking-wide text-pass">Incoming</div>
          {incomingIds.map((pid) => (
            <IncomingRow key={pid} playerId={pid} onUndo={() => onMove(pid, originOf[pid])} />
          ))}
        </div>
      )}
      {outgoing.length > 0 && (
        <div className="border-b border-line bg-fail/5 px-3 py-2">
          <div className="text-[10px] font-semibold uppercase tracking-wide text-fail">Outgoing</div>
          {outgoing.map((p) => (
            <div key={p.player_id} className="flex items-center justify-between py-0.5 text-sm">
              <span className="text-muted line-through">{p.name}</span>
              <button
                type="button"
                onClick={() => onMove(p.player_id, teamId)}
                className="text-xs text-brand underline"
              >
                undo
              </button>
            </div>
          ))}
        </div>
      )}

      <div className="flex items-center gap-1.5 border-b border-line px-2 py-1.5">
        <input
          type="search"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Filter roster…"
          aria-label={`Filter ${team?.abbreviation} roster`}
          className="w-full min-w-0 flex-1 rounded border border-line bg-panel2 px-2 py-1 text-xs"
        />
        <select
          value={positionFilter}
          onChange={(e) => setPositionFilter(e.target.value)}
          aria-label="Position filter"
          className="rounded border border-line bg-panel2 px-1 py-1 text-xs"
        >
          <option value="">All</option>
          <option value="G">G</option>
          <option value="F">F</option>
          <option value="C">C</option>
        </select>
        <select
          value={sort}
          onChange={(e) => setSort(e.target.value as "tei" | "age" | "name")}
          aria-label="Sort roster"
          className="rounded border border-line bg-panel2 px-1 py-1 text-xs"
        >
          <option value="tei">Impact</option>
          <option value="age">Age</option>
          <option value="name">Name</option>
        </select>
      </div>

      <div className="scroll-thin max-h-[380px] overflow-y-auto p-1.5">
        {!roster ? (
          <div className="space-y-1.5 p-1">
            {Array.from({ length: 7 }).map((_, i) => (
              <div key={i} className="skeleton h-10" />
            ))}
          </div>
        ) : (
          staying.map((player) => (
            <DraggablePlayer
              key={player.player_id}
              player={player}
              destinations={teamIds
                .filter((t) => t !== teamId)
                .map((t) => ({ id: t, abbr: teams.find((x) => x.id === t)?.abbreviation ?? "?" }))}
              onMove={onMove}
              onInspect={() => onInspect(player)}
            />
          ))
        )}
      </div>

      <div className="border-t border-line px-3 py-2">
        <details>
          <summary className="cursor-pointer text-xs text-muted hover:text-foreground">
            Add hypothetical pick (ownership unverified — labeled)
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
  onInspect,
}: {
  player: RosterPlayer;
  destinations: { id: string; abbr: string }[];
  onMove: (playerId: string, toTeamId: string) => void;
  onInspect: () => void;
}) {
  const { attributes, listeners, setNodeRef, isDragging } = useDraggable({
    id: player.player_id,
    data: { name: player.name },
  });
  return (
    <div
      ref={setNodeRef}
      className={`group flex items-center gap-2 rounded-md px-1.5 py-1 ${
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
      <button
        type="button"
        onClick={onInspect}
        className="shrink-0"
        aria-label={`About ${player.name}`}
      >
        <PlayerPhoto nbaPlayerId={player.nba_player_id} name={player.name} size={30} />
      </button>
      <button type="button" onClick={onInspect} className="min-w-0 flex-1 text-left">
        <span className="block truncate text-sm group-hover:text-brand">{player.name}</span>
        <span className="text-[10px] text-muted">
          {player.position ?? "—"} · {player.age ? `${player.age.toFixed(0)}y` : "—"}
          {player.archetype ? ` · ${player.archetype}` : ""}
        </span>
      </button>
      <span className="font-mono text-xs text-muted" title="Estimated player impact — see Methodology">
        {tei(player.tei)}
      </span>
      <span className="hidden gap-1 group-hover:flex">
        {destinations.map((d) => (
          <button
            key={d.id}
            type="button"
            onClick={() => onMove(player.player_id, d.id)}
            className="rounded border border-line px-1 text-[10px] text-muted hover:border-brand hover:text-brand"
            aria-label={`Send ${player.name} to ${d.abbr}`}
          >
            →{d.abbr}
          </button>
        ))}
      </span>
    </div>
  );
}

function IncomingRow({ playerId, onUndo }: { playerId: string; onUndo: () => void }) {
  const { data } = useQuery({
    queryKey: ["player-mini", playerId],
    queryFn: () =>
      api.get<{ player: { full_name: string; nba_player_id: number } }>(`/players/${playerId}`),
  });
  return (
    <div className="flex items-center gap-2 py-0.5 text-sm">
      {data && (
        <PlayerPhoto nbaPlayerId={data.player.nba_player_id} name={data.player.full_name} size={22} />
      )}
      <span className="flex-1">{data?.player.full_name ?? "…"}</span>
      <button type="button" onClick={onUndo} className="text-xs text-brand underline">
        undo
      </button>
    </div>
  );
}

/* -------------------------------------------------------------- rules panel */

function RulesPanel({
  validation,
  validating,
}: {
  validation: LegalityResponse | null;
  validating: boolean;
}) {
  return (
    <Card
      title="Trade rules check"
      subtitle={
        validating
          ? "checking…"
          : validation
            ? `cap year ${validation.league_year} · verified by the backend rules engine`
            : "move a player to run the check"
      }
    >
      {!validation ? (
        <EmptyState title="No check yet" hint="Move at least one player between teams." />
      ) : (
        <div className="space-y-3">
          <div className="flex flex-wrap items-center gap-2">
            <Badge status={validation.overall_status} className="text-sm">
              {LEGALITY_LABEL[validation.overall_status]}
            </Badge>
            <span className="text-xs text-muted">{LEGALITY_EXPLAIN[validation.overall_status]}</span>
          </div>
          {!validation.contract_provider_configured && (
            <p className="rounded-md border border-unavail/40 bg-unavail/10 px-2.5 py-1.5 text-xs text-unavail">
              Salary-matching rules can&apos;t run: contract data isn&apos;t imported.{" "}
              <Link href="/cap-lab" className="underline">
                Import contracts in Cap Lab
              </Link>{" "}
              to enable full checks.
            </p>
          )}
          <ul className="scroll-thin max-h-56 space-y-1.5 overflow-y-auto pr-1">
            {validation.rule_results.map((rule, i) => (
              <li key={i} className="flex items-start gap-2 text-sm">
                <Badge status={rule.status} className="mt-0.5 shrink-0">
                  {rule.status}
                </Badge>
                <span className="text-xs leading-relaxed">
                  {rule.message}
                  <span className="ml-1 font-mono text-[10px] text-muted">{rule.rule_code}</span>
                </span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </Card>
  );
}

/* -------------------------------------------------------- evaluation panel */

function EvaluationPanel({
  evaluation,
  teams,
  teamIds,
}: {
  evaluation: { legality: LegalityResponse; evaluations: Record<string, TeamEvaluation> };
  teams: Team[];
  teamIds: string[];
}) {
  const [activeTeam, setActiveTeam] = useState(teamIds[0]);
  const [advanced, setAdvanced] = useState(false);
  const teamEval = evaluation.evaluations[activeTeam];
  const team = teams.find((t) => t.id === activeTeam);
  const theme = teamTheme(team?.abbreviation);
  if (!teamEval) return null;

  const verdict = fanVerdict(teamEval.composite_utility, teamEval.confidence);
  const perf = teamEval.detail.performance as {
    delta_wins?: number;
    delta_net_rating?: number;
  };
  const gained = teamEval.drivers?.filter((d) => d.contribution > 0.5).slice(0, 3) ?? [];
  const lost = teamEval.drivers?.filter((d) => d.contribution < -0.5).slice(0, 3) ?? [];

  return (
    <Card
      title="Deal evaluation"
      subtitle="Fan summary first — expand for the full analysis"
      actions={
        <div className="flex gap-1" role="tablist" aria-label="Team perspective">
          {teamIds.map((tid) => {
            const t = teams.find((x) => x.id === tid);
            return (
              <button
                key={tid}
                role="tab"
                aria-selected={tid === activeTeam}
                onClick={() => setActiveTeam(tid)}
                className={`flex items-center gap-1.5 rounded-md px-2.5 py-1 text-xs ${
                  tid === activeTeam ? "bg-panel2 font-semibold" : "text-muted hover:text-foreground"
                }`}
              >
                <TeamLogo abbreviation={t?.abbreviation} size={16} />
                {t?.abbreviation}
              </button>
            );
          })}
        </div>
      }
    >
      <div
        className="rounded-lg border p-4"
        style={{ borderColor: `${theme.bright}44`, background: `${theme.primary}11` }}
      >
        <div className="flex flex-wrap items-center gap-3">
          <span
            className="rounded-full px-3 py-1 text-sm font-bold"
            style={{ background: `${theme.primary}44`, color: theme.bright }}
          >
            {VERDICT_LABEL[verdict]}
          </span>
          <span className="text-sm text-muted">
            Decision score {teamEval.composite_utility?.toFixed(0)}/100 · confidence{" "}
            {teamEval.confidence}
          </span>
          <Link href="/methodology#utility" className="text-xs text-brand underline">
            what does this mean?
          </Link>
        </div>
        <div className="mt-3 grid gap-3 text-sm sm:grid-cols-2 lg:grid-cols-4">
          <div>
            <div className="text-[11px] text-muted">Projected wins impact</div>
            <div className="font-mono text-lg">
              {perf?.delta_wins !== undefined
                ? `${perf.delta_wins >= 0 ? "+" : ""}${perf.delta_wins.toFixed(1)}`
                : "—"}
              <span className="ml-1 text-xs text-muted">
                [{teamEval.uncertainty.p10.toFixed(1)}, {teamEval.uncertainty.p90.toFixed(1)}]
              </span>
            </div>
          </div>
          <div>
            <div className="text-[11px] text-muted">Chance the deal helps</div>
            <div className="font-mono text-lg">
              {(teamEval.uncertainty.prob_positive * 100).toFixed(0)}%
            </div>
          </div>
          <div>
            <div className="text-[11px] text-muted">Payroll change</div>
            <div className="font-mono text-lg">
              {teamEval.legality.payroll_after !== null && teamEval.legality.payroll_before !== null
                ? money(teamEval.legality.payroll_after - teamEval.legality.payroll_before)
                : "unavailable"}
            </div>
          </div>
          <div>
            <div className="text-[11px] text-muted">Strengths gained / lost</div>
            <div className="text-xs leading-relaxed">
              {gained.length > 0 && (
                <span className="text-pass">
                  ▲ {gained.map((d) => COMPONENT_LABEL[d.component]).join(", ")}
                </span>
              )}
              {gained.length > 0 && lost.length > 0 && <br />}
              {lost.length > 0 && (
                <span className="text-fail">
                  ▼ {lost.map((d) => COMPONENT_LABEL[d.component]).join(", ")}
                </span>
              )}
              {gained.length === 0 && lost.length === 0 && (
                <span className="text-muted">roughly neutral</span>
              )}
            </div>
          </div>
        </div>
        {teamEval.excluded_components.length > 0 && (
          <p className="mt-2 text-[11px] text-unavail">
            Not evaluated (data missing):{" "}
            {teamEval.excluded_components.map((c) => COMPONENT_LABEL[c]).join(", ")} — weights
            renormalized.
          </p>
        )}
      </div>

      <button
        type="button"
        onClick={() => setAdvanced((a) => !a)}
        aria-expanded={advanced}
        className="mt-3 text-sm text-brand underline"
      >
        {advanced ? "Hide advanced analysis" : "Show advanced analysis"}
      </button>

      {advanced && (
        <div className="mt-3 grid gap-4 lg:grid-cols-2">
          <div>
            <h4 className="mb-1 text-sm font-semibold">Component scores</h4>
            <ComponentBars components={teamEval.components} excluded={teamEval.excluded_components} />
            <dl className="mt-2 space-y-1 text-[11px] text-muted">
              {Object.entries(COMPONENT_EXPLAIN).map(([key, explanation]) => (
                <div key={key}>
                  <dt className="inline font-semibold">{COMPONENT_LABEL[key]}: </dt>
                  <dd className="inline">{explanation}</dd>
                </div>
              ))}
            </dl>
          </div>
          <div className="space-y-4">
            <div>
              <h4 className="mb-1 text-sm font-semibold">Wins distribution (Monte Carlo)</h4>
              <UncertaintyStrip u={teamEval.uncertainty} />
            </div>
            <div>
              <h4 className="mb-1 text-sm font-semibold">Sensitivity to strategy weights</h4>
              <TornadoChart bars={teamEval.sensitivity_tornado} />
              <p className="text-[11px] text-muted">
                How the decision score moves when each weight swings ±50% — wide bars mean the
                verdict depends on your priorities.
              </p>
            </div>
          </div>
        </div>
      )}
    </Card>
  );
}

/* ------------------------------------------------------------ player drawer */

function PlayerDrawer({
  player,
  onClose,
}: {
  player: { id: string; name: string };
  onClose: () => void;
}) {
  const { data } = useQuery({
    queryKey: ["player", player.id],
    queryFn: () =>
      api.get<{
        player: {
          full_name: string;
          nba_player_id: number;
          position: string | null;
          birth_date: string | null;
          current_team: Team | null;
        };
        impact: { tei?: number; availability?: number | null; note: string };
        archetype: { label: string } | null;
      }>(`/players/${player.id}`),
  });
  const { data: stats } = useQuery({
    queryKey: ["player-stats", player.id],
    queryFn: () =>
      api.get<{ seasons: { season: string; base?: Record<string, number> }[] }>(
        `/players/${player.id}/stats`,
      ),
  });
  const latest = stats?.seasons?.filter((s) => s.base).at(-1);

  return (
    <div
      className="fixed inset-0 z-50 flex justify-end bg-black/50"
      role="dialog"
      aria-modal="true"
      aria-label={`${player.name} details`}
      onClick={onClose}
    >
      <div
        className="h-full w-full max-w-sm overflow-y-auto border-l border-line bg-panel p-4"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between">
          <h3 className="text-lg font-semibold">{player.name}</h3>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close player details"
            className="rounded px-2 py-1 text-muted hover:bg-panel2"
          >
            ✕
          </button>
        </div>
        {!data ? (
          <Spinner />
        ) : (
          <div className="mt-3 space-y-3 text-sm">
            <div className="flex items-center gap-3">
              <PlayerPhoto
                nbaPlayerId={data.player.nba_player_id}
                name={data.player.full_name}
                size={64}
              />
              <div>
                <div className="text-muted">
                  {data.player.position ?? "—"}
                  {data.player.current_team ? ` · ${data.player.current_team.abbreviation}` : ""}
                </div>
                {data.archetype && <Badge status="info">{data.archetype.label}</Badge>}
              </div>
            </div>
            <div className="grid grid-cols-2 gap-2">
              <div className="rounded-md border border-line bg-panel2 p-2">
                <div className="text-[10px] text-muted">Est. impact (TEI)</div>
                <div className="font-mono text-lg">{tei(data.impact.tei)}</div>
              </div>
              <div className="rounded-md border border-line bg-panel2 p-2">
                <div className="text-[10px] text-muted">Availability (hist.)</div>
                <div className="font-mono text-lg">
                  {data.impact.availability != null
                    ? `${(data.impact.availability * 100).toFixed(0)}%`
                    : "—"}
                </div>
              </div>
            </div>
            {latest?.base && (
              <div className="rounded-md border border-line bg-panel2 p-2 text-xs">
                <div className="mb-1 text-[10px] uppercase tracking-wide text-muted">
                  {latest.season} per game
                </div>
                {(["PTS", "REB", "AST", "STL", "BLK"] as const).map((k) => (
                  <span key={k} className="mr-3 font-mono">
                    {k} {latest.base?.[k]?.toFixed(1) ?? "—"}
                  </span>
                ))}
              </div>
            )}
            <Link href={`/players/${player.id}`} className="block text-xs text-brand underline">
              full player page →
            </Link>
            <p className="text-[11px] text-muted">{data.impact.note}</p>
          </div>
        )}
      </div>
    </div>
  );
}
