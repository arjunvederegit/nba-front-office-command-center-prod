"use client";

/**
 * Acquisition targets — the panel that starts from a need instead of from a trade.
 *
 * It renders three things the API insists on, and would be dishonest without:
 *
 * - **the two rules, in words**. Candidates are filtered by the need and ranked by
 *   projected wins, and neither is a hidden weighting. The panel prints both.
 * - **the cost, beside the target and never folded into its rank**. A cheap target and an
 *   expensive one sit in the same order here.
 * - **the search's own accounting** — how many players were considered, how many were set
 *   aside and why, and how many trades were actually evaluated against the budget.
 */

import Link from "next/link";
import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { NEED_LABEL, money } from "@/lib/format";
import { evaluatorLink } from "@/lib/shareState";
import type { AcquisitionResponse, AcquisitionTarget } from "@/lib/types";
import { Button, Panel, SkeletonRows, UnavailableNotice } from "@/components/ui";

const REJECTION_LABEL: Record<string, string> = {
  no_balancing_package: "no package balanced the value",
  verified_illegal: "the trade failed a CBA rule",
  focal_utility: "this team did not clear neutral",
  counterparty_utility: "the other team did not clear neutral",
  projected_win_loss: "one side lost more than two projected wins",
  context_error: "the trade context could not be built",
};

function TargetRow({
  target,
  teamId,
}: {
  target: AcquisitionTarget;
  teamId: string;
}) {
  const [open, setOpen] = useState(false);
  const cost = target.acquisition_cost;
  const evaluation = target.trade_evaluation;
  // The evaluator's own share-state encoding, so the link opens the exact deal that was
  // evaluated rather than an empty builder with the two teams in it.
  const href = evaluation
    ? evaluatorLink({
        teamIds: evaluation.team_ids,
        moves: Object.fromEntries(
          evaluation.player_moves.map((m) => [m.player_id, m.to_team_id]),
        ),
        picks: [],
        name: `${target.name} to ${teamId === evaluation.team_ids[0] ? "us" : target.team.abbreviation}`,
      })
    : evaluatorLink({ teamIds: [teamId, target.team.id], moves: {}, picks: [] });
  return (
    <li className="border-t border-hairline py-2.5 first:border-t-0">
      <div className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1">
        <div className="min-w-0">
          <span className="text-[13px] font-semibold text-foreground">{target.name}</span>
          <span className="ml-1.5 text-[12px] text-muted">{target.team.abbreviation}</span>
        </div>
        <div className="flex shrink-0 items-baseline gap-3 text-[12px]">
          <span className="data text-legal">
            {target.projected_delta_wins === null
              ? "—"
              : `${target.projected_delta_wins >= 0 ? "+" : ""}${target.projected_delta_wins.toFixed(1)} wins`}
          </span>
          <span className="data text-muted">
            +{(target.need_improvement * 100).toFixed(0)} percentile pts
          </span>
        </div>
      </div>
      <p className="mt-1 text-[11px] leading-snug text-muted">{target.why[0]}</p>
      <div className="mt-1.5 flex flex-wrap items-center gap-x-3 gap-y-1 text-[11px] text-faint">
        <span>
          Costs about {cost.package_value_projected_wins.toFixed(1)} wins of value back
        </span>
        <span>·</span>
        <span>
          {cost.salary === null
            ? "salary unavailable"
            : `${money(cost.salary)} in, needs ≈ ${money(cost.minimum_outgoing_salary)} out`}
        </span>
        {cost.rank_on_own_team_by_minutes !== null && (
          <>
            <span>·</span>
            <span>
              {target.team.abbreviation}&apos;s No. {cost.rank_on_own_team_by_minutes} by minutes
            </span>
          </>
        )}
        <button
          type="button"
          onClick={() => setOpen((v) => !v)}
          className="text-signal underline"
          aria-expanded={open}
        >
          {open ? "Hide detail" : "Why and how"}
        </button>
      </div>
      {open && (
        <div className="mt-2 rounded-md border border-hairline bg-panel2 p-2.5 text-[11px] leading-snug text-muted">
          <ul className="space-y-1">
            {target.why.slice(1).map((line) => (
              <li key={line}>{line}</li>
            ))}
          </ul>
          <p className="mt-2 text-foreground">
            Suggested package:{" "}
            {target.suggested_package.length === 0
              ? "none found"
              : target.suggested_package.map((p) => p.name).join(", ")}
          </p>
          <p className="mt-0.5">{target.suggested_package_note}.</p>
          {evaluation && (
            <p className="mt-1">
              Evaluated: this team {evaluation.focal_utility.toFixed(0)}/100,{" "}
              {target.team.abbreviation} {evaluation.counterparty_utility.toFixed(0)}/100 —{" "}
              {evaluation.legality_status.replace(/_/g, " ")}.
            </p>
          )}
          <p className="mt-1 text-faint">{cost.reported_not_scored}.</p>
          <div className="mt-2">
            <Link href={href} className="text-signal underline">
              Open this deal in the Trade Evaluator
            </Link>
          </div>
        </div>
      )}
    </li>
  );
}

