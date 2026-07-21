# Demo script (~6 minutes)

Prep: `make dev` with an ingested + trained database (`make sync-data && make train
&& make score`). Have `/` open.

## 1 · Frame the problem (30 s)

“Trade decisions are multi-objective decisions under cap law and uncertainty.
TradeLab structures the whole question instead of collapsing it to one number.”
Point at the landing badges: **data synced timestamp, season, contracts: not
configured** — “the product tells you what it doesn't know before you ask.”

## 2 · Decision room (60 s)

Open **Decision Room** → pick a team (e.g. Boston). The needs panel fills from
transparent percentile rules — hover a bar to show the plain-English explanation
and the provenance line (*Source: NBA.com via nba_api · Updated …*). Set strategy
to **Contend now**, drag a weight slider, mark one player untouchable, **Save
scenario**.

## 3 · Trade builder (90 s)

Open **Trade Builder** (from the scenario link). Add a second team. Drag a player
across — or use the accessible →ABC buttons — and watch the **backend-authoritative
legality panel** re-validate live: rule-by-rule results with pass / warning /
**unavailable** states. Call out the honesty: “no contract provider ⇒ salary
matching reports *unavailable*, so the overall status is *conditionally valid* —
it will never claim ‘legal’ from partial data.” Optionally add a hypothetical 2028
first (labeled). Name it and **Save & open full evaluation**.

## 4 · Evaluation (90 s)

On the trade page: composite utility with **component bars** (note any excluded
component and the renormalization note), **Monte Carlo wins strip** (median,
p10–p90, P(positive)), **tornado** (“which weight assumptions move the answer”),
and the persisted rule audit trail. Switch the team-perspective tab: “every team in
the deal gets its own evaluation — a trade that's great for you and terrible for
them is flagged by design in the generator.”

## 5 · Compare + report (60 s)

Clone the trade, tweak it, save. Open **Compare**, select both, compare: table with
Pareto frontier flags, and **rank stability** — “under 500 sampled weight vectors,
alternative A ranks first 94% of the time; that's what a robust recommendation looks
like.” Click **Report (print)** for the deterministic 9-section executive memo —
recommendation, rationale, impact, financials, risks, assumptions, alternatives,
questions, and data-freshness/limitations.

## 6 · Data health (30 s)

Open **Data Health**: per-table freshness, sync-run history, quality issues, active
model versions with real validation metrics. Close: “everything you saw is
reproducible — `make sync-data && make train` — and every number traces to a
timestamped NBA.com retrieval.”
