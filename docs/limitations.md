# Limitations

Candid scope statement — these are design boundaries, surfaced in the product
itself, not fine print.

## Data

- **No contract provider is bundled.** Payroll, tax/apron status, salary matching,
  and contract value are unavailable until the operator supplies lawful contract
  data; the app says so everywhere it matters and never estimates a salary.
- **No injury feed.** Availability is historical games played — not health status,
  not a medical prediction.
- **No verified draft-pick ownership.** Picks in trades are labeled hypotheticals;
  Stepien compliance is never certified.
- **Live game data is disabled by default** (offseason at build time; cdn.nba.com is
  also edge-blocked from some networks, which the app reports as a classified
  provider error rather than hiding).
- NBA.com may change or throttle endpoints without notice; the client fails to
  classified errors and retains the last valid snapshot with stale badges.

## Modeling

- **TEI is box-score-based.** No tracking, matchup, or lineup on/off data; defense
  is structurally under-measured. Validated against one forward transition (three
  ingested seasons) — MAE beats persistence, but bands are approximations that
  understate tail risk (role changes, injuries, aging outliers).
- **The wins conversion is a cross-sectional fit** (same-season net rating → wins)
  applied to hypothetical roster changes; it assumes context stability.
- **Rotation reallocation is a model of coach behavior**, proportional to
  established minutes with caps — real rotations will differ; users can override
  minutes.
- **Archetype clustering is descriptive** (silhouette 0.156); labels are
  conveniences, not positions.
- **Contract value (when enabled) is a documented heuristic**, not a fitted market
  model, until historical salary data exists.
- The candidate generator explores under constraints; its utility scores are not
  evidence that any real front office would accept a deal.

## CBA coverage

A documented subset (see [cba-rule-coverage.md](cba-rule-coverage.md)): no
sign-and-trades, trade exceptions, cash, BYC/poison-pill, or hard-cap triggers;
trade salary equals contract salary (no incentive/guarantee adjustments); roster
counts can't distinguish two-ways without contract data (handled with widened
honest bounds). **TradeLab is not an official cap-management product.**

## Engineering

- Dev-mode cache is in-process (single instance); Redis semantics only in
  compose/production.
- Backend coverage is 65% overall — core domain logic (CBA rules, analytics) is the
  tested surface; network-touching ingestion paths are exercised by probe scripts
  and classified-error tests rather than live CI calls.
- E2E tests require a locally ingested database; CI runs unit/integration tests
  against fixtures only (never NBA.com).
