"use client";

/**
 * Precedent — the completed trades a proposal resembles, and what a trade does to the
 * shape of a rotation.
 *
 * Two rules govern everything rendered here.
 *
 * **A similarity number is meaningless without its distribution.** 0.74 reads as a grade
 * until you know the middle of the corpus sits at 0.67. Every score is shown against the
 * per-dimension breakdown that produced it, and the panel says how large the searched
 * corpus is.
 *
 * **Resemblance is not consequence.** Nothing in the retrieval reads what happened after
 * these trades, and the panel says so in its own text rather than in a tooltip.
 */

import type {
  ComparablePick,
  ComparableSide,
  ComparablesResponse,
  RoleShareRow,
  RosterShapeDetail,
} from "@/lib/types";
import { MeterBar, Panel, UnavailableNotice } from "@/components/ui";

const DIMENSION_LABEL: Record<string, string> = {
  player_value: "On-court value",
  draft_capital: "Draft capital",
  structure: "Deal structure",
  age_profile: "Age profile",
  team_context: "Team situation",
  timing: "Timing",
};

function picks(list: ComparablePick[]): string {
  if (list.length === 0) return "—";
  return list
    .map((p) => `${p.draft_year} R${p.round_number}${p.conveyance === "unconditional" ? "" : `*`}`)
    .join(", ");
}

function names(list: { name: string; tei: number | null }[]): string {
  if (list.length === 0) return "—";
  return list
    .map((p) => (p.tei === null ? p.name : `${p.name} (${p.tei > 0 ? "+" : ""}${p.tei.toFixed(1)})`))
    .join(", ");
}

function ComparableCard({ side }: { side: ComparableSide }) {
  const dimensions = Object.entries(side.dimension_similarity).sort(
    (a, b) => b[1].weight - a[1].weight,
  );
  return (
    <li className="rounded-lg border border-hairline p-3">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h4 className="title-sm text-foreground">
          {side.team_abbreviation}
          <span className="text-muted"> · {side.transaction_date ?? side.season}</span>
        </h4>
        <span className="data text-[13px] text-foreground">
          {(side.similarity * 100).toFixed(0)}% similar
        </span>
      </div>
      <p className="mt-1.5 text-[12px] leading-snug text-muted">{side.source_text}</p>
      <dl className="mt-2 grid grid-cols-2 gap-x-4 gap-y-1 text-[12px]">
        <div>
          <dt className="text-faint">In</dt>
          <dd className="text-foreground">{names(side.incoming)}</dd>
          <dd className="text-muted">picks: {picks(side.picks_in)}</dd>
        </div>
        <div>
          <dt className="text-faint">Out</dt>
          <dd className="text-foreground">{names(side.outgoing)}</dd>
          <dd className="text-muted">picks: {picks(side.picks_out)}</dd>
        </div>
      </dl>
      <ul className="mt-2.5 space-y-1">
        {dimensions.map(([key, value]) => (
          <li key={key} className="flex items-center gap-2">
            <span className="w-28 shrink-0 text-[11px] text-muted">
              {DIMENSION_LABEL[key] ?? key}
            </span>
            <MeterBar
              value={value.similarity}
              max={1}
              color="var(--signal)"
              className="flex-1"
              label={`${DIMENSION_LABEL[key] ?? key} similarity`}
            />
            <span className="data w-9 shrink-0 text-right text-[11px] text-muted">
              {(value.similarity * 100).toFixed(0)}%
            </span>
          </li>
        ))}
      </ul>
      {side.why.length > 0 && (
        <p className="mt-2 text-[11px] leading-snug text-faint">{side.why[0]}</p>
      )}
      {side.dimensions_unavailable.length > 0 && (
        <p className="mt-1 text-[11px] leading-snug text-unavail">
          Not compared:{" "}
          {side.dimensions_unavailable.map((d) => DIMENSION_LABEL[d] ?? d).join(", ")} — one of the
          two sides does not state it.
        </p>
      )}
      {(side.reported_not_scored.cash_involved ||
        side.reported_not_scored.trade_exception_received) && (
        <p className="mt-1 text-[11px] leading-snug text-faint">
          Reported, never scored:{" "}
          {[
            side.reported_not_scored.cash_involved ? "cash changed hands" : null,
            side.reported_not_scored.trade_exception_received
              ? "this team received a trade exception"
              : null,
          ]
            .filter(Boolean)
            .join("; ")}
          .
        </p>
      )}
    </li>
  );
}

