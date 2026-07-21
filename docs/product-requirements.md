# Product requirements

## Problem

Trade decisions are multi-objective decisions made under cap law, uncertainty, and
time pressure. Existing public tools answer only "does the salary math work?" and
hide their assumptions. Analysts need a workspace that structures the whole
question — basketball value, legality, finances, timeline, risk — and is honest
about what it doesn't know.

## Users and jobs to be done

| User | Jobs |
| --- | --- |
| Basketball-ops analyst | Diagnose roster needs · construct 2–3-team structures · check legality against current cap parameters · compare alternatives · export a defensible memo |
| GM / executive | Read a one-page recommendation with tradeoffs, cap consequences, upside/downside, and confidence |
| Portfolio reviewer | Understand the problem framing, architecture, models, and decisions; run it locally |

## Functional requirements (implemented)

1. **Scenario setup** — focal team, 7 strategy presets, horizon (1/2/3/5y), risk
   tolerance, untouchables, preferred-outgoing, six importance weights (normalized);
   persisted.
2. **Roster diagnosis** — roster with TEI/archetype/availability, standings, team
   statistical profile, percentile-based needs with explanations, payroll status
   (honest unavailable state), freshness lines.
3. **Trade construction** — 2 and 3-team trades; drag-and-drop plus accessible
   click-to-move; player search via rostered lists; hypothetical picks (labeled);
   live backend validation; named alternatives; clone-and-modify.
4. **Evaluation** — per-team legality (4 states), salary movement, payroll/apron
   movement where data permits, six component scores with drivers, Δwins with Monte
   Carlo bands, tornado sensitivity, confidence level.
5. **Comparison** — 2–5 alternatives: table, Pareto dominance flags, first-place
   share under sampled weights, rank volatility.
6. **Executive report** — deterministic 9-section memo (Markdown + printable HTML).
7. **Candidate generation** — constrained beam search with both-sides utility
   floors; labeled as model exploration.
8. **Data health** — provider status, per-table freshness, sync runs, quality
   issues, model versions.

## Data requirements

- Primary basketball data exclusively from NBA.com via `nba_api` with stored
  provenance; no synthetic production data anywhere.
- Contracts/injuries/verified picks are optional provider-backed extensions; their
  absence produces explicit unavailable states, never estimates.
- Cap parameters from version-controlled YAML verified against official releases.

## Non-goals

Predicting actual trades · claiming knowledge of front-office preferences · an
opaque "AI GM" · betting integration · full CBA certification · medical/injury
prediction · replacing professional cap tools.

## Success metrics

| Metric | Target / current |
| --- | --- |
| Time to evaluate a constructed trade | < 5 s (current: ~1–3 s local) |
| Trades with fully available legality data | tracked; 0% without a contract provider — by design, surfaced honestly |
| Data freshness | roster/standings < 24 h when scheduler runs; badge past TTL |
| Provider sync success rate | visible per-run on /data-health |
| Impact-model validation | beat persistence baseline on held-out transition (0.637 vs 0.717 MAE ✓) |
| Recommendation robustness | first-place share reported for every comparison |
| User can identify top tradeoffs | every evaluation lists ranked drivers |

## Launch stages

1. **Local analyst build (done)** — full pipeline + UI on a local snapshot.
2. **Hosted demo** — deploy with a dated snapshot, scheduler on, admin sync gated.
3. **Contract-enabled** — user-supplied lawful contract data unlocks salary rules
   end to end.
4. **Depth** — lineup-level features, three-team search, pick valuation.

## Risks

NBA.com endpoint drift (mitigated: schema contracts, classified errors, snapshot
retention) · terms-of-use limits on redistribution (mitigated: no data committed;
runtime fetch only) · model overtrust (mitigated: uncertainty + sensitivity are
first-class, limitations documented) · cap-rule drift year to year (mitigated:
versioned YAML + rule-level source references).
