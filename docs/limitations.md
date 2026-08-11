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

- **A player the model has never scored is excluded, not averaged.** 43 of 530
  rostered players (8.1 %) have no impact estimate. They are left out of the
  projection and named in the response, and confidence drops to low when one is in
  the deal. They still count against roster limits. Before R1-4 they arrived at
  `tei = 0.0`, which is the **63rd percentile** of rostered players — a silent
  default more favourable than the −0.293 league mean suggests.
- **Roster fit needs players on both sides.** It compares the arriving package with
  the departing one, so a deal with nothing arriving (or nothing leaving) has no
  comparison to make and the component is withheld rather than scored against an
  invented median player. R5 introduces a measured replacement baseline.
- **TEI is box-score-based.** No tracking, matchup, or lineup on/off data; defense
  is structurally under-measured. Validated against one forward transition (three
  ingested seasons) — MAE beats persistence, but bands are approximations that
  understate tail risk (role changes, injuries, aging outliers).
- **The wins conversion is a cross-sectional fit** (same-season net rating → wins)
  applied to hypothetical roster changes; it assumes context stability.
- **Rotation reallocation is a model of coach behavior**, proportional to
  established minutes with caps — real rotations will differ; users can override
  minutes.
- **Roles are descriptive labels, not positions.** They come from a deterministic
  size-first rule chain over league percentiles (R4-3), not from clustering, so the same
  profile always yields the same label. Gating on size first means a tall high-assist
  player is named a big: Kevin Durant is a "playmaking big". **49 of 632 scored players
  (7.75 %) have no listed height** and are labelled `unclassified (no listed height)`
  rather than given a role from an imputed number.
- **No player skill claims to measure point-of-attack defence, on purpose.** A composite
  was built in R4-2 and withdrawn: on its pre-registered class — high-usage, high-assist,
  sub-6'8" players with real minutes — it scored **0.630 mean with 75 % above the median**
  against the steals proxy's 0.611 / 70 %, i.e. **worse than the thing it replaced**. A
  steals-led measure necessarily rates ball-dominant guards highly, because gambling into a
  passing lane appears in a box score and staying in front of a ball handler does not. The
  team-side need is still measured and shown, with the reason nothing is claimed about it.
  Measuring it needs matchup and tracking data this repository does not have.
- **`team_defense` is not a validated measure of defensive ability.** It is a construct:
  every term is a defensive act (blocks, steals, defensive rebounds, fouls as a cost, and
  points allowed on court). It is more stable than the steals proxy it replaced
  (year-over-year 0.838 vs 0.669) and imports less team quality (0.99 vs 1.51 of the decile
  gap), but every validation target available here derives from on-court `DEF_RATING`, so
  every available test is circular to some degree. Two specific consequences worth knowing:
  the composite is **big-biased** — blocks and defensive rebounding carry 0.58 of the weight
  — and its defensive-rebound term **overlaps the separate `rebounding` skill** at r = 0.58.
- **Three-point accuracy is shrunk, so extremes are pulled toward the league mean.** 37 % of
  player-seasons have under 50 attempts, so an unshrunk percentage ranks small-sample
  non-shooters at both extremes. The shrunk figure is deliberately conservative for
  low-volume shooters, and is **withheld entirely** for the 22 window players with no
  attempt record rather than defaulted to the league average.
- **Contract value (when enabled) is a documented heuristic**, not a fitted market
  model, until historical salary data exists.
- **The candidate generator is hidden and experimental** (R1-8). It has no UI entry
  point. Measured, it searches only about **14 % of counterparties** — it exhausts a
  400-evaluation budget after roughly six teams — and applies no salary matching, so it
  will propose packages that could never be executed. `POST /trades/generate` still
  responds, and its `coverage` block states exactly which teams were and were not
  searched. Its utility scores were never evidence that a real front office would accept
  a deal, and with that coverage they are not evidence of anything league-wide either.
  R5 rebuilds the search salary-matched and deterministic.

## What the product refuses to answer

- **An illegal trade gets no decision score.** When any participating team's verdict is
  `verified_illegal` the composite and every component are withheld and the failing
  rules are shown instead. Scoring a deal that cannot be executed invites comparing it
  against deals that can. The comparison board lists such deals but never ranks them.
- **"Nothing could be scored" is not zero.** With no scorable component the composite is
  `null`, not 0.0 — on a 0–100 scale a zero reads as a catastrophic verdict.
- **A deal in which nothing moves has no probability.** `prob_positive` is `null`, not
  0 %, when no players move.
- **Zeroing every weight yields no score**, rather than silently restoring a uniform
  prior over components the user switched off.

## CBA coverage

A documented subset (see [cba-rule-coverage.md](cba-rule-coverage.md)): no
sign-and-trades, trade exceptions, cash, BYC/poison-pill, or hard-cap triggers;
trade salary equals contract salary (no incentive/guarantee adjustments); roster
counts can't distinguish two-ways without contract data (handled with widened
honest bounds). **TradeLab is not an official cap-management product.**

## Engineering

- Dev-mode cache is in-process (single instance); Redis semantics only in
  compose/production.
- Backend coverage is **72 %** overall, enforced by a `--cov-fail-under` floor in CI
  — core domain logic (CBA rules, analytics) is the tested surface; network-touching
  ingestion paths are exercised by probe scripts and classified-error tests rather
  than live CI calls. (`ingestion/jobs.py` remains at 0 %; R5 addresses it.)
- E2E tests run in CI against a **dedicated database** seeded with a synthetic demo
  league (`make e2e`), never NBA.com and never a developer's ingested data.
