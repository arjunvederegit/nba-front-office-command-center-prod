"use client";

/**
 * Trade Evaluator — the war room.
 *
 * Two or three team workspaces sit side by side with a transaction lane running
 * between them, so the page reads as assets moving rather than a form being
 * filled in. Everything underneath is backend-authoritative: legality comes from
 * POST /trades/validate, impact from POST /trades/evaluate, and anything the
 * backend cannot compute is shown as missing rather than guessed.
 */

import { DndContext, DragOverlay, useDraggable, useDroppable } from "@dnd-kit/core";
import type { DragEndEvent, DragStartEvent } from "@dnd-kit/core";
import { useMutation, useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import {
  Suspense,
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  useSyncExternalStore,
} from "react";
import { api } from "@/lib/api";
import { tradeDetailSchema } from "@/lib/schemas";
import {
  COMPONENT_EXPLAIN,
  COMPONENT_LABEL,
  LEGALITY_EXPLAIN,
  LEGALITY_LABEL,
  LEGALITY_SHORT,
  NEED_LABEL,
  SKILL_LABEL,
  VERDICT_LABEL,
  fanVerdict,
  money,
  payrollDisclosure,
  tei,
} from "@/lib/format";
import { getFavoriteTeam } from "@/lib/teamTheme";
import { teamIdentity } from "@/lib/teamIdentity";
import type {
  LegalityResponse,
  PickMove,
  PlayerMove,
  RosterPlayer,
  RosterResponse,
  RuleResult,
  Scenario,
  Team,
  TeamEvaluation,
  TeamLegality,
  TradeDetail,
} from "@/lib/types";
import {
  BeforeAfterBars,
  ComponentBars,
  TornadoChart,
  UncertaintyStrip,
} from "@/components/charts";
import { HalfCourt, KeyFrame, TransactionLane } from "@/components/court";
import { PlayerPhoto, TeamCrest, TeamLogo } from "@/components/media";
import { useToast } from "@/components/toast";
import {
  Badge,
  Button,
  ButtonLink,
  EmptyState,
  MeterBar,
  PageHeader,
  Panel,
  Skeleton,
  SkeletonRows,
  SourceRail,
  StatBlock,
  Tabs,
  UnavailableNotice,
} from "@/components/ui";

/* ---------------------------------------------------------------- constants */

/** Four visually distinct states — glyph and word, never color alone. */
const LEGALITY_VISUAL: Record<string, { glyph: string; color: string; text: string }> = {
  verified_legal: { glyph: "✓", color: "var(--legal)", text: "text-legal" },
  verified_illegal: { glyph: "✕", color: "var(--illegal)", text: "text-illegal" },
  conditionally_valid: { glyph: "~", color: "var(--conditional)", text: "text-conditional" },
  not_evaluated: { glyph: "—", color: "var(--unknown)", text: "text-unavail" },
};

const RULE_STATUS_WORD: Record<string, string> = {
  pass: "passes",
  fail: "fails",
  warning: "warning",
  unavailable: "not run",
};

const CONTRACT_TOOLTIP =
  "Contract data isn't imported, so salaries and contract years can't be shown. RosterLab never estimates a salary.";

const HOW_IT_WORKS: { step: string; title: string; body: string }[] = [
  {
    step: "01",
    title: "Pick two teams",
    body: "Choose the sides of the deal — your team is preselected if you set one.",
  },
  {
    step: "02",
    title: "Move the assets",
    body: "Drag a player across the lane, or use the send button on any roster card.",
  },
  {
    step: "03",
    title: "Read the verdict",
    body: "The rules check runs live, then Evaluate returns projected impact with its uncertainty.",
  },
];

/* -------------------------------------------------------------- local types */

interface RotationRow {
  player_id: string;
  name: string;
  minutes: number;
  tei: number;
  availability: number;
}

interface PerformanceDetail {
  delta_wins?: number;
  delta_net_rating?: number;
  rotation_before?: RotationRow[];
  rotation_after?: RotationRow[];
}

interface FitDetail {
  unavailable?: string;
  needs?: Record<string, number>;
  needs_addressed?: Record<string, number>;
  redundancies?: Record<string, number>;
  skill_delta?: Record<string, number>;
  /** Needs the model measures but declines to claim any player skill addresses (R4-2). */
  needs_not_addressable?: Record<string, string>;
}

interface TimelineDetail {
  unavailable?: string;
  strategy?: string;
  incoming_alignment?: number;
  outgoing_alignment?: number;
}

interface PickValuation {
  pick: string;
  direction: "in" | "out";
  low: number;
  point: number | null;
  high: number;
  /** interval = priced; range = protected/swapped; unknown = ownership unverified. */
  precision: "interval" | "range" | "unknown";
  caveats: string[];
  slot_support: { min_slot: number; max_slot: number; central_slot: number | null };
}

interface AssetsDetail {
  picks_in?: number;
  picks_out?: number;
  roster_spots_delta?: number;
  picks_priced?: PickValuation[];
  picks_not_priced?: PickValuation[];
  pick_units_net?: number;
  pick_reference?: string;
  payroll_delta?: number;
  payroll_basis?: string;
  payroll_note?: string;
  /** Reported here, scored by the contract component — see `payroll_scored_note`. */
  payroll_scored?: boolean;
  payroll_scored_note?: string;
  precision_note?: string;
  unavailable?: string;
}

interface RiskDetail {
  /** null when no arriving player has a known availability history. */
  incoming_availability?: number | null;
  incoming_availability_players?: number;
  /** null when no departing player has a known availability history. */
  outgoing_availability?: number | null;
  outgoing_availability_players?: number;
  /** The measured fallback for a side with no priced package: who actually plays those minutes. */
  roster_availability?: number | null;
  roster_availability_players?: number;
  availability_delta?: number;
  baseline_note?: string;
  method?: string;
  /** Reported, never scored — see `scored: false`. */
  legality_verification?: {
    rules_evaluated: number;
    rules_with_a_definite_verdict: number;
    share: number | null;
    scored: boolean;
    note: string;
  };
  unavailable?: string;
}

interface TeamDetailResponse {
  team: Team;
  season: string;
  standing: {
    wins: number;
    losses: number;
    win_pct: number | null;
    conference: string | null;
    playoff_rank: number | null;
  } | null;
}

interface Destination {
  id: string;
  abbr: string;
  name: string;
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

function sectionOf<T>(detail: Record<string, Record<string, unknown>> | undefined, key: string): T {
  return (detail?.[key] ?? {}) as T;
}

/* --------------------------------------------------------------------- page */

export default function TradeEvaluatorPage() {
  return (
    <Suspense fallback={<BuilderSkeleton />}>
      <TradeEvaluator />
    </Suspense>
  );
}

function BuilderSkeleton() {
  return (
    <div role="status" aria-label="Loading the Trade Evaluator">
      <PageHeader
        eyebrow="Trade Evaluator"
        title="Trade Evaluator"
        lede="Build a two- or three-team deal, watch the rules check run live on the backend, then evaluate the projected impact for every side."
      />
      <div className="grid gap-3 lg:grid-cols-[minmax(0,1fr)_auto_minmax(0,1fr)]">
        <Skeleton className="h-[420px]" />
        <div className="flex items-center justify-center py-1 lg:min-h-[27rem] lg:px-1">
          <TransactionLane className="h-11 w-24" />
        </div>
        <Skeleton className="h-[420px]" />
      </div>
    </div>
  );
}

/**
 * True only after hydration. The builder is entirely client-data-driven and sits
 * inside a Suspense boundary that hydrates *after* the app shell has already
 * warmed the shared `teams` query — without this gate the first client render
 * would legitimately disagree with the server HTML.
 */
const noopSubscribe = () => () => {};
function useHydrated(): boolean {
  return useSyncExternalStore(
    noopSubscribe,
    () => true,
    () => false,
  );
}

function TradeEvaluator() {
  const hydrated = useHydrated();
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
  const [pickerOpen, setPickerOpen] = useState(false);
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
    queryFn: () => api.get<TradeDetail>(`/trades/${loadTradeId}`, tradeDetailSchema),
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

  /** Every rostered player in the builder, so incoming cards need no extra fetch. */
  const playerIndex = useMemo(() => {
    const map: Record<string, RosterPlayer> = {};
    if (rosters.data)
      for (const r of Object.values(rosters.data)) for (const p of r.roster) map[p.player_id] = p;
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

  const addTeam = useCallback(
    (id: string) => {
      setTeamIds((current) =>
        id && !current.includes(id) && current.length < 3 ? [...current, id] : current,
      );
    },
    [setTeamIds],
  );

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
    const url = `${window.location.origin}/trade-evaluator?state=${state}`;
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

  // R1-8 — the candidate generator is hidden pending a constrained rebuild in R5.
  //
  // Measured, it reaches **13.8 %** of counterparties (4 of 29): `evaluations_run`
  // hits the 400-evaluation budget after roughly six teams, in unordered insertion
  // order, and says nothing about the truncation. It has no salary matching, so it
  // proposed Donovan Mitchell *and* James Harden for Jordan Walsh at a counterparty
  // utility of 52.0 — above the 42.0 acceptance floor (QA-10).
  //
  // `services/candidates.py` and `POST /trades/generate` remain; only the entry point
  // is removed, so the R5 rebuild starts from working scaffolding rather than a blank
  // file.

  const loaded = teams ?? [];
  const threeWay = teamIds.length === 3;
  const overall = validation?.overall_status;
  const hasMoves = playerMoves.length > 0;

  if (!hydrated) return <BuilderSkeleton />;

  return (
    <div className="pb-24 lg:pb-0">
      <PageHeader
        eyebrow="Trade Evaluator"
        title="Trade Evaluator"
        lede="Build a two- or three-team deal, watch the rules check run live on the backend, then evaluate the projected impact for every side."
        actions={
          <TeamPicker
            teams={loaded}
            selected={teamIds}
            onAdd={addTeam}
            open={pickerOpen}
            setOpen={setPickerOpen}
          />
        }
        meta={
          <>
            {validation && <Badge status="info">Cap year {validation.league_year}</Badge>}
            {validating && (
              <span className="eyebrow flex items-center gap-1.5 text-signal">
                <span className="pulse-live h-1.5 w-1.5 rounded-full bg-signal" aria-hidden />
                Checking rules
              </span>
            )}
            {!validating && overall && (
              <Badge status={overall}>{LEGALITY_LABEL[overall]}</Badge>
            )}
            {scenario && (
              <Badge status="info">Strategy: {scenario.strategy.replaceAll("_", " ")}</Badge>
            )}
            <span className="text-[11px] text-faint">
              {teamIds.length}/3 teams · {playerMoves.length} player
              {playerMoves.length === 1 ? "" : "s"} moving
            </span>
          </>
        }
      />

      <div className="space-y-6">
        {teamIds.length === 0 ? (
          <StartHere teams={loaded} onAdd={addTeam} onPick={() => setPickerOpen(true)} />
        ) : (
          <DndContext onDragStart={onDragStart} onDragEnd={onDragEnd}>
            <div
              className={
                threeWay
                  ? "grid items-start gap-3 xl:grid-cols-[minmax(0,1fr)_auto_minmax(0,1fr)_auto_minmax(0,1fr)]"
                  : teamIds.length === 1
                    ? "grid gap-3 lg:grid-cols-[minmax(0,1fr)_auto_minmax(0,1fr)]"
                    : "grid items-start gap-3 lg:grid-cols-[minmax(0,1fr)_auto_minmax(0,1fr)]"
              }
            >
              {teamIds.map((tid, index) => (
                <TeamWorkspaceCell
                  key={tid}
                  index={index}
                  threeWay={threeWay}
                  teamIds={teamIds}
                  teams={loaded}
                  roster={rosters.data?.[tid]}
                  rosterLoading={rosters.isPending}
                  playerIndex={playerIndex}
                  moves={moves}
                  originOf={originOf}
                  validation={validation}
                  picks={picks}
                  setPicks={setPicks}
                  onRemove={() => removeTeam(tid)}
                  onMove={movePlayer}
                  onInspect={(p) => setDrawerPlayer({ id: p.player_id, name: p.name })}
                />
              ))}
              {teamIds.length === 1 && (
                <>
                  <LaneCell threeWay={false} active={false} left="var(--signal)" right="var(--signal)" />
                  <AddPartnerSlot teams={loaded} selected={teamIds} onAdd={addTeam} />
                </>
              )}
            </div>
            <DragOverlay dropAnimation={null}>
              {activeDrag && (
                <div className="flex items-center gap-2 rounded-md border border-signal bg-panel2 px-2.5 py-1.5 text-sm shadow-[var(--shadow-pop)]">
                  <span aria-hidden className="text-signal">
                    →
                  </span>
                  {activeDrag.name}
                </div>
              )}
            </DragOverlay>
          </DndContext>
        )}

        {teamIds.length < 2 && <HowItWorks />}

        {teamIds.length >= 2 && (
          <div className="grid gap-3 lg:grid-cols-[minmax(0,1fr)_minmax(280px,340px)]">
            <RulesCheck
              className="self-start"
              validation={validation}
              validating={validating}
              hasMoves={hasMoves}
            />
            <div>
              <div className="space-y-3 lg:sticky lg:top-20">
                <SaveShare
                  tradeName={tradeName}
                  setTradeName={setTradeName}
                  canAct={hasMoves}
                  evaluating={evaluate.isPending}
                  saving={saveTrade.isPending}
                  onEvaluate={() => evaluate.mutate()}
                  onSave={() => saveTrade.mutate()}
                  onCopy={copyShareLink}
                />
                <DealLedger
                  teams={loaded}
                  playerMoves={playerMoves}
                  picks={picks}
                  playerIndex={playerIndex}
                />
                <HowItWorks variant="rail" />
              </div>
            </div>
          </div>
        )}

        {evaluation && teams && (
          <EvaluationSection evaluation={evaluation} teams={teams} teamIds={teamIds} />
        )}
      </div>

      {/* Mobile action rail — the verdict and the primary action stay reachable. */}
      {teamIds.length >= 2 && hasMoves && (
        <div className="fixed inset-x-0 bottom-0 z-40 border-t border-line bg-arena/95 px-4 py-2.5 backdrop-blur lg:hidden">
          <div className="flex items-center gap-3">
            <span className="min-w-0 flex-1">
              {validating ? (
                <span className="eyebrow text-signal">Checking rules…</span>
              ) : overall ? (
                <span className={`flex items-center gap-1.5 ${LEGALITY_VISUAL[overall].text}`}>
                  <span aria-hidden className="data text-sm">
                    {LEGALITY_VISUAL[overall].glyph}
                  </span>
                  <span className="title-md truncate">{LEGALITY_SHORT[overall]}</span>
                </span>
              ) : (
                <span className="eyebrow">No check yet</span>
              )}
            </span>
            <Button
              variant="primary"
              size="sm"
              disabled={evaluate.isPending}
              onClick={() => evaluate.mutate()}
            >
              {evaluate.isPending ? "Evaluating…" : "Evaluate"}
            </Button>
          </div>
        </div>
      )}

      {drawerPlayer && <PlayerDrawer player={drawerPlayer} onClose={() => setDrawerPlayer(null)} />}
    </div>
  );
}

/* -------------------------------------------------------------- team picker */

function TeamPicker({
  teams,
  selected,
  onAdd,
  open,
  setOpen,
}: {
  teams: Team[];
  selected: string[];
  onAdd: (id: string) => void;
  open: boolean;
  setOpen: (open: boolean) => void;
}) {
  const [query, setQuery] = useState("");
  const boxRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const full = selected.length >= 3;

  useEffect(() => {
    if (!open) return;
    inputRef.current?.focus();
    function onPointer(event: MouseEvent) {
      if (boxRef.current && !boxRef.current.contains(event.target as Node)) setOpen(false);
    }
    function onKey(event: KeyboardEvent) {
      if (event.key === "Escape") {
        setOpen(false);
      }
    }
    document.addEventListener("mousedown", onPointer);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onPointer);
      document.removeEventListener("keydown", onKey);
    };
  }, [open, setOpen]);

  const q = query.trim().toLowerCase();
  const options = teams.filter(
    (t) =>
      !q ||
      t.full_name.toLowerCase().includes(q) ||
      t.abbreviation.toLowerCase().includes(q) ||
      (t.city ?? "").toLowerCase().includes(q),
  );

  return (
    <div ref={boxRef} className="relative">
      <Button
        type="button"
        variant="secondary"
        aria-haspopup="dialog"
        aria-expanded={open}
        disabled={full}
        title={full ? "A trade can involve at most three teams" : "Add a team to the trade"}
        onClick={() => setOpen(!open)}
      >
        <span aria-hidden className="text-signal">
          +
        </span>
        {full ? "Max 3 teams" : "Add team"}
      </Button>

      {open && (
        <div
          role="dialog"
          aria-label="Add a team to the trade"
          className="absolute right-0 top-full z-50 mt-2 w-[min(88vw,26rem)] overflow-hidden rounded-lg border border-line bg-panel shadow-[var(--shadow-pop)]"
        >
          <div className="border-b border-hairline p-3">
            <label htmlFor="team-picker-filter" className="eyebrow">
              Add a team
            </label>
            <input
              id="team-picker-filter"
              ref={inputRef}
              type="search"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Filter by city, name or abbreviation…"
              className="mt-1.5 w-full rounded-md border border-line bg-panel2 px-2.5 py-1.5 text-sm placeholder:text-faint focus:border-signal/60"
            />
          </div>
          <div className="scroll-thin max-h-[20rem] overflow-y-auto p-2">
            {options.length === 0 ? (
              <p className="px-2 py-6 text-center text-sm text-muted">
                No team matches “{query}”.
              </p>
            ) : (
              <ul className="grid grid-cols-4 gap-1.5 sm:grid-cols-5">
                {options.map((team) => {
                  const taken = selected.includes(team.id);
                  const identity = teamIdentity(team.abbreviation);
                  return (
                    <li key={team.id}>
                      <button
                        type="button"
                        disabled={taken}
                        aria-label={
                          taken
                            ? `${team.full_name} is already in this trade`
                            : `Add ${team.full_name} to the trade`
                        }
                        title={team.full_name}
                        onClick={() => {
                          onAdd(team.id);
                          setOpen(false);
                          setQuery("");
                        }}
                        className="flex w-full flex-col items-center gap-1 rounded-md border border-hairline bg-panel2 px-1 py-2 transition-colors hover:border-signal/50 hover:bg-panel3 disabled:opacity-35"
                      >
                        <TeamLogo abbreviation={team.abbreviation} size={26} decorative />
                        <span
                          className="numeral text-[12px] leading-none"
                          style={{ color: taken ? undefined : identity.bright }}
                        >
                          {team.abbreviation}
                        </span>
                      </button>
                    </li>
                  );
                })}
              </ul>
            )}
          </div>
          <p className="border-t border-hairline px-3 py-2 text-[11px] text-faint">
            {selected.length}/3 selected · press Escape to close
          </p>
        </div>
      )}
    </div>
  );
}

/* ---------------------------------------------------------- workspace + lane */

function TeamWorkspaceCell(props: {
  index: number;
  threeWay: boolean;
  teamIds: string[];
  teams: Team[];
  roster?: RosterResponse;
  rosterLoading: boolean;
  playerIndex: Record<string, RosterPlayer>;
  moves: Record<string, string>;
  originOf: Record<string, string>;
  validation: LegalityResponse | null;
  picks: PickMove[];
  setPicks: React.Dispatch<React.SetStateAction<PickMove[]>>;
  onRemove: () => void;
  onMove: (playerId: string, toTeamId: string) => void;
  onInspect: (player: RosterPlayer) => void;
}) {
  const { index, threeWay, teamIds, teams, moves, originOf } = props;
  const teamId = teamIds[index];
  const previousId = index > 0 ? teamIds[index - 1] : null;
  const laneActive = previousId
    ? Object.entries(moves).some(
        ([pid, to]) =>
          (originOf[pid] === previousId && to === teamId) ||
          (originOf[pid] === teamId && to === previousId),
      )
    : false;

  return (
    <>
      {previousId && (
        <LaneCell
          threeWay={threeWay}
          active={laneActive}
          left={teamIdentity(teams.find((t) => t.id === previousId)?.abbreviation).bright}
          right={teamIdentity(teams.find((t) => t.id === teamId)?.abbreviation).bright}
        />
      )}
      <TeamWorkspace {...props} teamId={teamId} />
    </>
  );
}

function LaneCell({
  threeWay,
  active,
  left,
  right,
}: {
  threeWay: boolean;
  active: boolean;
  left: string;
  right: string;
}) {
  return (
    <div
      className={
        threeWay
          ? "flex items-center justify-center gap-2 py-1 xl:min-h-[27rem] xl:flex-col xl:px-1 xl:py-0"
          : "flex items-center justify-center gap-2 py-1 lg:min-h-[27rem] lg:flex-col lg:px-1 lg:py-0"
      }
    >
      <TransactionLane
        orientation="vertical"
        active={active}
        leftColor={left}
        rightColor={right}
        className={threeWay ? "h-16 w-9 xl:hidden" : "h-16 w-9 lg:hidden"}
      />
      <TransactionLane
        orientation="horizontal"
        active={active}
        leftColor={left}
        rightColor={right}
        className={threeWay ? "hidden h-11 w-24 xl:block" : "hidden h-11 w-24 lg:block"}
      />
      <span className="eyebrow whitespace-nowrap text-[0.5625rem] text-faint">
        {active ? "assets moving" : "no assets yet"}
      </span>
    </div>
  );
}

function TeamWorkspace({
  teamId,
  teamIds,
  teams,
  roster,
  rosterLoading,
  playerIndex,
  moves,
  originOf,
  validation,
  picks,
  setPicks,
  onRemove,
  onMove,
  onInspect,
}: {
  teamId: string;
  teamIds: string[];
  teams: Team[];
  roster?: RosterResponse;
  rosterLoading: boolean;
  playerIndex: Record<string, RosterPlayer>;
  moves: Record<string, string>;
  originOf: Record<string, string>;
  validation: LegalityResponse | null;
  picks: PickMove[];
  setPicks: React.Dispatch<React.SetStateAction<PickMove[]>>;
  onRemove: () => void;
  onMove: (playerId: string, toTeamId: string) => void;
  onInspect: (player: RosterPlayer) => void;
}) {
  const team = teams.find((t) => t.id === teamId);
  const identity = teamIdentity(team?.abbreviation);
  const { setNodeRef, isOver } = useDroppable({ id: teamId });
  const legality = validation?.teams[teamId];

  const { data: detail } = useQuery({
    queryKey: ["team-detail", teamId],
    queryFn: () => api.get<TeamDetailResponse>(`/teams/${teamId}`),
    staleTime: 300_000,
  });

  const [query, setQuery] = useState("");
  const [positionFilter, setPositionFilter] = useState("");
  const [sort, setSort] = useState<"tei" | "age" | "name">("tei");
  const [pickYear, setPickYear] = useState(2027);
  const [pickTo, setPickTo] = useState("");

  const destinations: Destination[] = teamIds
    .filter((t) => t !== teamId)
    .map((t) => {
      const other = teams.find((x) => x.id === t);
      return { id: t, abbr: other?.abbreviation ?? "?", name: other?.full_name ?? "the other team" };
    });

  const all = roster?.roster ?? [];
  const staying = all
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
  const stayingTotal = all.filter((p) => (moves[p.player_id] ?? teamId) === teamId).length;
  const incoming = Object.entries(moves)
    .filter(([pid, to]) => to === teamId && originOf[pid] && originOf[pid] !== teamId)
    .map(([pid]) => playerIndex[pid])
    .filter((p): p is RosterPlayer => Boolean(p));
  const outgoing = all.filter((p) => moves[p.player_id] && moves[p.player_id] !== teamId);

  const standing = detail?.standing;
  // R2c: with partial contract coverage the verified payroll is withheld but a lower
  // bound is publishable. `≥` and the coverage count travel with the number so the
  // reader can never mistake a floor for the payroll.
  const payrollShown = payrollDisclosure(
    legality?.payroll_after,
    legality?.payroll_known_after,
    legality?.payroll_coverage_after,
  );

  return (
    <Panel
      as="section"
      accent={identity.bright}
      padded={false}
      className={`transition-colors ${isOver ? "ring-1 ring-signal" : ""}`}
    >
      <div ref={setNodeRef}>
        {/* ---------------------------------------------------------- header */}
        <header
          className="flex items-start justify-between gap-3 border-b border-hairline px-4 py-3"
          style={{ background: `linear-gradient(100deg, ${identity.primary}2e, transparent 70%)` }}
        >
          <div className="flex min-w-0 items-center gap-3">
            <TeamCrest abbreviation={team?.abbreviation} name={team?.full_name} size={44} />
            <div className="min-w-0">
              <div className="flex items-baseline gap-2">
                <span className="numeral text-2xl leading-none" style={{ color: identity.bright }}>
                  {team?.abbreviation ?? "—"}
                </span>
                {legality && (
                  <Badge status={legality.status}>{LEGALITY_SHORT[legality.status]}</Badge>
                )}
              </div>
              <h2 className="title-md mt-1 truncate text-foreground">
                {team?.full_name ?? "Loading…"}
              </h2>
              <p className="mt-0.5 truncate text-[11px] text-muted">
                {standing ? (
                  <>
                    <span className="data">
                      {standing.wins}-{standing.losses}
                    </span>
                    {standing.playoff_rank
                      ? ` · #${standing.playoff_rank} ${standing.conference ?? ""}`
                      : ""}
                    {detail?.season ? ` · ${detail.season}` : ""}
                  </>
                ) : (
                  <span className="text-faint">record not available</span>
                )}
              </p>
            </div>
          </div>
          <button
            type="button"
            onClick={onRemove}
            aria-label={`Remove ${team?.full_name ?? "team"} from the trade`}
            className="shrink-0 rounded-md border border-transparent px-2 py-1 text-muted transition-colors hover:border-illegal/40 hover:text-illegal"
          >
            <span aria-hidden>✕</span>
          </button>
        </header>

        {/* ------------------------------------------------------ ledger row */}
        <div className="grid grid-cols-2 gap-x-3 gap-y-3 border-b border-hairline px-4 py-3 sm:grid-cols-4">
          <StatBlock
            size="sm"
            label="Roster"
            value={
              legality ? (
                <span>
                  {legality.roster_before}
                  <span aria-hidden className="mx-1 text-faint">
                    →
                  </span>
                  {legality.roster_after}
                </span>
              ) : (
                all.length || "—"
              )
            }
            note={legality ? "before → after" : "players listed"}
          />
          <StatBlock
            size="sm"
            label="Out"
            value={legality?.outgoing_salary != null ? money(legality.outgoing_salary) : "—"}
            note={legality?.outgoing_salary != null ? "salary" : "no salaries"}
            title={legality?.outgoing_salary != null ? undefined : CONTRACT_TOOLTIP}
          />
          <StatBlock
            size="sm"
            label="In"
            value={legality?.incoming_salary != null ? money(legality.incoming_salary) : "—"}
            note={legality?.incoming_salary != null ? "salary" : "no salaries"}
            title={legality?.incoming_salary != null ? undefined : CONTRACT_TOOLTIP}
          />
          <StatBlock
            size="sm"
            label="Payroll"
            value={payrollShown.value}
            note={
              payrollShown.kind === "verified"
                ? `from ${money(legality?.payroll_before)}`
                : payrollShown.note
            }
            title={
              payrollShown.kind === "verified"
                ? undefined
                : payrollShown.kind === "floor"
                  ? (legality?.payroll_coverage_note ?? CONTRACT_TOOLTIP)
                  : CONTRACT_TOOLTIP
            }
          />
        </div>

        {/* --------------------------------------------------- moving assets */}
        {(incoming.length > 0 || outgoing.length > 0) && (
          <div className="space-y-2.5 border-b border-hairline bg-court/40 px-4 py-3">
            {incoming.length > 0 && (
              <AssetGroup
                direction="in"
                players={incoming}
                onUndo={(pid) => onMove(pid, originOf[pid])}
                counterpartOf={(pid) =>
                  teams.find((t) => t.id === originOf[pid])?.abbreviation ?? "?"
                }
              />
            )}
            {outgoing.length > 0 && (
              <AssetGroup
                direction="out"
                players={outgoing}
                onUndo={(pid) => onMove(pid, teamId)}
                counterpartOf={(pid) =>
                  teams.find((t) => t.id === moves[pid])?.abbreviation ?? "?"
                }
              />
            )}
          </div>
        )}

        {/* --------------------------------------------------- roster filters */}
        <div className="flex flex-wrap items-center gap-1.5 border-b border-hairline px-3 py-2">
          <input
            type="search"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Filter roster…"
            aria-label={`Filter the ${team?.full_name ?? "team"} roster by name`}
            className="min-w-0 flex-1 rounded-md border border-line bg-panel2 px-2 py-1 text-[13px] placeholder:text-faint focus:border-signal/60"
          />
          <select
            value={positionFilter}
            onChange={(e) => setPositionFilter(e.target.value)}
            aria-label={`Filter the ${team?.abbreviation ?? "team"} roster by position`}
            className="rounded-md border border-line bg-panel2 px-1.5 py-1 text-[13px]"
          >
            <option value="">All</option>
            <option value="G">Guards</option>
            <option value="F">Forwards</option>
            <option value="C">Centers</option>
          </select>
          <select
            value={sort}
            onChange={(e) => setSort(e.target.value as "tei" | "age" | "name")}
            aria-label={`Sort the ${team?.abbreviation ?? "team"} roster`}
            className="rounded-md border border-line bg-panel2 px-1.5 py-1 text-[13px]"
          >
            <option value="tei">Impact</option>
            <option value="age">Age</option>
            <option value="name">Name</option>
          </select>
        </div>

        {/* ------------------------------------------------------ roster list */}
        <div className="scroll-thin max-h-[26rem] space-y-1.5 overflow-y-auto p-2">
          {!roster && rosterLoading ? (
            <SkeletonRows rows={6} height="h-[3.25rem]" />
          ) : staying.length === 0 ? (
            <div className="px-3 py-8 text-center">
              <p className="title-md text-foreground">
                {stayingTotal === 0 ? "Everyone is on the move" : "No player matches"}
              </p>
              <p className="mx-auto mt-1 max-w-xs text-[13px] leading-relaxed text-muted">
                {stayingTotal === 0
                  ? "Every listed player has been sent out. Undo one above to bring them back."
                  : "Clear the filter or choose a different position to see the rest of the roster."}
              </p>
              {stayingTotal > 0 && (
                <Button
                  size="sm"
                  className="mt-3"
                  onClick={() => {
                    setQuery("");
                    setPositionFilter("");
                  }}
                >
                  Clear filters
                </Button>
              )}
            </div>
          ) : (
            staying.map((player) => (
              <RosterCard
                key={player.player_id}
                player={player}
                destinations={destinations}
                onMove={onMove}
                onInspect={() => onInspect(player)}
              />
            ))
          )}
        </div>

        {/* ------------------------------------------------------------ picks */}
        <div className="border-t border-hairline px-4 py-2.5">
          <details className="group">
            <summary className="eyebrow cursor-pointer list-none text-muted transition-colors hover:text-foreground">
              <span aria-hidden className="mr-1.5 inline-block transition-transform group-open:rotate-90">
                ›
              </span>
              Draft picks · ownership unverified
            </summary>
            <div className="mt-2.5 flex flex-wrap items-center gap-2 text-[13px]">
              <label className="sr-only" htmlFor={`pick-year-${teamId}`}>
                Draft year to send from {team?.abbreviation}
              </label>
              <select
                id={`pick-year-${teamId}`}
                value={pickYear}
                onChange={(e) => setPickYear(Number(e.target.value))}
                className="rounded-md border border-line bg-panel2 px-1.5 py-1"
              >
                {[2027, 2028, 2029, 2030, 2031].map((y) => (
                  <option key={y}>{y}</option>
                ))}
              </select>
              <span className="whitespace-nowrap text-muted">1st round →</span>
              <label className="sr-only" htmlFor={`pick-to-${teamId}`}>
                Team receiving the pick
              </label>
              <select
                id={`pick-to-${teamId}`}
                value={pickTo}
                onChange={(e) => setPickTo(e.target.value)}
                className="rounded-md border border-line bg-panel2 px-1.5 py-1"
              >
                <option value="">to…</option>
                {destinations.map((d) => (
                  <option key={d.id} value={d.id}>
                    {d.abbr}
                  </option>
                ))}
              </select>
              <Button
                size="sm"
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
              >
                Add pick
              </Button>
            </div>
            <p className="mt-2 text-[11px] leading-snug text-faint">
              Pick ownership isn&apos;t imported, so every pick added here is labeled hypothetical
              and never counted as verified capital.
            </p>
            <ul className="mt-1.5 space-y-1">
              {picks
                .filter((p) => p.from_team_id === teamId)
                .map((p, i) => (
                  <li
                    key={`${p.draft_year}-${p.to_team_id}-${i}`}
                    className="flex items-center justify-between gap-2 text-[12px]"
                  >
                    <span className="flex min-w-0 items-center gap-1.5">
                      <span className="data whitespace-nowrap">
                        {p.draft_year} R{p.round_number}
                      </span>
                      <span aria-hidden className="text-faint">
                        →
                      </span>
                      <span className="numeral">
                        {teams.find((x) => x.id === p.to_team_id)?.abbreviation}
                      </span>
                      <Badge status="unavailable">hypothetical</Badge>
                    </span>
                    <button
                      type="button"
                      className="shrink-0 text-[11px] text-muted underline transition-colors hover:text-illegal"
                      aria-label={`Remove the ${p.draft_year} first-round pick from this trade`}
                      onClick={() => setPicks((prev) => prev.filter((x) => x !== p))}
                    >
                      remove
                    </button>
                  </li>
                ))}
            </ul>
          </details>
        </div>

        <div className="px-4 pb-3">
          <SourceRail
            source={roster?.source ?? "NBA.com via nba_api"}
            retrievedAt={roster?.source_retrieved_at ?? null}
          />
        </div>
      </div>
    </Panel>
  );
}

function AssetGroup({
  direction,
  players,
  onUndo,
  counterpartOf,
}: {
  direction: "in" | "out";
  players: RosterPlayer[];
  onUndo: (playerId: string) => void;
  counterpartOf: (playerId: string) => string;
}) {
  const isIn = direction === "in";
  return (
    <div>
      <div className="flex items-center gap-2">
        <span
          className={`eyebrow flex items-center gap-1.5 ${isIn ? "text-legal" : "text-illegal"}`}
        >
          <span aria-hidden className="data text-xs">
            {isIn ? "←" : "→"}
          </span>
          {isIn ? "In" : "Out"}
        </span>
        <span className="text-[11px] text-faint">
          {players.length} player{players.length === 1 ? "" : "s"}
        </span>
      </div>
      <ul className="mt-1.5 space-y-1">
        {players.map((p) => (
          <li
            key={p.player_id}
            className="lane-in flex items-center gap-2 rounded-md border px-2 py-1.5"
            style={{
              // Arriving assets travel in from the lane; departing assets lean out.
              ["--lane-from" as string]: isIn ? "-14px" : "14px",
              borderColor: isIn ? "rgb(52 211 153 / 0.35)" : "rgb(251 113 133 / 0.35)",
              background: isIn ? "rgb(52 211 153 / 0.07)" : "rgb(251 113 133 / 0.07)",
            }}
          >
            <PlayerPhoto nbaPlayerId={p.nba_player_id} name={p.name} size={26} />
            <span className="min-w-0 flex-1 truncate text-[13px]">{p.name}</span>
            <span className="numeral whitespace-nowrap text-[12px] text-muted">
              {isIn ? "from" : "to"} {counterpartOf(p.player_id)}
            </span>
            <button
              type="button"
              onClick={() => onUndo(p.player_id)}
              aria-label={`Undo moving ${p.name}`}
              className="shrink-0 rounded px-1 text-[11px] text-signal underline"
            >
              undo
            </button>
          </li>
        ))}
      </ul>
    </div>
  );
}

function RosterCard({
  player,
  destinations,
  onMove,
  onInspect,
}: {
  player: RosterPlayer;
  destinations: Destination[];
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
      className={`flex flex-wrap items-center gap-x-2.5 gap-y-2 rounded-lg border border-hairline bg-panel2/60 p-2 transition-colors hover:border-signal/40 ${
        isDragging ? "opacity-30" : ""
      }`}
    >
      <button
        type="button"
        {...listeners}
        {...attributes}
        aria-label={`Drag ${player.name} to another team`}
        className="shrink-0 cursor-grab touch-none px-0.5 text-faint transition-colors hover:text-foreground"
      >
        <span aria-hidden>⠿</span>
      </button>
      <button
        type="button"
        onClick={onInspect}
        className="flex min-w-0 flex-[1_1_8rem] items-center gap-2.5 text-left"
        aria-label={`Open details for ${player.name}`}
      >
        <PlayerPhoto nbaPlayerId={player.nba_player_id} name={player.name} size={38} square />
        <span className="min-w-0">
          <span
            className="block truncate text-[13px] font-semibold leading-tight text-foreground"
            title={player.name}
          >
            {player.name}
          </span>
          <span className="mt-0.5 block truncate text-[11px] leading-tight text-muted">
            {player.position ?? "—"} · {player.age ? `${player.age.toFixed(0)}y` : "age —"}
            {player.archetype ? ` · ${player.archetype}` : ""}
          </span>
          {/* Real contract data. This line was two hardcoded em-dashes until R2b, so a
              contracts import changed nothing here and the defect became invisible the
              moment the import was marked done. */}
          <span
            className="mt-0.5 block text-[10px] leading-tight text-faint"
            title={player.salary === null ? CONTRACT_TOOLTIP : undefined}
          >
            salary <span className="data">{player.salary === null ? "—" : money(player.salary)}</span> ·
            years{" "}
            <span className="data">
              {player.contract_years_remaining === null ? "—" : player.contract_years_remaining}
            </span>
            {player.contract_type && ` · ${player.contract_type}`}
          </span>
        </span>
      </button>
      <span className="shrink-0 text-right" title="Estimated player impact (TEI) — see Methodology">
        <span className="eyebrow block text-[0.5rem]">Impact</span>
        <span
          className={`numeral text-lg leading-none ${
            (player.tei ?? 0) >= 0 ? "text-foreground" : "text-muted"
          }`}
        >
          {tei(player.tei)}
        </span>
      </span>
      <span className="ml-auto flex shrink-0 gap-1">
        {destinations.map((d) => (
          <button
            key={d.id}
            type="button"
            onClick={() => onMove(player.player_id, d.id)}
            aria-label={`Send ${player.name} to ${d.abbr}`}
            title={`Send ${player.name} to the ${d.name}`}
            className="numeral flex items-center gap-0.5 whitespace-nowrap rounded-md border border-line px-1.5 py-1 text-[12px] text-muted transition-colors hover:border-signal hover:text-signal"
          >
            <span aria-hidden>→</span>
            {d.abbr}
          </button>
        ))}
      </span>
    </div>
  );
}

/* --------------------------------------------------------------- empty flow */

/** The 30-franchise board — the fastest way into a deal, reused by both empty states. */
function TeamBoard({
  teams,
  selected,
  onAdd,
  columns = "grid-cols-5 sm:grid-cols-8 lg:grid-cols-10",
}: {
  teams: Team[];
  selected: string[];
  onAdd: (id: string) => void;
  columns?: string;
}) {
  if (teams.length === 0) {
    return (
      <div className={`grid gap-1.5 ${columns}`}>
        {Array.from({ length: 30 }).map((_, i) => (
          <Skeleton key={i} className="h-[58px]" />
        ))}
      </div>
    );
  }
  return (
    <ul className={`grid gap-1.5 ${columns}`}>
      {teams.map((team) => {
        const taken = selected.includes(team.id);
        const identity = teamIdentity(team.abbreviation);
        return (
          <li key={team.id}>
            <button
              type="button"
              disabled={taken}
              aria-label={
                taken ? `${team.full_name} is already in this trade` : `Add ${team.full_name} to the trade`
              }
              title={team.full_name}
              onClick={() => onAdd(team.id)}
              className="flex w-full flex-col items-center gap-1 rounded-lg border border-hairline bg-panel2/70 px-1 py-2 transition-colors hover:border-signal/50 hover:bg-panel3 disabled:opacity-30"
            >
              <TeamLogo abbreviation={team.abbreviation} size={28} decorative />
              <span
                className="numeral text-[12px] leading-none"
                style={{ color: taken ? undefined : identity.bright }}
              >
                {team.abbreviation}
              </span>
            </button>
          </li>
        );
      })}
    </ul>
  );
}

function StartHere({
  teams,
  onAdd,
  onPick,
}: {
  teams: Team[];
  onAdd: (id: string) => void;
  onPick: () => void;
}) {
  return (
    <Panel padded={false} className="relative overflow-hidden">
      <HalfCourt className="pointer-events-none absolute -bottom-20 right-[-8%] h-[150%] w-[52%] text-signal/15 sm:w-[38%]" />
      <div className="relative p-4 sm:p-6">
        <EmptyState
          title="Put two teams on the board"
          hint="A deal needs both sides. Pick the franchises you want to trade between — the rules check starts running the moment an asset crosses the lane."
          action={
            <>
              <Button variant="primary" onClick={onPick}>
                Search for a team
              </Button>
              <ButtonLink href="/team-outlook" variant="secondary">
                Browse team outlooks
              </ButtonLink>
            </>
          }
        />
        <div className="mt-5 border-t border-hairline pt-4">
          <div className="mb-2.5 flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
            <span className="eyebrow">Or start from a franchise</span>
            <span className="text-[11px] text-faint">One click puts them on the board</span>
          </div>
          <TeamBoard teams={teams} selected={[]} onAdd={onAdd} />
        </div>
      </div>
    </Panel>
  );
}

function AddPartnerSlot({
  teams,
  selected,
  onAdd,
}: {
  teams: Team[];
  selected: string[];
  onAdd: (id: string) => void;
}) {
  return (
    <div className="panel relative flex min-h-[260px] flex-col justify-center overflow-hidden border-dashed p-5">
      {/* The court grid is a backdrop; masking it on the container would fade the tiles. */}
      <span aria-hidden className="court-grid pointer-events-none absolute inset-0" />
      <div className="relative text-center">
        <TransactionLane className="mx-auto h-11 w-28" />
        <p className="title-md mt-2 text-foreground">Add a trade partner</p>
        <p className="mx-auto mt-1 max-w-xs text-[13px] leading-relaxed text-muted">
          One side is set. Choose who&apos;s on the other end of the call and the live rules check
          turns on.
        </p>
      </div>
      <div className="relative mt-4">
        <TeamBoard
          teams={teams}
          selected={selected}
          onAdd={onAdd}
          columns="grid-cols-5 sm:grid-cols-6"
        />
      </div>
    </div>
  );
}

/** The transaction receipt: every asset that changes hands, in plain language. */
function DealLedger({
  teams,
  playerMoves,
  picks,
  playerIndex,
}: {
  teams: Team[];
  playerMoves: PlayerMove[];
  picks: PickMove[];
  playerIndex: Record<string, RosterPlayer>;
}) {
  const abbr = (id: string) => teams.find((t) => t.id === id)?.abbreviation ?? "—";
  if (playerMoves.length === 0 && picks.length === 0) {
    return (
      <Panel title="Deal ledger" subtitle="Nothing is moving yet.">
        <p className="text-[13px] leading-relaxed text-muted">
          Send a player across the lane and every asset in the deal is listed here, with the team it
          leaves and the team it joins.
        </p>
      </Panel>
    );
  }
  return (
    <Panel
      title="Deal ledger"
      subtitle={`${playerMoves.length} player${playerMoves.length === 1 ? "" : "s"}${
        picks.length > 0 ? ` · ${picks.length} pick${picks.length === 1 ? "" : "s"}` : ""
      } changing hands`}
    >
      <ul className="space-y-2">
        {playerMoves.map((move) => {
          const player = playerIndex[move.player_id];
          return (
            <li key={move.player_id} className="flex items-center gap-2">
              <PlayerPhoto
                nbaPlayerId={player?.nba_player_id}
                name={player?.name ?? "Player"}
                size={24}
              />
              <span className="min-w-0 flex-1 truncate text-[13px]">
                {player?.name ?? "Player"}
              </span>
              <span className="numeral flex shrink-0 items-center gap-1 whitespace-nowrap text-[12px] text-muted">
                {abbr(move.from_team_id)}
                <span aria-hidden className="text-signal">
                  →
                </span>
                {abbr(move.to_team_id)}
              </span>
            </li>
          );
        })}
        {picks.map((pick, i) => (
          <li key={`pick-${i}`} className="flex items-center gap-2">
            <span
              aria-hidden
              className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-panel3 text-[10px] text-muted"
            >
              R{pick.round_number}
            </span>
            <span className="min-w-0 flex-1 truncate text-[13px]">
              {pick.draft_year} round {pick.round_number}{" "}
              <Badge status="unavailable">hypothetical</Badge>
            </span>
            <span className="numeral flex shrink-0 items-center gap-1 whitespace-nowrap text-[12px] text-muted">
              {abbr(pick.from_team_id)}
              <span aria-hidden className="text-signal">
                →
              </span>
              {abbr(pick.to_team_id)}
            </span>
          </li>
        ))}
      </ul>
    </Panel>
  );
}

function HowItWorks({ variant = "strip" }: { variant?: "strip" | "rail" }) {
  const rail = variant === "rail";
  return (
    <section
      className={
        rail
          ? "rounded-xl border border-hairline px-4 py-3.5"
          : "hardwood rounded-xl border border-hairline px-4 py-4"
      }
    >
      <div className="eyebrow mb-3">How the evaluator works</div>
      <ol className={rail ? "space-y-3" : "grid gap-x-6 gap-y-3 sm:grid-cols-3"}>
        {HOW_IT_WORKS.map((item) => (
          <li key={item.step} className="flex gap-3">
            <span className="numeral shrink-0 text-xl leading-none text-signal">{item.step}</span>
            <span className="min-w-0">
              <span className="block whitespace-nowrap text-sm font-semibold text-foreground">
                {item.title}
              </span>
              <span className="mt-0.5 block text-[12px] leading-snug text-muted">{item.body}</span>
            </span>
          </li>
        ))}
      </ol>
    </section>
  );
}

/* -------------------------------------------------------------- rules check */

function RulesCheck({
  validation,
  validating,
  hasMoves,
  className,
}: {
  validation: LegalityResponse | null;
  validating: boolean;
  hasMoves: boolean;
  className?: string;
}) {
  const status = validation?.overall_status;
  const visual = status ? LEGALITY_VISUAL[status] : null;
  const blocked = validation?.rule_results.filter((r) => r.status === "unavailable") ?? [];

  return (
    <Panel
      className={className}
      title="Live rules check"
      subtitle={
        validation
          ? `Cap year ${validation.league_year} · every result below comes from the backend rules engine, not the browser.`
          : "The check runs automatically the moment a player crosses the lane."
      }
      accent={visual?.color ?? "var(--signal)"}
      actions={
        validating ? (
          <span className="eyebrow flex items-center gap-1.5 text-signal">
            <span className="pulse-live h-1.5 w-1.5 rounded-full bg-signal" aria-hidden />
            Checking
          </span>
        ) : null
      }
    >
      {!validation ? (
        validating || hasMoves ? (
          <div className="space-y-3">
            <Skeleton className="h-24" />
            <SkeletonRows rows={3} height="h-9" />
          </div>
        ) : (
          <EmptyState
            title="No check to run yet"
            hint="Move at least one player between the teams and RosterLab validates the deal against the 2023 CBA rules it can verify."
          />
        )
      ) : (
        <div className="space-y-4">
          {/* --------------------------------------------- headline verdict */}
          <KeyFrame accent={visual?.color} className="rounded-lg border border-hairline bg-court/50 px-4 pb-4 pt-5">
            <div className="flex flex-wrap items-center gap-x-3 gap-y-1.5">
              <span
                aria-hidden
                className={`numeral text-3xl leading-none ${visual?.text ?? ""}`}
                style={{ color: visual?.color }}
              >
                {visual?.glyph}
              </span>
              <h3 className={`title-lg whitespace-nowrap ${visual?.text ?? "text-foreground"}`}>
                {LEGALITY_LABEL[status ?? "not_evaluated"]}
              </h3>
            </div>
            <p className="mt-2 max-w-2xl text-sm leading-relaxed text-muted">
              {LEGALITY_EXPLAIN[status ?? "not_evaluated"]}
            </p>
            {status !== "verified_legal" && (
              <p className="mt-2 text-[12px] leading-relaxed text-faint">
                RosterLab never reports a deal as legal while a required check is missing — an
                incomplete check stays incomplete.
              </p>
            )}
          </KeyFrame>

          {/* ------------------------------------- what could not be checked */}
          {!validation.contract_provider_configured && (
            <UnavailableNotice
              reason={
                <>
                  Contract data isn&apos;t imported, so{" "}
                  {blocked.length > 0 ? (
                    <>
                      {blocked.length} check{blocked.length === 1 ? "" : "s"} could not run:{" "}
                      <span className="data text-[12px] text-foreground">
                        {[...new Set(blocked.map((r) => r.rule_code))].join(", ")}
                      </span>
                      .
                    </>
                  ) : (
                    "salary-matching checks could not run."
                  )}{" "}
                  Everything that depends on salary — matching bands, aprons and payroll — stays
                  unavailable rather than estimated.
                </>
              }
              steps={
                <ButtonLink href="/salary-cap-center" size="sm" variant="secondary">
                  Open the Salary-Cap Center
                </ButtonLink>
              }
            />
          )}

          {/* -------------------------------------------------- rule details */}
          <div>
            <div className="eyebrow mb-2">Rule by rule</div>
            <ul className="scroll-thin max-h-[22rem] space-y-1.5 overflow-y-auto pr-1">
              {validation.rule_results.map((rule, i) => (
                <RuleRow
                  key={`${rule.rule_code}-${i}`}
                  rule={rule}
                  teamAbbr={rule.team_id ? validation.teams[rule.team_id]?.abbreviation : undefined}
                />
              ))}
            </ul>
          </div>

          <SourceRail
            source={`Rules engine · 2023 CBA · cap parameters from ${validation.cap_parameters_source}`}
          />
        </div>
      )}
    </Panel>
  );
}

function RuleRow({ rule, teamAbbr }: { rule: RuleResult; teamAbbr?: string }) {
  const entries = Object.entries(rule.calculation ?? {});
  return (
    <li className="rounded-md border border-hairline bg-panel2/50">
      <details className="group">
        <summary className="flex cursor-pointer list-none items-start gap-2 px-2.5 py-2">
          <Badge status={rule.status} className="mt-0.5 shrink-0">
            {RULE_STATUS_WORD[rule.status] ?? rule.status}
          </Badge>
          {teamAbbr && (
            <span
              className="numeral mt-0.5 shrink-0 whitespace-nowrap rounded border border-line px-1.5 text-[12px] leading-5 text-muted"
              style={{ color: teamIdentity(teamAbbr).bright }}
            >
              {teamAbbr}
            </span>
          )}
          <span className="min-w-0 flex-1 text-[13px] leading-snug">{rule.message}</span>
          <span
            aria-hidden
            className="mt-0.5 shrink-0 text-faint transition-transform group-open:rotate-90"
          >
            ›
          </span>
        </summary>
        <div className="space-y-2 border-t border-hairline px-2.5 py-2 text-[12px]">
          <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
            <span className="data text-[11px] text-signal">{rule.rule_code}</span>
            <span className="text-faint">confidence: {rule.confidence}</span>
          </div>
          {entries.length > 0 && (
            <dl className="grid gap-x-4 gap-y-1 sm:grid-cols-2">
              {entries.map(([key, value]) => (
                <div key={key} className="flex justify-between gap-2 border-b border-hairline/60 pb-1">
                  <dt className="truncate text-muted">{key.replaceAll("_", " ")}</dt>
                  <dd className="data shrink-0 text-right text-foreground">
                    {typeof value === "number"
                      ? Math.abs(value) >= 100_000
                        ? money(value)
                        : String(value)
                      : Array.isArray(value)
                        ? value.join(", ") || "—"
                        : String(value)}
                  </dd>
                </div>
              ))}
            </dl>
          )}
          <p className="text-[11px] leading-snug text-faint">Reference: {rule.source_reference}</p>
        </div>
      </details>
    </li>
  );
}

/* ------------------------------------------------------------- save & share */

function SaveShare({
  tradeName,
  setTradeName,
  canAct,
  evaluating,
  saving,
  onEvaluate,
  onSave,
  onCopy,
}: {
  tradeName: string;
  setTradeName: (value: string) => void;
  canAct: boolean;
  evaluating: boolean;
  saving: boolean;
  onEvaluate: () => void;
  onSave: () => void;
  onCopy: () => void;
}) {
  return (
    <Panel title="Run it" subtitle="Evaluate now, then keep the deal for comparison." accent="var(--leather)">
      <div className="space-y-3">
        <div>
          <label htmlFor="deal-name" className="eyebrow">
            Deal name
          </label>
          <input
            id="deal-name"
            value={tradeName}
            onChange={(e) => setTradeName(e.target.value)}
            placeholder="Name this deal…"
            className="mt-1.5 w-full rounded-md border border-line bg-panel2 px-2.5 py-1.5 text-sm placeholder:text-faint focus:border-signal/60"
          />
        </div>
        <Button
          variant="primary"
          className="w-full"
          disabled={!canAct || evaluating}
          onClick={onEvaluate}
        >
          {evaluating ? "Evaluating…" : "Evaluate this deal"}
        </Button>
        <div className="flex gap-2">
          <Button className="flex-1" disabled={!canAct || saving} onClick={onSave}>
            {saving ? "Saving…" : "Save deal"}
          </Button>
          <Button className="flex-1" disabled={!canAct} onClick={onCopy}>
            Copy share link
          </Button>
        </div>
        {!canAct && (
          <p className="text-[11px] leading-snug text-faint">
            Move at least one player between teams to enable these actions.
          </p>
        )}
        <p className="text-[11px] leading-snug text-faint">
          Saved deals line up in{" "}
          <Link href="/strategy-lab" className="text-signal underline">
            Strategy Lab
          </Link>{" "}
          so you can rank them under your own priorities.
        </p>
      </div>
    </Panel>
  );
}

/* -------------------------------------------------------- evaluation report */

function EvaluationSection({
  evaluation,
  teams,
  teamIds,
}: {
  evaluation: { legality: LegalityResponse; evaluations: Record<string, TeamEvaluation> };
  teams: Team[];
  teamIds: string[];
}) {
  const [activeTeam, setActiveTeam] = useState(teamIds[0]);
  const resolvedTeam = evaluation.evaluations[activeTeam] ? activeTeam : teamIds[0];
  const teamEval = evaluation.evaluations[resolvedTeam];
  const team = teams.find((t) => t.id === resolvedTeam);
  const identity = teamIdentity(team?.abbreviation);
  if (!teamEval) return null;

  return (
    <Panel
      title="Deal evaluation"
      subtitle="One team's point of view at a time — headline verdict first, the full analysis underneath."
      accent={identity.bright}
      actions={
        <Tabs
          ariaLabel="Team perspective"
          active={resolvedTeam}
          onChange={setActiveTeam}
          tabs={teamIds
            .filter((tid) => evaluation.evaluations[tid])
            .map((tid) => ({
              id: tid,
              label: teams.find((t) => t.id === tid)?.abbreviation ?? "—",
            }))}
        />
      }
    >
      <TeamEvaluationView
        key={resolvedTeam}
        teamEval={teamEval}
        identity={identity}
        teamAbbreviations={Object.fromEntries(
          Object.entries(evaluation.legality.teams).map(([id, t]) => [id, t.abbreviation]),
        )}
      />
    </Panel>
  );
}

/**
 * Players the impact model has never scored are excluded from the projection and named
 * here. Before R1-4 they arrived carrying `tei = 0.0` — the 63rd percentile of rostered
 * players — so a player with no data quietly moved the number.
 */
function UnmodeledNotice({ teamEval }: { teamEval: TeamEvaluation }) {
  const names = teamEval.unmodeled_players ?? [];
  if (!teamEval.has_unmodeled_players || names.length === 0) return null;
  const inDeal = [...teamEval.incoming, ...teamEval.outgoing]
    .filter((p) => p.tei === null)
    .map((p) => p.name);
  return (
    <p className="mt-2 border-t border-hairline pt-2.5 text-[11px] leading-snug text-unavail">
      {names.length === 1 ? "1 player has" : `${names.length} players have`} no impact
      estimate and {names.length === 1 ? "was" : "were"} left out of the projection rather
      than given a league-average stand-in: {names.join(", ")}.
      {inDeal.length > 0 && (
        <>
          {" "}
          {inDeal.length === 1 ? "One of them is" : "Some of them are"} in this deal (
          {inDeal.join(", ")}), so confidence is reported as low.
        </>
      )}{" "}
      They still count against the roster limits.
    </p>
  );
}

function TeamEvaluationView({
  teamEval,
  identity,
  teamAbbreviations,
}: {
  teamEval: TeamEvaluation;
  identity: ReturnType<typeof teamIdentity>;
  teamAbbreviations: Record<string, string>;
}) {
  const [tab, setTab] = useState("impact");
  const verdict = fanVerdict(teamEval.composite_utility, teamEval.confidence);
  const suppressed = teamEval.decision_status === "suppressed_illegal";
  const perf = sectionOf<PerformanceDetail>(teamEval.detail, "performance");
  const gained = teamEval.drivers?.filter((d) => d.contribution > 0.5).slice(0, 3) ?? [];
  const lost = teamEval.drivers?.filter((d) => d.contribution < -0.5).slice(0, 3) ?? [];
  const payrollDelta =
    teamEval.legality.payroll_after !== null && teamEval.legality.payroll_before !== null
      ? teamEval.legality.payroll_after - teamEval.legality.payroll_before
      : null;

  if (suppressed) {
    // A deal that fails a verified rule cannot be executed, so it gets no verdict, no
    // score and no component breakdown — only the reason and the rules that caused it.
    return (
      <div
        className="rounded-lg border px-4 py-4"
        style={{ borderColor: "var(--illegal)", background: "rgb(248 113 113 / 0.06)" }}
      >
        <div className="flex items-center gap-2">
          <TeamLogo abbreviation={identity.abbreviation} size={18} decorative />
          <span className="eyebrow">Verdict for {identity.abbreviation}</span>
        </div>
        <h3 className="title-lg mt-1.5 text-foreground">No decision score — this deal is illegal</h3>
        <p className="mt-2 max-w-prose text-[13px] leading-relaxed text-muted">
          {teamEval.suppression?.message}
        </p>
        <ul className="mt-3 space-y-2">
          {(teamEval.suppression?.failing_rules ?? []).map((rule, index) => (
            <li
              key={`${rule.rule_code}-${rule.team_id ?? "all"}-${index}`}
              className="rounded-lg border border-hairline bg-panel2 px-3 py-2"
            >
              <div className="eyebrow flex flex-wrap items-center gap-2 text-[0.5625rem] text-illegal">
                <span>{rule.rule_code}</span>
                {/* A deal can be illegal because of the counterparty; naming the side
                    keeps the refusal from reading as a fault of this team. */}
                {rule.team_id && teamAbbreviations[rule.team_id] && (
                  <span className="text-unavail">fails for {teamAbbreviations[rule.team_id]}</span>
                )}
              </div>
              <p className="mt-0.5 text-sm text-foreground">{rule.message}</p>
            </li>
          ))}
        </ul>
        <p className="mt-3 border-t border-hairline pt-2.5 text-[11px] leading-snug text-faint">
          Salary in {money(teamEval.legality.incoming_salary)} · out{" "}
          {money(teamEval.legality.outgoing_salary)} · roster{" "}
          {teamEval.legality.roster_before} → {teamEval.legality.roster_after}. Fix the rule
          failures above and evaluate again.
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-5">
      {/* ------------------------------------------------- 1. headline verdict */}
      <div
        className="rounded-lg border px-4 py-4"
        style={{
          borderColor: `${identity.bright}40`,
          background: `linear-gradient(120deg, ${identity.primary}22, transparent 70%)`,
        }}
      >
        <div className="flex flex-wrap items-end justify-between gap-x-6 gap-y-3">
          <div className="min-w-0">
            <div className="flex items-center gap-2">
              <TeamLogo abbreviation={identity.abbreviation} size={18} decorative />
              <span className="eyebrow">Verdict for {identity.abbreviation}</span>
            </div>
            <h3 className="title-lg mt-1.5 whitespace-nowrap text-foreground">
              {VERDICT_LABEL[verdict]}
            </h3>
            <p className="mt-1.5 text-[12px] text-muted">
              Confidence {teamEval.confidence} ·{" "}
              <Link href="/methodology#utility" className="text-signal underline">
                how this is calculated
              </Link>
            </p>
          </div>
          <div className="flex shrink-0 items-end gap-5">
            <StatBlock
              size="lg"
              align="right"
              label="Decision score"
              value={
                teamEval.composite_utility != null ? teamEval.composite_utility.toFixed(0) : "—"
              }
              note="0–100 · 50 is neutral"
              accent={identity.bright}
            />
          </div>
        </div>
        {teamEval.excluded_components.length > 0 && (
          <p className="mt-3 border-t border-hairline pt-2.5 text-[11px] leading-snug text-unavail">
            Not scored because the data is missing:{" "}
            {teamEval.excluded_components.map((c) => COMPONENT_LABEL[c] ?? c).join(", ")} — the
            remaining weights were rescaled so the score stays comparable.
          </p>
        )}
        <UnmodeledNotice teamEval={teamEval} />
      </div>

      {/* ------------------------------------------------- 2. impact summary */}
      <div className="grid gap-4 lg:grid-cols-[minmax(0,1.4fr)_minmax(0,1fr)]">
        <div className="rounded-lg border border-hairline bg-panel2/40 p-3.5">
          <UncertaintyStrip u={teamEval.uncertainty} />
          {perf.delta_net_rating !== undefined && (
            <p className="mt-2 text-[11px] text-faint">
              Modeled net-rating change{" "}
              <span className="data text-muted">
                {perf.delta_net_rating >= 0 ? "+" : ""}
                {perf.delta_net_rating.toFixed(2)}
              </span>{" "}
              per 100 possessions after reallocating rotation minutes.
            </p>
          )}
        </div>
        <div className="grid grid-cols-2 gap-3">
          <div className="rounded-lg border border-hairline bg-panel2/40 p-3">
            <StatBlock
              size="sm"
              label="Payroll change"
              value={payrollDelta !== null ? money(payrollDelta) : "—"}
              note={payrollDelta !== null ? "committed salary" : "contracts not imported"}
              title={payrollDelta !== null ? undefined : CONTRACT_TOOLTIP}
            />
          </div>
          <div className="rounded-lg border border-hairline bg-panel2/40 p-3">
            <StatBlock
              size="sm"
              label="Roster spots"
              value={`${teamEval.legality.roster_before} → ${teamEval.legality.roster_after}`}
              note="players under contract"
            />
          </div>
          <div className="col-span-2 rounded-lg border border-hairline bg-panel2/40 p-3">
            <div className="eyebrow text-[0.5625rem]">Strengths gained / lost</div>
            <div className="mt-1.5 space-y-1 text-[12px] leading-snug">
              {gained.length > 0 && (
                <p className="text-legal">
                  <span aria-hidden>▲</span> gained:{" "}
                  {gained.map((d) => COMPONENT_LABEL[d.component] ?? d.component).join(", ")}
                </p>
              )}
              {lost.length > 0 && (
                <p className="text-illegal">
                  <span aria-hidden>▼</span> lost:{" "}
                  {lost.map((d) => COMPONENT_LABEL[d.component] ?? d.component).join(", ")}
                </p>
              )}
              {gained.length === 0 && lost.length === 0 && (
                <p className="text-muted">Roughly neutral across every scored component.</p>
              )}
            </div>
          </div>
        </div>
      </div>

      {/* ------------------------------------------------ 3. advanced section */}
      <div>
        <div className="border-b border-hairline">
          <Tabs
            ariaLabel="Advanced analysis"
            active={tab}
            onChange={setTab}
            tabs={[
              { id: "impact", label: "Impact" },
              { id: "fit", label: "Fit" },
              { id: "cap", label: "Cap" },
              { id: "timeline", label: "Timeline" },
              { id: "risk", label: "Risk & uncertainty" },
            ]}
          />
        </div>
        <div className="pt-4">
          {tab === "impact" && <ImpactTab teamEval={teamEval} perf={perf} />}
          {tab === "fit" && <FitTab teamEval={teamEval} />}
          {tab === "cap" && <CapTab teamEval={teamEval} />}
          {tab === "timeline" && <TimelineTab teamEval={teamEval} />}
          {tab === "risk" && <RiskTab teamEval={teamEval} />}
        </div>
      </div>

      <SourceRail
        source="RosterLab evaluation model over ingested NBA data"
        retrievedAt={teamEval.evaluated_at}
      />
    </div>
  );
}

function ImpactTab({ teamEval, perf }: { teamEval: TeamEvaluation; perf: PerformanceDetail }) {
  const rows = useMemo(() => {
    const before = perf.rotation_before ?? [];
    const after = perf.rotation_after ?? [];
    if (before.length === 0 && after.length === 0) return [];
    const byId = new Map<string, { name: string; before: number; after: number }>();
    for (const r of before) byId.set(r.player_id, { name: r.name, before: r.minutes, after: 0 });
    for (const r of after) {
      const existing = byId.get(r.player_id);
      if (existing) existing.after = r.minutes;
      else byId.set(r.player_id, { name: r.name, before: 0, after: r.minutes });
    }
    return [...byId.values()]
      .sort((a, b) => Math.max(b.before, b.after) - Math.max(a.before, a.after))
      .slice(0, 8);
  }, [perf]);

  return (
    <div className="grid gap-6 lg:grid-cols-2">
      <div className="min-w-0">
        {/* Cyan is the chart voice; the diverging red already means "below neutral". */}
        <ComponentBars components={teamEval.components} excluded={teamEval.excluded_components} />
        <dl className="mt-3 space-y-1.5 text-[11px] leading-snug text-muted">
          {Object.entries(COMPONENT_EXPLAIN).map(([key, explanation]) => (
            <div key={key}>
              <dt className="inline font-semibold text-foreground">{COMPONENT_LABEL[key]}: </dt>
              <dd className="inline">{explanation}</dd>
            </div>
          ))}
        </dl>
      </div>
      <div className="min-w-0">
        {rows.length > 0 ? (
          <BeforeAfterBars
            rows={rows}
            title="Rotation minutes — before vs after"
            unit="projected minutes per game"
            why="Where the deal actually changes who plays; a trade that never reaches the floor can't move the record."
          />
        ) : (
          <UnavailableNotice reason="This evaluation did not return a rotation breakdown, so the before-and-after minutes chart can't be drawn." />
        )}
        {perf.delta_wins !== undefined && (
          <p className="mt-3 text-[12px] leading-relaxed text-muted">
            Reallocating those minutes moves the projection by{" "}
            <span className="data text-foreground">
              {perf.delta_wins >= 0 ? "+" : ""}
              {perf.delta_wins.toFixed(1)}
            </span>{" "}
            wins before uncertainty is applied.
          </p>
        )}
      </div>
    </div>
  );
}

function FitTab({ teamEval }: { teamEval: TeamEvaluation }) {
  const fit = sectionOf<FitDetail>(teamEval.detail, "fit");
  if (fit.unavailable) {
    return (
      <UnavailableNotice
        reason={fit.unavailable}
        steps={
          <ButtonLink href="/team-outlook" size="sm">
            Open Team Outlook
          </ButtonLink>
        }
      />
    );
  }

  const needs = fit.needs ?? {};
  const addressed = fit.needs_addressed ?? {};
  const skills = fit.skill_delta ?? {};
  const redundancies = fit.redundancies ?? {};
  const notAddressable = fit.needs_not_addressable ?? {};
  const rankedNeeds = Object.entries(needs)
    .filter(([, severity]) => severity > 0)
    .sort((a, b) => b[1] - a[1]);

  return (
    <div className="grid gap-6 lg:grid-cols-2">
      <div className="min-w-0">
        <h4 className="title-md text-foreground">Needs this deal addresses</h4>
        <p className="mt-1 text-[12px] leading-snug text-muted">
          Only needs the model measured as real for this roster are listed. The bar is how severe
          the need is; the number is how far this deal moves it.
        </p>
        {rankedNeeds.length === 0 ? (
          <p className="mt-3 text-[13px] text-muted">
            No measurable roster need is outstanding for this team, so fit is scored on redundancy
            alone.
          </p>
        ) : (
          <ul className="mt-3 space-y-2.5">
            {rankedNeeds.map(([key, severity]) => {
              const delta = addressed[key] ?? 0;
              return (
                <li key={key}>
                  <div className="flex items-baseline justify-between gap-3">
                    <span className="min-w-0 truncate text-[13px]">{NEED_LABEL[key] ?? key}</span>
                    <span
                      className={`data shrink-0 text-[12px] ${
                        delta > 0 ? "text-legal" : delta < 0 ? "text-illegal" : "text-faint"
                      }`}
                    >
                      {delta > 0 ? "+" : ""}
                      {delta.toFixed(3)}
                    </span>
                  </div>
                  <MeterBar
                    value={severity}
                    max={Math.max(...rankedNeeds.map(([, s]) => s), 0.001)}
                    color="var(--signal)"
                    className="mt-1"
                    label={`${NEED_LABEL[key] ?? key} severity`}
                  />
                </li>
              );
            })}
          </ul>
        )}
        {Object.keys(notAddressable).length > 0 && (
          <div className="mt-3 border-t border-hairline pt-2.5">
            {Object.entries(notAddressable).map(([key, reason]) => (
              <p key={key} className="text-[11px] leading-snug text-faint">
                <span className="text-muted">{NEED_LABEL[key] ?? key}</span> is measured for
                this roster but not scored here — {reason}.
              </p>
            ))}
          </div>
        )}
      </div>
      <div className="min-w-0">
        <h4 className="title-md text-foreground">Skill balance change</h4>
        <p className="mt-1 text-[12px] leading-snug text-muted">
          Minutes-weighted skill profile arriving minus the profile leaving.
        </p>
        <ul className="mt-3 space-y-1.5">
          {Object.entries(skills)
            .sort((a, b) => Math.abs(b[1]) - Math.abs(a[1]))
            .map(([key, value]) => (
              <li key={key} className="flex items-center justify-between gap-3 text-[13px]">
                <span className="min-w-0 truncate">{SKILL_LABEL[key] ?? key.replaceAll("_", " ")}</span>
                <span
                  className={`data shrink-0 text-[12px] ${
                    value > 0 ? "text-legal" : value < 0 ? "text-illegal" : "text-faint"
                  }`}
                >
                  {value > 0 ? "+" : ""}
                  {value.toFixed(2)}
                </span>
              </li>
            ))}
        </ul>
        {Object.keys(redundancies).length > 0 && (
          <p className="mt-3 border-t border-hairline pt-2.5 text-[11px] leading-snug text-faint">
            Redundancy penalty applied to:{" "}
            {Object.entries(redundancies)
              .filter(([, v]) => v > 0)
              .map(([k, v]) => `${SKILL_LABEL[k] ?? k.replaceAll("_", " ")} (${v.toFixed(2)})`)
              .join(", ") || "none"}
            .
          </p>
        )}
      </div>
    </div>
  );
}

/**
 * Partial contract coverage in the cap tab (R2c). Payroll appears as a floor with the
 * coverage attached; the apron row states only what the known salaries already prove.
 * "Not yet proven above the tax" is not "below the tax", and this must never imply it.
 */
function PartialCapPosition({ legality }: { legality: TeamLegality }) {
  const before = legality.payroll_coverage_before;
  const after = legality.payroll_coverage_after;
  const shownBefore = payrollDisclosure(
    legality.payroll_before,
    legality.payroll_known_before,
    before,
  );
  const shownAfter = payrollDisclosure(legality.payroll_after, legality.payroll_known_after, after);
  return (
    <div className="space-y-3">
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <StatBlock size="sm" label="Payroll before" value={shownBefore.value} note={shownBefore.note} />
        <StatBlock
          size="sm"
          label="Payroll after"
          value={shownAfter.value}
          note={after ? shownAfter.note : "a traded salary is unknown"}
        />
        <StatBlock
          size="sm"
          label="Apron before"
          value={legality.apron_status_at_least_before ?? "not proven"}
          note={legality.apron_status_at_least_before ? "at least" : "known salaries clear no line"}
        />
        <StatBlock
          size="sm"
          label="Apron after"
          value={legality.apron_status_at_least_after ?? "not proven"}
          note={legality.apron_status_at_least_after ? "at least" : "known salaries clear no line"}
        />
      </div>
      <UnavailableNotice
        reason={
          <>
            {legality.payroll_coverage_note}{" "}
            Payroll is shown as a floor, so cap and apron position stay unverified — the missing
            salaries could cross any threshold.
          </>
        }
      />
    </div>
  );
}

function CapTab({ teamEval }: { teamEval: TeamEvaluation }) {
  const contract = sectionOf<{ unavailable?: string; net_surplus_cap_share?: number; method?: string }>(
    teamEval.detail,
    "contract",
  );
  const assets = sectionOf<AssetsDetail>(teamEval.detail, "assets");
  const legality = teamEval.legality;
  const known = legality.payroll_before !== null && legality.payroll_after !== null;

  return (
    <div className="space-y-4">
      {known ? (
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
          <StatBlock size="sm" label="Payroll before" value={money(legality.payroll_before)} />
          <StatBlock size="sm" label="Payroll after" value={money(legality.payroll_after)} />
          <StatBlock
            size="sm"
            label="Apron before"
            value={legality.apron_status_before ?? "—"}
          />
          <StatBlock size="sm" label="Apron after" value={legality.apron_status_after ?? "—"} />
        </div>
      ) : legality.payroll_known_before !== null ? (
        <PartialCapPosition legality={legality} />
      ) : (
        <UnavailableNotice
          reason={
            contract.unavailable ??
            "Contract data isn't imported, so payroll, apron position and contract value can't be computed for this team."
          }
          steps={
            <ButtonLink href="/salary-cap-center" size="sm" variant="secondary">
              Open the Salary-Cap Center
            </ButtonLink>
          }
        />
      )}

      {contract.net_surplus_cap_share !== undefined && (
        <p className="text-[13px] leading-relaxed text-muted">
          Net contract surplus{" "}
          <span className="data text-foreground">
            {contract.net_surplus_cap_share >= 0 ? "+" : ""}
            {(contract.net_surplus_cap_share * 100).toFixed(2)}%
          </span>{" "}
          of the cap. {contract.method}
        </p>
      )}

      <div className="rounded-lg border border-hairline bg-panel2/40 p-3.5">
        <div className="eyebrow">Draft capital &amp; flexibility</div>
        <div className="mt-2 grid grid-cols-2 gap-3 sm:grid-cols-3">
          <StatBlock size="sm" label="Picks in" value={assets.picks_in ?? 0} note="in this deal" />
          <StatBlock size="sm" label="Picks out" value={assets.picks_out ?? 0} note="in this deal" />
          <StatBlock
            size="sm"
            label="Roster spots"
            value={
              assets.roster_spots_delta !== undefined
                ? `${assets.roster_spots_delta > 0 ? "+" : ""}${assets.roster_spots_delta}`
                : "—"
            }
            note="net change"
          />
        </div>

        {(assets.picks_priced?.length ?? 0) + (assets.picks_not_priced?.length ?? 0) > 0 && (
          <ul className="mt-3 space-y-1.5 text-[12px]">
            {[...(assets.picks_priced ?? []), ...(assets.picks_not_priced ?? [])].map((p, i) => (
              <li key={`${p.pick}-${p.direction}-${i}`} className="flex flex-wrap items-baseline gap-x-2">
                <span className="text-muted">
                  {p.direction === "in" ? "→" : "←"} {p.pick}
                </span>
                <span className="data text-foreground">
                  {p.point !== null
                    ? `${p.point.toFixed(2)} (${p.low.toFixed(2)}–${p.high.toFixed(2)})`
                    : `${p.low.toFixed(2)}–${p.high.toFixed(2)}`}
                </span>
                <span className="text-faint">
                  slots {p.slot_support.min_slot}–{p.slot_support.max_slot}
                  {p.precision !== "interval" && ` · no point estimate (${p.precision})`}
                </span>
              </li>
            ))}
          </ul>
        )}

        {assets.unavailable ? (
          <p className="mt-2.5 text-[11px] leading-snug text-faint">{assets.unavailable}</p>
        ) : (
          assets.precision_note && (
            <p className="mt-2.5 text-[11px] leading-snug text-faint">{assets.precision_note}</p>
          )
        )}
        {assets.payroll_delta !== undefined && (
          <p className="mt-1 text-[11px] leading-snug text-faint">
            Payroll change{" "}
            <span className="data text-muted">
              {assets.payroll_delta >= 0 ? "+" : "−"}
              {money(Math.abs(assets.payroll_delta))}
            </span>
            . {assets.payroll_scored_note}.
          </p>
        )}
        {assets.payroll_note && (
          <p className="mt-1 text-[11px] leading-snug text-faint">{assets.payroll_note}.</p>
        )}
      </div>
    </div>
  );
}

function TimelineTab({ teamEval }: { teamEval: TeamEvaluation }) {
  const timeline = sectionOf<TimelineDetail>(teamEval.detail, "timeline");
  if (timeline.unavailable || timeline.incoming_alignment === undefined) {
    return (
      <UnavailableNotice
        reason={
          timeline.unavailable ??
          "Player ages are missing for at least one asset, so competitive-window alignment can't be scored."
        }
      />
    );
  }
  const delta = (timeline.incoming_alignment ?? 0) - (timeline.outgoing_alignment ?? 0);
  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
        <StatBlock
          size="sm"
          label="Strategy"
          value={(timeline.strategy ?? "custom").replaceAll("_", " ")}
        />
        <StatBlock
          size="sm"
          label="Arriving fit"
          value={(timeline.incoming_alignment ?? 0).toFixed(2)}
          note="0–1 · age vs window"
        />
        <StatBlock
          size="sm"
          label="Departing fit"
          value={(timeline.outgoing_alignment ?? 0).toFixed(2)}
          note="0–1 · age vs window"
        />
      </div>
      <p className="text-[13px] leading-relaxed text-muted">
        {delta > 0.02
          ? "The players arriving align better with this team's stated window than the players leaving."
          : delta < -0.02
            ? "The players leaving aligned better with this team's stated window than the players arriving."
            : "Arriving and departing players sit at roughly the same point in this team's window."}{" "}
        Alignment is a documented age-vs-strategy curve, not a projection of future production.
      </p>
    </div>
  );
}

function RiskTab({ teamEval }: { teamEval: TeamEvaluation }) {
  const risk = sectionOf<RiskDetail>(teamEval.detail, "risk");
  // `prob_positive` is the simulation's, and it is deliberately NOT the risk component:
  // it is the performance projection restated as a probability, and scoring it made
  // `risk` 0.86-correlated with `performance` (R5-1b).
  const probPositive = teamEval.uncertainty.prob_positive;
  const pct = (v: number | null | undefined) =>
    v === null || v === undefined ? "—" : `${(v * 100).toFixed(0)}%`;
  const delta = risk.availability_delta;
  return (
    <div className="grid gap-6 lg:grid-cols-2">
      <div className="min-w-0">
        <UncertaintyStrip u={teamEval.uncertainty} />
        <div className="mt-3 grid grid-cols-2 gap-3">
          <StatBlock
            size="sm"
            label="Arriving availability"
            value={pct(risk.incoming_availability ?? risk.roster_availability)}
            note={
              risk.incoming_availability === null || risk.incoming_availability === undefined
                ? `no arriving player with a games-played history — priced at this roster's ${pct(
                    risk.roster_availability,
                  )}`
                : `${risk.incoming_availability_players ?? 0} player(s), minutes-weighted`
            }
          />
          <StatBlock
            size="sm"
            label="Departing availability"
            value={pct(risk.outgoing_availability ?? risk.roster_availability)}
            note={
              risk.outgoing_availability === null || risk.outgoing_availability === undefined
                ? `no departing player with a games-played history — priced at this roster's ${pct(
                    risk.roster_availability,
                  )}`
                : `${risk.outgoing_availability_players ?? 0} player(s), minutes-weighted`
            }
          />
        </div>
        {delta !== undefined && (
          <p className="mt-2 text-[12px] leading-snug text-muted">
            The risk score is this <span className="data text-foreground">
              {delta >= 0 ? "+" : ""}
              {(delta * 100).toFixed(1)} pt
            </span>{" "}
            change in the availability of the minutes involved — nothing else.{" "}
            {delta > 0.02
              ? "This deal sheds games-missed exposure."
              : delta < -0.02
                ? "This deal takes on games-missed exposure."
                : "Exposure is roughly unchanged."}{" "}
            Availability is historical games played, not a medical prediction.
          </p>
        )}
        <p className="mt-2 text-[11px] leading-snug text-faint">
          <span className="data text-muted">{pct(probPositive)}</span> of{" "}
          {teamEval.uncertainty.n_draws.toLocaleString()} simulations produce a positive win
          impact. That is the projection&rsquo;s own uncertainty and is reported here, not scored:
          it is the performance component restated as a probability, and counting it as risk made
          the two components 0.86-correlated.
        </p>
        {risk.legality_verification && risk.legality_verification.share !== null && (
          <p className="mt-1 text-[11px] leading-snug text-faint">
            {risk.legality_verification.rules_with_a_definite_verdict} of{" "}
            {risk.legality_verification.rules_evaluated} implemented CBA checks reached a verdict
            for this team. Reported, never scored — what moves it is which contract fields the
            configured provider supplies, not the deal.
          </p>
        )}
        {teamEval.uncertainty.top_uncertainty_drivers.length > 0 && (
          <ul className="mt-3 space-y-1 text-[12px] text-muted">
            {teamEval.uncertainty.top_uncertainty_drivers.map((d) => (
              <li key={d.side} className="flex items-center justify-between gap-3">
                <span className="capitalize">{d.side} side spread</span>
                <span className="data text-foreground">±{d.spread_wins.toFixed(2)} wins</span>
              </li>
            ))}
          </ul>
        )}
      </div>
      <div className="min-w-0">
        {teamEval.sensitivity_tornado.length > 0 ? (
          <TornadoChart bars={teamEval.sensitivity_tornado} />
        ) : (
          <UnavailableNotice reason="No sensitivity range was returned for this evaluation." />
        )}
        <p className="mt-2 text-[11px] leading-snug text-faint">
          Each bar swings one priority weight by ±50%. A wide bar means the verdict depends on your
          priorities, not on the deal.
        </p>
      </div>
    </div>
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
  useEffect(() => {
    function onKey(event: KeyboardEvent) {
      if (event.key === "Escape") onClose();
    }
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [onClose]);

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
      className="fixed inset-0 z-[60] flex justify-end bg-court/70 backdrop-blur-sm"
      role="dialog"
      aria-modal="true"
      aria-label={`${player.name} details`}
      onClick={onClose}
    >
      <div
        className="scroll-thin h-full w-full max-w-sm overflow-y-auto border-l border-line bg-panel p-4"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0">
            <div className="eyebrow">Player</div>
            <h2 className="title-lg mt-1 truncate text-foreground">{player.name}</h2>
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close player details"
            className="shrink-0 rounded-md border border-transparent px-2 py-1 text-muted transition-colors hover:border-line hover:text-foreground"
          >
            <span aria-hidden>✕</span>
          </button>
        </div>
        {!data ? (
          <div className="mt-4 space-y-3">
            <Skeleton className="h-20" />
            <SkeletonRows rows={3} height="h-14" />
          </div>
        ) : (
          <div className="mt-4 space-y-3.5">
            <div className="flex items-center gap-3">
              <PlayerPhoto
                nbaPlayerId={data.player.nba_player_id}
                name={data.player.full_name}
                size={64}
                square
              />
              <div className="min-w-0">
                <div className="text-sm text-muted">
                  {data.player.position ?? "—"}
                  {data.player.current_team ? ` · ${data.player.current_team.abbreviation}` : ""}
                </div>
                {data.archetype && (
                  <div className="mt-1.5">
                    {/* Role labels reach 31 characters ("unclassified (no listed
                        height)") where the retired k-means labels topped out at 18, and
                        this Badge sits in a max-w-sm drawer, so it must be allowed to
                        wrap rather than overflow. */}
                    <Badge status="info" className="max-w-full whitespace-normal text-left">
                      {data.archetype.label}
                    </Badge>
                  </div>
                )}
              </div>
            </div>
            <div className="grid grid-cols-2 gap-2">
              <div className="rounded-lg border border-hairline bg-panel2 p-2.5">
                <StatBlock size="sm" label="Est. impact" value={tei(data.impact.tei)} note="TEI" />
              </div>
              <div className="rounded-lg border border-hairline bg-panel2 p-2.5">
                <StatBlock
                  size="sm"
                  label="Availability"
                  value={
                    data.impact.availability != null
                      ? `${(data.impact.availability * 100).toFixed(0)}%`
                      : "—"
                  }
                  note="historical"
                />
              </div>
            </div>
            <div className="rounded-lg border border-hairline bg-panel2 p-2.5">
              <div className="eyebrow text-[0.5625rem]">Contract</div>
              <p className="mt-1 text-[12px] leading-snug text-muted">
                <span className="data">—</span> · {CONTRACT_TOOLTIP}
              </p>
            </div>
            {latest?.base && (
              <div className="rounded-lg border border-hairline bg-panel2 p-2.5">
                <div className="eyebrow text-[0.5625rem]">{latest.season} per game</div>
                <div className="mt-1.5 flex flex-wrap gap-x-4 gap-y-1">
                  {(["PTS", "REB", "AST", "STL", "BLK"] as const).map((k) => (
                    <span key={k} className="whitespace-nowrap text-[12px]">
                      <span className="text-faint">{k}</span>{" "}
                      <span className="data text-foreground">
                        {latest.base?.[k]?.toFixed(1) ?? "—"}
                      </span>
                    </span>
                  ))}
                </div>
              </div>
            )}
            <ButtonLink href={`/players/${player.id}`} size="sm" className="w-full">
              Full player page →
            </ButtonLink>
            <p className="text-[11px] leading-snug text-faint">{data.impact.note}</p>
          </div>
        )}
      </div>
    </div>
  );
}
