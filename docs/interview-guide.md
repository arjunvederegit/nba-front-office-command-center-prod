# Interview guide

How to discuss TradeLab in strategy/product/quant interviews — with the honest
answers to the hard follow-ups.

## The ambiguous problem and how it was structured

Start from the real question: *"should we make this trade?"* is under-specified —
right answer depends on objectives (win now vs optionality vs cost), constraints
(CBA, roster), and risk appetite. The structuring move: (1) make the strategic frame
explicit and persistent (scenario: strategy, horizon, weights, untouchables);
(2) decompose value into six measurable components; (3) separate *legality* (rules,
verifiable) from *desirability* (weighted, subjective); (4) treat missing data as a
first-class state; (5) test conclusions for robustness before calling them
recommendations.

## Stakeholders

Analyst (constructs and defends), executive (consumes the memo), counterparty teams
(modeled explicitly — every team gets its own evaluation and the generator enforces
a counterparty utility floor), and the reviewer/regulator analogue: the honesty
standard exists because a tool that overstates certainty is worse than no tool.

## Architecture in 60 seconds

Next.js UI → FastAPI → services → (CBA engine | analytics) → SQLAlchemy/Postgres;
one hardened integration boundary for NBA.com (`nba_api`) carrying rate limits,
retries, circuit breakers, caching, schema contracts; idempotent ingestion with
provenance on every row; models versioned with validation metrics; Docker compose +
CI. Key property: routers never see raw provider payloads, and the frontend never
decides legality.

## Provider limitations and what they forced

`nba_api` has no contracts, injuries, or pick ownership. Rather than fake them:
ContractProvider interface with an honest `None` default, availability from games
played, hypothetical-labeled picks, and the four-state legality standard. Also a war
story: stats.nba.com hangs on slightly-wrong headers and cdn.nba.com edge-blocks
some networks — hence classified errors, default-header discipline, and the
circuit breaker (found empirically during this build).

## The math, defended

- **Why components + weights, not one model?** No ground truth for "good trade";
  objectives are incommensurable; weights make the subjectivity explicit and
  sensitivity-testable.
- **Why is TEI credible?** Not because it's fancy — because its validation is
  honest: time-aware split, persistence baseline, held-out MAE (0.637 vs 0.717),
  residual-based bands, and a model card stating what it can't see (tracking,
  matchup, defense).
- **Why calibrate wins/net-rating?** A hard-coded 2.7 is folklore; fitting on the
  ingested 90 team-seasons (2.24, R² 0.95) makes the constant inspectable and the
  residual usable in the Monte Carlo.
- **What would falsify the approach?** If rank-stability said most comparisons flip
  under small weight changes, the composite would be decoration — that's exactly why
  sensitivity is a first-class output.

## CBA implementation

Explain the band structure (200%+$250K / +$9.096M / 125%+$250K, scaled with the cap;
100%+$250K at the aprons; no aggregation above the second apron) and the deliberate
exclusions (S&T, TPEs, cash, BYC, hard caps) with the fail-safe: excluded ⇒
unavailable ⇒ at best conditionally valid. Know the honesty rule cold: *partial
validation never yields "legal".*

## Tradeoffs I'd defend

SQLite/in-proc dev defaults vs Postgres/Redis prod (ADR-8) · APScheduler vs Celery
(ADR-9) · heuristic contract value vs silence (chose labeled heuristic, excluded
without data) · beam-search generator vs "AI GM" (bounded, explainable, labeled).

## Failure modes I'd watch in production

Silent NBA.com schema drift (mitigated: contracts + classified errors, but a new
column rename still needs a fixture update) · stale-model/fresh-data skew (data
version stamps mitigate) · users reading TEI as truth (bands + model card + UI
copy) · offseason roster churn making "current season" semantics ambiguous
(documented CURRENT_SEASON/CAP_LEAGUE_YEAR split).

## With a team and a quarter, next

(1) lineup/on-off ingestion → TEI v2 with a defensible defensive signal;
(2) contract-provider adapters + fitted market-salary model; (3) three-team
generator with pick valuation; (4) evaluation telemetry → measure the success
metrics in the PRD instead of defining them.