export function PrecedentPanel({
  data,
  loading,
  error,
}: {
  data?: ComparablesResponse;
  loading?: boolean;
  error?: string;
}) {
  if (loading) {
    return <p className="text-[13px] text-muted">Searching completed trades…</p>;
  }
  if (error) {
    return <UnavailableNotice reason={error} />;
  }
  if (!data) {
    return (
      <p className="text-[13px] text-muted">
        Evaluate a trade to search the completed-trade record for precedents.
      </p>
    );
  }
  if (!data.available) {
    return (
      <UnavailableNotice
        reason={
          <>
            {data.unavailable_reason}
            {data.unmodelled_players && data.unmodelled_players.length > 0 && (
              <> Players without modelled production: {data.unmodelled_players.join(", ")}.</>
            )}
          </>
        }
      />
    );
  }
  const coverage = data.coverage;
  return (
    <div className="grid gap-4 lg:grid-cols-[minmax(0,1.6fr)_minmax(0,1fr)]">
      <div className="min-w-0">
        <h4 className="title-md text-foreground">Completed trades this one resembles</h4>
        <p className="mt-1 text-[12px] leading-snug text-muted">
          {/* `trades_rankable`, not `trades_ingested`: 565 trades are ingested and 535 can
              be ranked, and naming the larger number here would claim coverage the
              retrieval does not have. The gap is stated below rather than absorbed. */}
          Ranked over {coverage.sides_rankable.toLocaleString()} team-sides of{" "}
          {coverage.trades_rankable.toLocaleString()} completed trades. A side is one
          team&apos;s view of one trade, because sending a star for picks and receiving one are
          different decisions — at most one side of any trade appears here.
        </p>
        <ul className="mt-3 space-y-3">
          {data.comparables.map((side) => (
            <ComparableCard key={side.key} side={side} />
          ))}
        </ul>
        {data.comparables.length === 0 && (
          <p className="mt-3 text-[13px] text-muted">
            No completed trade in the corpus is close enough to show.
          </p>
        )}
      </div>
      <aside className="min-w-0 space-y-3 text-[12px] leading-snug text-muted">
        <div className="rounded-lg border border-hairline p-3">
          <h5 className="title-sm text-foreground">Resemblance is not consequence</h5>
          <p className="mt-1">
            Nothing here reads what happened after these trades. A historical deal that worked is
            not an argument that this one will.
          </p>
        </div>
        {data.not_scored && (
          <div className="rounded-lg border border-hairline p-3">
            <h5 className="title-sm text-foreground">Not part of the similarity</h5>
            <ul className="mt-1 space-y-1.5">
              {data.not_scored.map((entry) => (
                <li key={entry.field}>
                  <span className="text-foreground">{entry.field}</span> — {entry.reason}.
                </li>
              ))}
            </ul>
          </div>
        )}
        <div className="rounded-lg border border-hairline p-3">
          <h5 className="title-sm text-foreground">Coverage</h5>
          <p className="mt-1">{coverage.note}</p>
          <p className="mt-1.5">
            Seasons ingested {coverage.seasons_ingested[0]} –{" "}
            {coverage.seasons_ingested[coverage.seasons_ingested.length - 1]};{" "}
            {coverage.sides_blocked_by_unmodelled_players} sides withheld because a player in them
            has no modelled production
            {coverage.trades_ingested > coverage.trades_rankable && (
              <>
                ; {(coverage.trades_ingested - coverage.trades_rankable).toLocaleString()} of{" "}
                {coverage.trades_ingested.toLocaleString()} ingested trades cannot be ranked at all
              </>
            )}
            .
          </p>
          {/* The rule that decided every feature season above. Silent when it is the
              ingested calendar, because that is the case with nothing to disclose. */}
          {coverage.calendar_backed === false && (
            <p className="mt-1.5 text-conditional">
              No season calendar has been ingested, so each trade&apos;s feature season was decided
              from its calendar month. That mis-describes draft-night, preseason and
              November-2020 trades. Run <code>make sync-season-calendar</code>.
            </p>
          )}
        </div>
      </aside>
    </div>
  );
}

/* ------------------------------------------------------------- rotation shape */

function roleNote(row: RoleShareRow): string {
  if (row.congested) return "above the league 90th percentile";
  if (row.lost) return "no longer a rotation role";
  return "";
}

export function RosterShapePanel({ shape }: { shape: RosterShapeDetail }) {
  if (shape.unavailable) {
    return <UnavailableNotice reason={shape.unavailable} />;
  }
  const rows = (shape.roles ?? [])
    .filter((r) => Math.abs(r.delta) >= 2 || r.congested || r.lost)
    .sort((a, b) => Math.abs(b.delta) - Math.abs(a.delta));
  return (
    <Panel
      title="Rotation consequences"
      subtitle="Minutes by player role, of 240. Roster composition — not lineup data."
    >
      {rows.length === 0 ? (
        <p className="text-[13px] text-muted">
          No role&apos;s minutes move by more than two of 240. The rotation keeps its shape.
        </p>
      ) : (
        <table className="w-full text-[12px]">
          <thead>
            <tr className="text-left text-faint">
              <th className="pb-1 font-normal">Role</th>
              <th className="pb-1 text-right font-normal">Before</th>
              <th className="pb-1 text-right font-normal">After</th>
              <th className="pb-1 text-right font-normal">League median</th>
              <th className="pb-1 font-normal">Note</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.role} className="border-t border-hairline">
                <td className="py-1.5 text-foreground">{row.role}</td>
                <td className="data py-1.5 text-right text-muted">
                  {row.minutes_before.toFixed(0)}
                </td>
                <td
                  className={`data py-1.5 text-right ${
                    row.congested ? "text-conditional" : row.lost ? "text-illegal" : "text-foreground"
                  }`}
                >
                  {row.minutes_after.toFixed(0)}
                </td>
                <td className="data py-1.5 text-right text-faint">
                  {row.league_median === null ? "—" : row.league_median.toFixed(0)}
                </td>
                <td className="py-1.5 text-muted">{roleNote(row)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      {shape.lineup_fit && !shape.lineup_fit.available && (
        <p className="mt-3 border-t border-hairline pt-2.5 text-[11px] leading-snug text-unavail">
          <span className="font-semibold text-foreground">Lineup-aware fit is unavailable. </span>
          {shape.lineup_fit.reason}.
        </p>
      )}
    </Panel>
  );
}
