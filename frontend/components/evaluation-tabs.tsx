"use client";

/**
 * The seven panels behind the evaluation's tab strip.
 *
 * Extracted from `app/trade-evaluator/page.tsx` in R7. The page was 2,964 lines and grew
 * in every release since R4; these are the part of it with the cleanest boundary — each
 * one takes a `TeamEvaluation` (and, where it needs it, one typed section of its detail
 * bag), renders, and holds no state the builder shares. The only page-local helper they
 * used was `sectionOf`, which moved to `lib/evaluationDetail.ts` because reading a typed
 * section out of the detail bag is not a rendering concern.
 *
 * Nothing here changed behaviour. It is a move, and the page imports them back under the
 * same names.
 */

import { useQuery } from "@tanstack/react-query";
import { useMemo } from "react";
import { api } from "@/lib/api";
import { sectionOf } from "@/lib/evaluationDetail";
import {
  COMPONENT_EXPLAIN,
  COMPONENT_LABEL,
  NEED_LABEL,
  SKILL_LABEL,
  money,
  payrollDisclosure,
} from "@/lib/format";
import { comparablesResponseSchema } from "@/lib/schemas";
import type {
  AssetsDetail,
  ComparablesResponse,
  FitDetail,
  PerformanceDetail,
  PickMove,
  PlayerMove,
  RiskDetail,
  RosterShapeDetail,
  TeamEvaluation,
  TeamLegality,
  TimelineDetail,
} from "@/lib/types";
import {
  BeforeAfterBars,
  ComponentBars,
  TornadoChart,
  UncertaintyStrip,
} from "@/components/charts";
import { PrecedentPanel, RosterShapePanel } from "@/components/precedent";
import { ButtonLink, MeterBar, StatBlock, UnavailableNotice } from "@/components/ui";

export function PrecedentTab({
  focalTeamId,
  teamIds,
  playerMoves,
  pickMoves,
}: {
  focalTeamId: string;
  teamIds: string[];
  playerMoves: PlayerMove[];
  pickMoves: PickMove[];
}) {
  const query = useQuery({
    queryKey: ["comparables", focalTeamId, playerMoves, pickMoves],
    queryFn: () =>
      api.post<ComparablesResponse>(
        "/trades/comparables",
        {
          team_ids: teamIds,
          focal_team_id: focalTeamId,
          player_moves: playerMoves,
          pick_moves: pickMoves,
          k: 5,
        },
        comparablesResponseSchema,
      ),
  });
  return (
    <PrecedentPanel
      data={query.data}
      loading={query.isPending}
      error={query.error ? String(query.error) : undefined}
    />
  );
}

export function ImpactTab({ teamEval, perf }: { teamEval: TeamEvaluation; perf: PerformanceDetail }) {
  const shape = sectionOf<RosterShapeDetail>(teamEval.detail, "roster_shape");
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
        <div className="mt-4">
          <RosterShapePanel shape={shape} />
        </div>
      </div>
    </div>
  );
}

export function FitTab({ teamEval }: { teamEval: TeamEvaluation }) {
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
export function PartialCapPosition({ legality }: { legality: TeamLegality }) {
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

export function CapTab({ teamEval }: { teamEval: TeamEvaluation }) {
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

export function TimelineTab({ teamEval }: { teamEval: TeamEvaluation }) {
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

export function RiskTab({ teamEval }: { teamEval: TeamEvaluation }) {
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
          {teamEval.uncertainty.n_draws.toLocaleString()}
          {" simulations produce a positive win impact. That is the projection’s own "}
          {"uncertainty and is reported here, not scored: it is the performance component "}
          {"restated as a probability, and counting it as risk made the two components "}
          {"0.86-correlated."}
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