export function AcquisitionTargetsPanel({ teamId }: { teamId: string }) {
  const [needKey, setNeedKey] = useState<string | null>(null);
  const [sort, setSort] = useState<"impact" | "need">("impact");
  const query = useQuery({
    queryKey: ["acquisition-targets", teamId, needKey, sort],
    queryFn: () =>
      api.get<AcquisitionResponse>(
        `/teams/${teamId}/acquisition-targets?limit=6&sort=${sort}` +
          (needKey ? `&need_key=${needKey}` : ""),
      ),
  });
  const data = query.data;

  return (
    <Panel
      title="Who fixes this?"
      subtitle="Start from the need. Candidates are filtered by it and ranked by projected wins — both rules are printed below, and cost is reported beside each name, never folded into the order."
      className="min-w-0"
    >
      {query.isPending && <SkeletonRows rows={4} height="h-10" />}
      {query.error && <UnavailableNotice reason={String(query.error)} />}
      {data && !data.available && (
        <UnavailableNotice
          reason={data.unavailable_reason ?? "No targets could be produced for this team."}
        />
      )}
      {data?.available && (
        <>
          <div className="flex flex-wrap items-center gap-1.5">
            {data.diagnosis
              .filter((d) => d.severity > 0)
              .slice(0, 5)
              .map((d) => {
                const active = (data.target_need?.need_key ?? "") === d.need_key;
                return (
                  <button
                    key={d.need_key}
                    type="button"
                    disabled={!d.addressable}
                    onClick={() => setNeedKey(d.need_key)}
                    title={d.addressable ? d.explanation : (d.not_addressable_reason ?? "")}
                    className={`rounded-full border px-2.5 py-1 text-[11px] transition-colors ${
                      active
                        ? "border-signal/60 bg-signal/12 text-signal"
                        : d.addressable
                          ? "border-line text-muted hover:bg-panel2"
                          : "border-line text-faint opacity-60"
                    }`}
                  >
                    {NEED_LABEL[d.need_key] ?? d.need_key}
                    {!d.addressable && " · no skill addresses this"}
                  </button>
                );
              })}
          </div>
          <div className="mt-2 flex flex-wrap items-center gap-2 text-[11px] text-faint">
            <span>Rank by</span>
            <Button size="sm" variant={sort === "impact" ? "primary" : undefined} onClick={() => setSort("impact")}>
              Projected wins
            </Button>
            <Button size="sm" variant={sort === "need" ? "primary" : undefined} onClick={() => setSort("need")}>
              Need improvement
            </Button>
          </div>
          <p className="mt-2 text-[11px] leading-snug text-muted">
            <span className="text-foreground">Filter: </span>
            {data.filter_rule}. <span className="text-foreground">Rank: </span>
            {data.sort_rule}.
          </p>
          <ul className="mt-2">
            {data.targets.map((t) => (
              <TargetRow key={t.player_id} target={t} teamId={teamId} />
            ))}
          </ul>
          {data.targets.length === 0 && (
            <p className="mt-3 text-[13px] text-muted">
              No player both improves this need and survives a trade both front offices would
              make. The rejection counts below say where the search stopped.
            </p>
          )}
          {data.search && data.feasibility && (
            <p className="mt-3 border-t border-hairline pt-2.5 text-[11px] leading-snug text-faint">
              {data.search.players_considered} players considered ·{" "}
              {data.search.does_not_improve_the_need} do not improve this need ·{" "}
              {data.search.no_skill_measured} have the skill unmeasured ·{" "}
              {data.feasibility.trades_evaluated} trades evaluated against a budget of{" "}
              {data.feasibility.budget}. Rejected:{" "}
              {Object.entries(data.feasibility.rejected)
                .filter(([, n]) => n > 0)
                .map(([reason, n]) => `${n} because ${REJECTION_LABEL[reason] ?? reason}`)
                .join("; ") || "none"}
              .
            </p>
          )}
        </>
      )}
    </Panel>
  );
}
