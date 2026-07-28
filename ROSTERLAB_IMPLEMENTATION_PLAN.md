# RosterLab — Implementation Plan

**Plan date:** 2026-07-28 · **Baseline commit:** `f16dedc` (main, clean tree)
**Input:** [`ROSTERLAB_PRODUCT_TECHNICAL_AUDIT.md`](ROSTERLAB_PRODUCT_TECHNICAL_AUDIT.md)
**Prior planning:** [`docs/rosterlab-enhancement-plan.md`](docs/rosterlab-enhancement-plan.md) documents the
*completed* TradeLab → RosterLab transformation. It is history, not backlog, and it is mislabeled as a forward
plan — R1 corrects that label. This document is the forward plan.

---

## 0. How to read this plan

The audit is accurate. Every quantitative claim re-checked against the live database and the source at `f16dedc`
reproduced exactly. **Nothing in it was refuted.**

But verification went further than confirming it, and three of its headline recommendations do not survive contact
with measurement:

- **P0-2 cannot deliver its stated outcome.** With full contract coverage simulated, `overall_status` stays
  `conditionally_valid` and the UI renders the identical *"Incomplete check — data missing"* badge. It also makes
  one rule actively less honest.
- **P0-3 cannot be fitted on the metric it names.** Minutes-weighted ridge TEI explains **R² = 0.004** of team net
  rating (t = 0.59). The transparent index the project rejected explains **R² = 0.624** on the same panel
  (t = 9.80). You cannot calibrate a metric that carries no signal.
- **P0-7's acceptance criteria are gameable.** An exhaustive weight search found that **48 % of defensible weight
  vectors** satisfy *"Daniels and Green in the top defensive quartile"* — including ones that put 30–40 % weight on
  **offensive** rebound rate inside a defense score. A criterion half of random weightings pass is a curve fit to
  two names, not a validation.

The audit is therefore used here as strong evidence, not as a checklist. §1.3 lists every point of departure with
its measurement.

Work is organised as **releases**, not weeks. A release is a branch, a PR, and a set of commits that leaves the
product defensible. Gates block; they do not become debt.

Two invariants govern every change:

> **I1 — No number appears on screen that the system cannot defend.** A value is measured, or fitted and labelled
> with its fit quality, or absent with a stated reason. There is no fourth category.
>
> **I2 — A default is never rendered as a measurement.** Where the code substitutes a fallback, the response
> carries the substitution and the UI shows it.

---

## 1. Verification against the current repository

### 1.1 Repository state

`HEAD` is `f16dedcbdc99e0e365b04aa271712c2019b06dbd`, clean tree. **The repository is at exactly the audited
commit.** The only untracked file is the audit. Nothing has drifted.

Three environment facts that change remedies:

- `backend/tradelab.db` is **gitignored** and was never tracked (no `*.db` in `git log --all --diff-filter=A`), and
  `backend/Dockerfile` does not `COPY` it. **Nothing is shipped.** The test rows live only in the local dev DB.
- `make setup` **does** create `.env` (`Makefile:19`, `@test -f .env || cp .env.example .env`). The audit's claim
  here is false. The real defects are that `.env.example` omits `CAP_LEAGUE_YEAR`, `SYNC_ROSTERS_EVERY_HOURS` and
  `SYNC_STATS_EVERY_HOURS`, and that `docker compose up` **cannot boot on a clean clone** because both the backend
  and worker services declare `env_file: .env`, which is gitignored.
- **A scheduler already exists.** `worker.py` is a complete APScheduler wired into `docker-compose` as its own
  service with 6 h / 24 h intervals and env overrides. The audit's "no scheduler" would have someone rebuild it.
  The true gap is that the *local dev* path has no `make worker` target.

Commit convention is conventional commits (`feat:`, `fix:`, `refactor:`, `chore:`, `docs:`, `test+docs:`).

### 1.2 Confirmed first-hand

| Audit claim | Measured | |
| --- | --- | --- |
| 43 rostered players have no TEI | 43 (8.1 % of 530) | ✅ |
| TEI mean −0.293, min −3.29, max 4.26, n = 512 | identical | ✅ |
| One distinct band width, 6.311 | 1 distinct, 6.310578, min = max | ✅ |
| ~25 players below `REPLACEMENT_TEI = −2.0` | 23 / 512 (4.5th pct) | ✅ |
| `team_needs` 279 rows, 135 severity 0 | identical | ✅ |
| Duplicate `model_versions` strings | `v202607210204` × 3 per model | ✅ |
| `team_projection` slope 2.235 / R² 0.9527 / n = 90 | identical, in-sample | ✅ |
| Ridge coefs `z_PIE −0.086`, `z_NET_RATING −0.030`, `AGE −0.0051` | identical | ✅ |
| Ridge MAE 0.6374 vs index 0.6454, selected on validation, no test set | identical | ✅ |
| `contracts`/`contract_years`/`draft_picks`/`injuries`/`transactions` = 0 | identical | ✅ |
| `perimeter_defense = pct("stl_per_min")`, used for both defense needs | `archetypes.py`, `needs.py:159-160` | ✅ |
| `"ball_security": "creation"` | `needs.py:165` | ✅ |
| Composite never consults legality | no `overall_status` ref in `evaluation.py` | ✅ |
| `_assets = 50 + 8·Δpicks − 2·Δspots` | `evaluation.py:339,424` | ✅ |
| Freshness from `MAX(finished_at)` across all jobs | `data_health.py:80,130` | ✅ |
| Test fixtures: `E2E scenario` ×2, `BOS — Contend now` ×3, 50 comparison sets | identical | ✅ |
| `zod`/`react-hook-form`/`@hookform/resolvers` zero imports | grep confirms | ✅ |
| Team Outlook Strengths/Needs fallback | `team-outlook/[teamId]/page.tsx:435` | ✅ |

Two audit numbers are slightly off and should be corrected rather than repeated: **open** data-quality issues are
**562, not 842** (842 is the total row count; 280 are resolved duplicates), and backend coverage measured with
`--cov=app` is **68 %, not 64 %**. The per-module coverage table underneath is exact.

### 1.3 Where this plan departs from the audit

Each item below is measured, not argued.

---

#### C1 — W1's named fix site is dead code

`projection.py:92 team_tei_to_net_rating_delta` has **zero callers**. `evaluation.py:235` inlines its body. A patch
that edits the function is a runtime no-op.

Corroborating: `projection.py:17` defines `PLAYERS_ON_COURT = 5.0` and **nothing in the repository references it**.
The author wrote the constant for exactly the factor the audit says is missing, then never applied it.

#### C2 — The headline number and its interval come from different models

`_performance` derives `delta_net` from a full 240-minute rotation reallocation, **normalised** to a mean.
`uncertainty.simulate_delta_wins` sums `minutes_share × effective` over traded players only, **unnormalised** — the
shares sum to **1.69–1.79**, i.e. ~175 % of a team. Availability is also **double-discounted**: once into
`effective_tei` in the allocator and again in the draw. `REPLACEMENT_TEI = −2.0` is defined twice
(`projection.py:73`, `uncertainty.py:35`), unsynchronised.

#### C3 — The ×5 is not a fix to apply, and 5 is empirically wrong

Dimensionally the audit is right *conditional on a premise it refutes in the same document*. Empirically the
question is settled: the fitted coefficient is **b = 14.98 (SE 1.53)** — five sits **6.5 standard errors below it**.
Applying a hardcoded ×5 *and* a fitted slope yields an effective **74.9×**, a 5.0× overstatement that pins nearly
every trade at a clamp. **Fit the coefficient; never ship a bare 5×.**

#### C4 — The calibration cannot run on the metric or the tables the audit names

`player_impact_estimates`, `rosters` and `player_team_history` are **all 2025-26 only**. There is zero historical
roster data and zero historical TEI. The regression is executable only by reconstructing team membership from
`player_season_stats.team_id` (populated 572/572, 569/569, 573/573) and re-deriving per-season TEI. True usable
n = **90 in levels, 60 in change-on-change**.

And the metric matters more than the tables:

| Regressor | Levels (n=90) | Change-on-change (n=60) |
| --- | --- | --- |
| **Ridge TEI (production)** | slope 3.15, SE 5.39, t = 0.59, **R² = 0.004** | slope 2.01, t = 0.42, **R² = 0.003** |
| **Baseline index (rejected)** | slope 17.20, SE 1.06, t = 16.27, R² = 0.750 | **slope 14.98, SE 1.53, t = 9.80, R² = 0.624** |

**P0-8 must precede P0-3.** Fitting on ridge TEI yields a coefficient indistinguishable from zero, collapsing every
projected-wins delta — and it would be misdiagnosed as a bug in the calibration rather than in the metric. This is
the single most important structural change to the audit's roadmap.

Use the **change-on-change** specification as the production coefficient. The levels R² = 0.750 is
reflection-contaminated: minutes-weighted `z(PIE)` alone reaches 0.844 on the same panel, and the index puts 0.14
weight on `z_PIE`. Publishing 0.750 as validation repeats the §7.3 error the audit flags elsewhere.

#### C5 — The ridge is a volume metric, and the only signal in the projection is availability

Player-level correlations (n = 1714): ridge TEI vs `z_USG_PCT` **0.716**, vs `z_MIN` **0.632**, vs `z_NET_RATING`
**0.100**. Combined with negative coefficients on its own target components, TEI is closest to *"who shoots a lot
and plays a lot, minus how efficient he actually was."*

Worse: regressing team net rating on the code's own `team_tei_per_minute` gives R² = 0.282 **with** the
availability discount and R² = 0.015 (slope **−4.97**) **without** it. The projection's apparent validity comes
entirely from *healthy teams win more*. The impact model contributes nothing.

There is also a **train/serve skew**: the ridge is fit on within-season z-scores of full-league rows and served on
z-scores recomputed over a synthetic `"window"` pseudo-season built from recency-averaged features over a filtered
≥200-minute population (`impact.py:205-207`).

#### C6 — TEI's target is next-season; its use is present-tense

`build_target` is *next-season* `0.6·z(PIE) + 0.4·z(NET_RATING)`; TEI is consumed as a *current* value and would be
calibrated against *contemporaneous* net rating. Resolve explicitly: define the production index as a
**descriptive current-value metric** and leave projection to the age curve.

#### C7 — The defensive fix is cheap, but not for the reason first assumed — and there is a trap

`DEF_RATING` and `E_DEF_RATING` are ingested at **100 % coverage across all three seasons**, and appear in
`features.py` `ADVANCED_COLS`/`ESTIMATED_COLS`. Team `DEF_RATING` exists for all **90** team-seasons. `FG3_PCT` is
in the stored `base` JSON at 1714/1714. So the data genuinely exists and no new provider surface is required.

**But `player_skill_vector` never sees any of it.** It receives the recency-weighted frame, whose columns are
exactly `MODEL_FEATURES` plus nine metadata fields — verified as: `AGE, AST_PCT, DREB_PCT, GP, MIN, NET_RATING,
OREB_PCT, PIE, TM_TOV_PCT, TS_PCT, USG_PCT, blk_per_min, fg3a_rate, fta_rate, height_inches, pts_per75,
stl_per_min`. `DEF_RATING`, `FG3_PCT`, `tov_per_min` and `AST_TO` are **absent**.

**The trap:** `archetypes.pct()` returns **0.5 on a missing column** before ever touching the league series. A
skill defined on an absent column silently becomes exactly 0.5 for all 632 players — no error, no warning, no test
failure. The UI would show the need as addressed while the skill contributed precisely nothing. This was verified
empirically. Any new skill must add its column to `MODEL_FEATURES` **and** be covered by a
no-silent-constant assertion.

Also: raw `DEF_RATING` is **65.1 % team-season fixed effects**. Adopting it unadjusted re-introduces the exact
reflection problem that made ridge TEI worthless, newly labelled "measured defense". It must be team-demeaned.

#### C8 — BBRef cannot reach `verified_legal`; the `file` CSV provider can

Measured with full contract coverage simulated: `overall_status` stays **`conditionally_valid`**, because
`restrictions.py:25-37` emits `RECENTLY_SIGNED = unavailable` for every outgoing player once a provider is
configured but supplies no `signed_date`, and `context.py:180-181` caps there. `format.ts:37` maps that to the
**same badge shown today**. The audit's headline outcome — *"trades move from Incomplete check to real verdicts"* —
is unreachable via BBRef at any coverage level.

Rule activation is **5 of 9, not 9 of 9**: `SALARY_DATA_AVAILABLE`, `SALARY_MATCHING`, `SECOND_APRON_AGGREGATION`,
`MINIMUM_TEAM_SALARY`, `ROSTER_SIZE` gain substantive verdicts; `RECENTLY_SIGNED` (unavailable), `NO_TRADE_CLAUSE`
(silent), `TWO_WAY_EXCLUSION` (silent), `STEPIEN_FUTURE_FIRSTS` (unavailable) stay dark.

`file_provider.py` accepts `nba_player_id` (**exact identity**), `signed_date`, `no_trade_clause`, `contract_type`
(two-way), `player_option`, `team_option`, `guaranteed`, `source_name`, `source_date` — precisely the three fields
that keep the badge pinned. **A hand-curated CSV covering one or two teams unlocks `verified_legal` for those
teams, which BBRef cannot do at any coverage level.**

#### C9 — P0-2 as written *regresses* the product's core claim

`bbref_provider.py:186` hardcodes `contract_type="standard"` for every row. `roster.py:24-27` gates `types_known`
on `all(p.contract_type is not None) and contract_provider_configured`. Importing therefore flips **all 30 teams**
from `warning`/`medium` to **`pass`/`high` confidence** on falsified type data. A 14-man roster of 11 standard +
3 two-way (illegal) would report `pass` at high confidence.

Two-way salaries compound it **in the permissive direction**: `context.py:100-113` excludes only
`contract_type == "two-way"`, so a two-way salary inflates `outgoing_salary` and therefore `maximum_incoming` — the
engine approves trades it should reject.

**A post-import run showing (pass, high) on ROSTER_SIZE is a failed acceptance, not a success.**

#### C10 — The payroll gate is all-or-nothing, and the seasons don't line up

`_team_payroll` returns `None` unless **every** rostered player has a known salary — correct, and its docstring
says why. But rosters are `season='2025-26'` while `builder.py:88-101` looks up
`ContractYear.season == cap_league_year == '2026-27'`. Every 2025-26 rostered player whose deal expired scores as
unknown. Measured sensitivity on the live 530-row roster:

| Roster players missing a `2026-27` salary | Teams with a payroll |
| --- | --- |
| 1 % | 26 / 30 |
| 2 % | 21 / 30 |
| 5 % | 10 / 30 |
| 10 % | 4 / 30 |
| 20 % | **0 / 30** |

An offseason BBRef snapshot plausibly misses 25–40 % (expired contracts) → **zero teams with payroll**, while the
job reports a high BBRef-side match rate the whole time, because the metric that matters is not computed anywhere.

#### C11 — The N+1 is a problem *today*, not a latent one

Measured on the live DB with `contracts` at **0 rows**: `/trades/generate` issues **21,112 queries in 2.55 s**.
With contracts loaded it becomes **47,158 queries / 5.17 s** on local SQLite; on the `docker-compose` Postgres path
that is 7–14 s of pure round-trip latency. `load_cap_params` was called **1,197 times for one immutable row** in a
single request. Batch-loading alone takes it to **2,412 queries / 0.88 s** *with no contract data at all*.

This inverts the sequencing: the batch fix is a **standalone, net-positive release that ships before any import**,
not a P1 follow-up.

#### C12 — Audit recommendations that are wrong and must not be implemented

| Audit item | Why it is wrong |
| --- | --- |
| **§7.4** — replace the 15 % slope sigma with the fitted `residual_std = 2.894` | Category error. 2.894 is the *prediction* residual in wins for a team-season; the *parameter* uncertainty of the slope is **SE = 0.0531**. The hardcoded 0.3353 is already **6.3× too wide**; 2.894 would be ~55× too wide. This would make the tool substantially worse. |
| **§7.3** — the in-sample R² invalidates the wins model | Mislabelling is real; the severity is not. LOO cross-validation on the same 90 rows gives **R² = 0.9505 vs 0.9527 in-sample**, RMSE 2.962 vs 2.894. Two parameters on 90 points is not overfitting. This is the **best-calibrated component in the pipeline**. Fix the label, not the model. |
| **§7.1** — `AGE` unstandardised inside L2 | Mechanics stated backwards (a larger-scale feature is *under*-penalised), and the magnitude is negligible: −0.28 TEI points across the entire 19–41 range on a 7.5-point scale. The real finding is the opposite — **TEI is effectively age-blind**. |
| **§7.1** — `.fillna(0.0)` on z-scores | Latent, not active. All 1714 advanced rows have **zero nulls** in every z-source column. Response is a coverage check at train time, not a rewrite. |
| **§7.1** — `Ridge(random_state=)` no-op, `alpha` untuned | Both true, both zero-impact. Listing them beside W1 inflates the defect count and invites spending effort on `RidgeCV`. |
| **Engineering #10** — rate limiter holds the lock across `sleep()` | This is the **correct** implementation of a global minimum-interval pacer. Releasing first makes every waiting thread compute an identical wait and fire simultaneously — the thundering herd the class exists to prevent. |
| **Engineering #17** — `ADMIN_TOKEN` | Not a finding. `deps.py:8-13` fails closed with 403 before any comparison, and `test_api.py:239-241` already regression-tests it. OpenAPI visibility is discovery, not access. **Strike it.** |
| **P1-1** — fold `risk` into `performance` | **Backwards.** Collinearity is real (corr 0.83) but the prescription deletes the wrong term: `risk` carries sd **15.29**, `performance` sd **1.27**. Risk is 12× the signal. Folding it leaves `timeline` — a nine-valued step function on age — as the dominant driver. |
| **P1-1** — "no component clips at 100" | Solves a problem that does not occur. Across 400 simulated realistic trades, `performance`, `timeline`, `assets` and `risk` clipped **zero** times. The `risk` clip is mathematically dead. Only `fit` (×120) plausibly clips. |
| **P0-4(c)** — cap `_assets` roster-spot credit at ±2 | A no-op for every real trade: measured `assets` over 400 realistic trades ∈ {48, 50, 52}. Harmless; do not count it as an improvement. |
| **P0-4** — acceptance "gutting a roster scores < 20" | **Cannot be met by P0-4's own recommendations.** Implemented as written, measured **50.1–55.0** across 8 real teams, because `risk` (79–93) is untouched. |
| **P0-5** — validate roster membership "in the Pydantic request model" | Architecturally impossible: a `field_validator` has no DB session, and `trades.py:141-145` reconstructs moves from stored `trade_assets` without touching a Pydantic model. Must live in `build_trade_context`. |
| **P0-10** — purge the "shipped" DB | Nothing is shipped (gitignored, never tracked, not in the Dockerfile). The content finding is right; the remedy changes entirely. |
| **§13** — delete `zod` | `lib/api.ts:30` is a bare unchecked cast with **no runtime validation of any API response**. The choice is *use* zod or delete it — and R3/R5 change response shapes, which is exactly when an unchecked cast bites. |
| **QA-11** — move `EFF` to `_TOTAL_FIELDS` | Unstated side effect: `_TOTAL_FIELDS` uses `_required_float`, `_RATE_FIELDS` uses `_optional_float`. Moving it makes `EFF` mandatory and starts rejecting rows with a blank value. Needs a third category. |
| **QA-9** — remove the `slice(0,4)` fallback | Incomplete: the only emptiness guard above it is `sortedNeeds.length === 0`, so for ATL and CLE you would render a bare `<h4>Needs</h4>` over an empty `<ul>`. |
| **§9 #9** — the `-0.0` fix | A negative-zero guard fixes nothing: in JS `-0 >= 0` is true, so literal `-0` already renders `+0.0`. All 27 real cases are small negatives (Draymond Green −0.0173) that round to zero while taking sign from the *unrounded* value. **Round first, then derive the sign.** |
| **§6.1** — "4 checks / 2 named" → dedupe | Per-team duplication is **meaningful**: `trade_rule_results` carries `team_id` and each rule is evaluated per participating team. Reporting "2 checks" for a 5-team trade where all five are blocked destroys real information. |
| **§6.2** — make `NO_TRADE_CLAUSE` block | Setting status `fail` contradicts the rule's own design note (*"consent is a real-world outcome"*) and would report real star trades as `verified_illegal`. The right change is a warning-aware status. |
| **§5.3** — `games` has no consumer | `ingestion/quality.py:133-134` reads `Game` for the `future_dates` check. The substantive point stands; "no consumer" invites deleting the model and breaking quality checks. |
| **§5.3** — season/league-year skew is a defect | `config/__init__.py:36-38` carries an explicit, correct rationale: a July-2026 trade is governed by the 2026-27 cap even though 2025-26 is the last completed stats season. **Unifying them would be actively wrong.** The real issue is the undocumented env vars. |
| **§8** — the market-value anchor is a live error | Currently **inert**: `contracts` = 0 → `_contract_value` returns `None` on every trade. It becomes live in R2, which is when to fix it. |

#### C13 — Real defects the audit missed

Beyond C1–C12, verification surfaced these. Each is assigned to a release below.

**Scoring and honesty**
- `fit.py:38` `delta = skills_in.get(k, 0.5) - skills_out.get(k, 0.5)` treats an **empty side as a 50th-percentile
  player**. Trading everyone away for nothing scores as if you acquired a median NBA rotation player in every
  skill — the **third** contributor to the 72.85 headline that W5 does not name.
- `sensitivity.py:26-27` `composite_utility` returns **0.0, not `None`**, when every component is unavailable. On a
  0–100 scale that reads as catastrophic, contradicting the module's own docstring. `test_analytics.py:52` pins the
  wrong behaviour.
- `normalize_weights` (`sensitivity.py:15-17`) **silently re-enables zeroed sliders**: weights summing to ≤ 0
  return a uniform distribution with no notice.
- Driver contributions **do not reconcile with the composite**: `evaluation.py:457` uses pre-renormalization
  weights while `composite_utility` uses renormalized ones. Measured: utility − 50 = 7.06 vs summed drivers 4.94.
- The 43 unmodelled players also receive a **full-confidence uncertainty band** (`TEI_SIGMA_DEFAULT = 1.5`),
  so the Monte Carlo expresses the same confidence about a player with zero data as about a 36-mpg star.
- `tei = 0.0` is the **63rd percentile** of rostered players (306 of 487 have TEI < 0) — the silent default is far
  more favourable than the −0.293 mean suggests, and it directly contradicts
  `docs/model-card-player-impact.md:50-51`.
- **The same player has two different ages depending on trade side**: outgoing cards use `rosters.age`, incoming
  cards use `birth_date` arithmetic. Max discrepancy 1.07 years; 9–14 players land in a different age bucket.
- `?format=` is unvalidated (`trades.py:266`) and the row is persisted **before** the branch, so `?format=pdf`
  returns markdown while writing a record claiming PDF.

**Freshness and data**
- **Timezone bug on the exact path P0-1 fixes**: `last_successful_sync` serialises **naive** while
  `tables[*].last_retrieved_at` serialises **tz-aware**, so the browser parses them on different clocks.
- P0-1's "reuse the per-source `last_retrieved`" is **provider-contaminated**:
  `tables['player_season_stats'].last_retrieved_at` is the CSV import, not the NBA.com sync — still wrong by ~25 h.
  It needs a `source_provider='nba_api'` filter, which is a loop restructure, not a reuse.
- `data_quality_issues` **grows unbounded**: resolve-and-recreate, not a stable backlog. 280 rows were resolved and
  280 identical rows re-detected **four seconds later**. At N runs the table holds 280 × N.
- Open-issue count is **unknowable from the API** (`.limit(50)` with no total; 562 open, 50 renderable).
- `FreshnessBadge` (`ui.tsx:314-327`) is the one correct per-entity staleness contract in the codebase and is
  **dead code** — zero app usages.
- Superseded `player_impact_estimates` are **never garbage-collected** (1536 rows = 512 × 3 versions); every
  `make train && make score` adds 512 orphans.
- `model_versions` has **no unique constraint** and nothing prevents two simultaneously-active rows per model.
- Empty `contracts` renders as **"derived"** rather than "empty" on Data Health, because the `stale === null` check
  precedes the `rows === 0` check.

**CBA**
- **Band math is discontinuous at the active league year.** `context.py:54-58` scales the three TPE anchors by
  `cap_ratio` but leaves `allowance = 250_000` unscaled. At 2026-27 max-incoming **jumps ±$16,673** at the band
  edges — sending out $0.02 more salary *reduces* allowed intake by $16,673. The audit checked the anchors, not the
  scaling.
- **Four rules emit no `rule_result` row at all** (`MINIMUM_TEAM_SALARY`, `RECENTLY_SIGNED`, `NO_TRADE_CLAUSE`,
  `TWO_WAY_EXCLUSION`), so `rule_results` silently shrinks from 9 rule types to 5 and the UI cannot render
  "not checked".
- `NO_TRADE_CLAUSE` has **no `unavailable` path** — it tests truthiness of a `bool | None`, so it cannot
  distinguish "no NTC" from "unknown". A real clause is a silent false negative in any BBRef import.
- `SALARY_DATA_AVAILABLE` shows a green **pass on picks-only trades with zero contract data**, because the
  missing-list is empty when no players move.
- `contract_provider_configured` is **true with zero data** — setting the env var with no file changes behaviour at
  five call sites.
- `guaranteed` is a **contract-level total** written into a per-season column and served as per-season.
- **Name matching will mis-bind**: `jobs.py:330` builds `{full_name.lower(): p}` over 5,121 players, no
  normalization, last-writer-wins. 38 duplicate lowercase names; `Brandon Williams` exists as both an active and a
  historical row — a coin flip decides which gets the contract, and the losing team's payroll is `None` forever.
- `source_date` is the **file mtime**, not the page's as-of date — re-saving the file makes the snapshot claim to
  be from today. The Data Health contracts card is binary fresh/unavailable, so an eight-month-old snapshot reports
  "fresh".
- `ContractRecord.team_abbreviation` is parsed and **never read**, so payroll = 2025-26 roster × 2026-27 salaries
  with no cross-check.

**Basketball**
- **`fit.py` aggregates per *need*, not per *skill***, so identical percentiles are counted multiple times:
  `perimeter_defense` **2×**, `shooting` **2×**, `creation` up to **3×**, while rim protection, rebounding, size
  and scoring count once. This silently reweights the entire fit model and is invisible in the explanation dict.
  Affects 30 of 112 active team-skill pairs.
- `needs.py:94-98` `_percentile` includes the team being scored, so the league leader caps at 96.7.
- `projection.py:57-66`'s cap-redistribution loop is **unreachable**: proportional allocation across 16–18 players
  puts the top player at ~25 minutes, well under `DEFAULT_MAX_MINUTES = 36`. ~10 lines of dead logic creating a
  false impression that star minutes are modelled.
- **Inconsistent rotation definitions**: `_fit` uses the top 9 by minutes; `_performance` allocates across the
  entire roster. The same roster is 9 players for redundancy and 18 for impact.
- `availability.py` hardcodes 82 games and applies it to an in-progress season; 2023-24 shows a max
  `games_played` of 84, and `clip(0,1)` hides both anomalies.
- The audit's `timeline_alignment` bucket widths are wrong — they are **3 and 4 years, never 5** — and the
  Tatum-28/Dončić-27 = 50.0 example only reproduces under `contend`. Under the **default** strategy
  (`custom` → retool) they score 0.7 vs 1.0, giving **20.0**. The defect is the hard boundary, not the function.
- Framing 135 severity-0 `team_needs` rows as a defect is wrong: **69 are deliberately consumed as the Strengths
  panel**. Only 66 are truly inert.

**Frontend**
- **`trade-evaluator/page.tsx:1408` hardcodes the salary and years values as JSX literals** with no data binding.
  **Importing contract data will not populate them.** This becomes invisible precisely when someone declares the
  contract work complete.
- `[:12]` is not a top-12 but an **arbitrary 12**: `detail` is built in input order and `_roster_cards` has no
  `ORDER BY`, so ordering is whatever SQLite returns.
- **Two different confidence semantics for the same deal**: the Trade Evaluator passes the backend's real
  confidence to `fanVerdict`; Strategy Lab synthesizes it from whether any component is missing.
- The favourite-team store **cannot sync across tabs** (no `storage` listener) and is read non-reactively in the
  Trade Evaluator. `salary-cap-center` falls back to `teams[0]` (alphabetical → Atlanta) and never consults it —
  the concrete cause of the audit's "CHI → ATL" observation.
- The competitive-window label is far more fragile than one threshold table: **19 of 30 teams change label**
  depending only on whether the cohort is top-8-by-TEI or the full roster.
- Player Explorer's percentile shading is computed over a population including **one-game samples** (39 of 573
  players have GP ≤ 5).
- `scripts/visual_qa.mjs` **can never fail** — it prints `PROBLEMS (n)` and contains no `process.exit`. If wired
  into CI as a gate, that gate is vacuous.
- `String(error)` leaks an `Error:` prefix into user copy; React Query `retry: 1` **doubles latency on 404s**;
  three incompatible local types exist for the `archetype` field.

**Engineering / CI**
- **Three CI checks end in `|| true`** (`alembic check`, `pip-audit`, `npm audit`) and can never fail the build.
  The `alembic check` one is dangerous: R2 will produce model/migration drift that CI detects and discards.
- **No `--cov-fail-under`** — coverage can slide during P0 work with no signal.
- **Playwright is never run in CI.** The end-to-end flow the audit reproduced QA-1…QA-13 against is unguarded.
- The `docker` job builds both images and **never runs them**.
- `ingestion/jobs.py` is **222/222 statements at 0 %** — the pipeline writing the `DataSyncRun` rows behind the
  freshness bug is completely untested.
- `score.py:46` is a **second, unreported N+1** (lazy `RosterEntry.player`, up to 530 extra SELECTs).
- `evaluation.py:397,404` do **function-local imports of the private `_player_salary`** inside the hot path
  (~800 executions per generate request).
- `main.py:63` reads `_request_log[client_ip]` **before** the asset exemption, so asset traffic still creates
  permanent dict keys — the exemption does not prevent the growth it appears to.
- `deps.py:14` uses a **non-constant-time token comparison** (one-line `hmac.compare_digest` fix).
- `core/cache.py` swallows all Redis exceptions and falls through to a per-process cache, so under multi-worker
  compose **the same trade can score differently on different workers**.
- Engineering #3's O(n²) attribution points at the wrong hotspot: `player_skill_vector` is
  **0.43 ms/call at n=500 and 0.60 ms at n=32,000** — effectively flat. It is 0.345 s of the 1.18 s;
  `recency_weighted_features` is **0.796 s**.
- W8/QA-10 is **understated**: 4 of 29 counterparties are reached (**13.8 %**), not ~21 %.

**Documentation**
- The product is **still named TradeLab in 10 of 17 docs** after the rebrand.
- `docs/demo-script.md` is **entirely dead** — it walks routes renamed twice.
- `docs/rosterlab-enhancement-plan.md` is stale and **mislabeled as a forward plan**.
- No document discloses that the dev DB contains test data, though `CONTRIBUTING.md` rule 1 requires fixtures to
  live only under `backend/tests`.

### 1.4 Protected surface

Unchanged unless a line item below says otherwise; reject PRs that touch these incidentally:

`integrations/nba_api/*` (**including the rate limiter's lock discipline — see C12**) · `ProvenanceMixin` ·
`cba/context.py:overall_status` four-state logic · the `unavailable`-never-guess rule contract ·
`sensitivity.composite_utility` component-dropping and renormalization · identity-resolution strictness ·
`stats_csv.py` totals/per-game separation · the `{error: {code, message, request_id}}` contract · the
`wins ~ net_rating` model (**the best-calibrated component in the pipeline — LOO R² = 0.9505**) ·
`worker.py`'s APScheduler · the user-downloads-the-snapshot boundary · designed empty states · accessibility.

---

## 2. Plan shape

### 2.1 Principles

1. **Credibility before capability.**
2. **Separate correctness from modelling.** A change that fixes wrong behaviour without moving a modelled number
   ships early. A change that moves every number ships with its own validation evidence. Never the same commit.
3. **Prefer activation to construction** — but verify the activation actually activates something (C8).
4. **Delete before rewriting; hide before deleting.**
5. **Tests land before fixes**, `@pytest.mark.xfail(strict=True)` where they encode current wrong behaviour, so
   "the fix worked" is distinguishable from "the number changed" and an accidental early fix is loud.
6. **No acceptance criterion that can be satisfied by tuning** (C7).

### 2.2 Release map

```
R0  Test scaffolding + CI teeth        (no production code)
      │
      ├──► R1  Correctness & honesty            ── no model retrain, no new data
      │         │
      ├──► R2a  Performance & instrumentation   ── no contract data; net-positive alone
      │         └──► R2b  Contract import + the rule fixes that MUST ship with it
      │                    └──► R2c  Disclosed-coverage payroll
      │
      └──► R3  Impact units & calibration       ── depends on R1
                 └──► R4  Basketball methodology
                        └──► R5  Decision engine
                               └──► R6  Differentiation ──► R7  Polish
```

**Critical path:** R0 → R1 → R3 → R4 → R5. **R2a ships regardless of whether contract data ever arrives** and makes
the product 2.9× faster today. R2b is gated on a human artifact and on R2a.

**File overlaps requiring a stated merge order:**

| File | Items | Order |
| --- | --- | --- |
| `services/evaluation.py` | R1-3, R1-4, R1-5 | sequential within R1 |
| `api/schemas.py` | R1-2, R1-3 | R1-3 first |
| `cba/builder.py` | R1-2 (roster check), R2a (batch load) | **R1 merges first**; different functions |
| `services/data_health.py` | R1-1, R2b (contracts card) | **R1 merges first** |
| `analytics/projection.py` | R1-5 (detail sort), R3-3 (denominator) | R1 first |

### 2.3 Opus vs Sonnet

> **Opus where a wrong answer would be silently plausible. Sonnet where correctness is verifiable by a test that
> can be written before the change.**

| Release | Work | Model |
| --- | --- | --- |
| R0 | Test scaffolding, fixtures, CI gates | **Sonnet** |
| R1 | Validation, chart sort, labels, dead deps, e2e isolation | **Sonnet** |
| R1 | Unavailable-state semantics; what replaces a suppressed score | **Opus** |
| R2a | Batch loading, memoization, coverage instrumentation | **Sonnet** |
| R2b | Identity join, season semantics, which rules stay dark, the ROSTER_SIZE regression | **Opus** |
| R2b | CSV loader wiring, badges, tests | **Sonnet** |
| R2c | Disclosed-coverage model | **Opus** |
| **R3** | **All of it** | **Opus** |
| R4 | Defensive metric design, sign conventions, threshold rules, archetype branch ordering | **Opus** |
| R4 | Feature plumbing, re-score, rendering, tests | **Sonnet** |
| R5 | Component redesign, pick curve, generator constraints | **Opus** |
| R5 | N+1, caching, coverage, scheduler | **Sonnet** |
| R6 | Similarity metric | **Opus** |
| R6 | Retrieval plumbing, UI, export | **Sonnet** |
| R7 | Everything | **Sonnet** |

R3 and R4 must also have their **acceptance evidence reviewed by a separate Opus pass** from the implementation.
The failure mode there is a model that passes its own tests because the tests encode the same mistake — and for
R4 that failure mode is *measured* at 48 % (C7).

---

## 3. R0 — Test scaffolding and CI teeth `[Sonnet]`

**Ships before any production change.** No behaviour changes.

- **R0-1** New `backend/tests/unit/test_evaluation_sanity.py` plus a shared `seeded_league` fixture in
  `conftest.py` — a ~15-player roster **with `PlayerImpactEstimate` and `TeamNeed` rows**. The existing `seeded`
  fixture has rosters but no impact estimates, so every card currently gets `tei = 0.0` and no sanity property is
  testable against it. Mark each currently-failing property `@pytest.mark.xfail(strict=True, reason="QA-N")`.
- **R0-2** Remove `|| true` from `alembic check` in `ci.yml:31`. R2 will produce migration drift that CI currently
  detects and discards. Leave the two `audit` steps advisory but log them explicitly.
- **R0-3** Add `--cov-fail-under=68` (the measured value, not the audit's 64).
- **R0-4** Run Playwright in CI. The flow QA-1…QA-13 were reproduced against is currently unguarded.
- **R0-5** Make `scripts/visual_qa.mjs` exit non-zero on problems; add `/players/[playerId]` and an invalid-ID
  route to its `ROUTES` list.
- **R0-6** Align `make test-backend` with CI's `--cov=app`; fix the `help` target's `grep` so `e2e` appears.

**Commit:** `test+ci: add sanity scaffolding, enforce coverage, and give CI gates teeth`

---

## 4. R1 — Correctness and honesty

**Goal:** every displayed number is correct or explicitly unavailable. **No modelled number changes.**
**Branch:** `fix/r1-correctness-honesty`

### R1-1 · Freshness attribution `[Sonnet]`

Derive `last_success` from `MAX(source_retrieved_at)` **filtered to `source_provider='nba_api'`** — per C13, the
per-source value the audit suggested reusing is contaminated by the CSV import and would still be wrong by ~25 h.
Fix the **naive/aware serialisation mismatch** on the same path. Fix the Data Health ordering so empty `contracts`
renders "empty", not "derived". Add `open_quality_issue_counts` and a total alongside the `.limit(50)` list.

One backend site corrects all six frontend consumers; **no frontend change required**.

*Accept:* `/data-health` reports **stale**; nav reads "Data aging"; homepage shows Jul 21. Invariant test:
`nba_fresh` is never true while any NBA table is stale, and an `index_assets` run never moves NBA freshness.
**Commit:** `fix(data-health): derive NBA freshness from nba_api retrieval times, not job completions`

### R1-2 · Trade construction validation `[Sonnet]`

Roster-membership and duplicate-move checks in **`build_trade_context`** (C12 — a Pydantic validator has no session
and would leave the three already-persisted trades unvalidated). Extract the existing `Literal` at `schemas.py:67`
into a `Strategy` alias; apply to `EvaluateRequest` and `GenerateRequest`. Make `?format=` a
`Literal["markdown","html"]` and persist the row **after** the branch.

*Accept:* each case returns 422 with a specific message; the five already-correct cases stay correct.
**Commit:** `fix(api): reject phantom, duplicate and unknown-strategy trade moves`

### R1-3 · Legality gate and empty-trade neutrality `[Opus]`

When `overall_status == "verified_illegal"`, suppress the composite and all components; render the failing rule and
its dollar figures. Distinguish `composite_utility: null` **suppressed** from `null` **low-confidence** in the
response contract. Credit what exists: `reports.py:64-65` already overrides the report verdict — the gaps are the
API field, `fanVerdict`, and Strategy Lab's client-side score.

Also: `prob_positive → None` on an empty trade; `composite_utility` returns **`None`, not 0.0**, when everything is
unavailable (`test_analytics.py:52` pins the wrong behaviour and must change); `normalize_weights` must not
silently re-enable zeroed sliders; driver contributions must use renormalized weights so they reconcile with the
composite.

**Not in this release:** flooring vacated minutes. It moves every number and belongs in R3-3. And per C12 the
audit's "< 20" criterion is unreachable without the `risk` fix, so it is stated in R3, not here.

*Accept:* the roster-giveaway returns **no decision score** and names the 12-man minimum; drivers sum to
`utility − 50`.
**Commits:** `feat(evaluation): suppress the decision score for verified-illegal trades` ·
`fix(analytics): return None rather than zero when no component can be scored`

### R1-4 · No defaults rendered as measurements `[Opus]`

Keep `tei`, `availability` and `minutes` as `None` when absent; propagate `has_unmodeled_players` and the names;
downgrade confidence. **`tei = 0.0` is the 63rd percentile of rostered players** — this is the sharpest violation in
the product. Unmodelled players must also stop receiving `TEI_SIGMA_DEFAULT = 1.5`, which currently expresses the
same confidence about a player with no data as about a star.

Sweep the rest: `pct()`'s 0.5, `fit_score`'s 0.5 for a **missing skill**, and separately `fit.py:38`'s 0.5 for an
**empty side** — the third unnamed contributor to the 72.85 headline (C13). Suppress the report's availability line
by having `_risk` return `None`.

The Opus judgment: excluding an unmodelled player from *impact* while keeping them in the *roster count* — and
saying so — rather than silently shrinking the roster. This aligns with an existing deliberate design
(`min_total_minutes = 200`), so it makes a principled exclusion visible rather than inventing policy.

*Accept:* no numeric fallback reaches a rendered value without a companion disclosure field. Grep-enforced.
**Commit:** `fix(evaluation): never substitute league-average defaults for missing player data`

### R1-5 · Rotation chart `[Sonnet]`

Sort `detail` by minutes descending before slicing; add `ORDER BY` to `_roster_cards`; always include every traded
player regardless of rank. The frontend join is correct — do not touch it.
**Commit:** `fix(evaluation): sort rotation detail and always include traded players`

### R1-6 · Team Outlook Strengths/Needs `[Sonnet]`

Replace the fallback with a **conditional render** — per C12, simply deleting it leaves ATL and CLE with an empty
`<ul>` under a bare heading.
**Commit:** `fix(team-outlook): show an explicit no-pressing-needs state instead of a severity-blind fallback`

### R1-7 · Test-data isolation `[Sonnet]`

Point Playwright at a dedicated `DATABASE_URL`; add `make seed-demo` and a one-shot `purge-fixtures`; guard test
asserting no scenario/proposal/comparison-set name matches `/(test|smoke|e2e)/i`. Also fix the upstream cause: the
Strategy Lab scenario dropdown renders only `name`, so five rows with two distinct names are indistinguishable.
**Commit:** `chore(dev): isolate the e2e database and add a demo seed command`

### R1-8 · Hide the candidate generator `[Sonnet]`

Remove the UI entry point; mark the endpoint experimental. `candidates.py` stays for the R5 rebuild.
Correct the docs: **13.8 %** of counterparties are reached, not ~21 %.
**Commit:** `chore(trades): hide the candidate generator pending a constrained rebuild`

### R1-9 · Copy, labels, hygiene `[Sonnet]`

Monotone verdict **labels** (thresholds unchanged — C12). Unify `fanVerdict` confidence semantics across the two
pages. Round-then-sign for `-0.0`. Report distinct rules **and** team-sides separately in the rule-count copy.
`notFound()` on invalid routes; drop React Query `retry` for 404s; `toString` override on `ApiError`. Share one
`archetype` type. Content-hash `model_versions` strings and add `UNIQUE(model_name, version)` behind a de-dup
migration. GC superseded `player_impact_estimates`. `hmac.compare_digest` in `deps.py`. Move the `_request_log`
write after the asset exemption. Add `CAP_LEAGUE_YEAR` / `SYNC_*_EVERY_HOURS` to `.env.example`; make
`docker-compose` bootable without `.env`. Add `make worker`.

**On `zod`:** do not delete it. `lib/api.ts:30` is an unchecked cast and R3/R5 change response shapes. Either wire
runtime validation at the API boundary or remove all three packages — decide, don't default.
**Do not** touch `ADMIN_TOKEN` or the rate limiter (C12).

Leave the dead `FreshnessBadge` in place; R2b uses it.

### R1 gate

- [ ] CI green; every xfail from R0 has flipped to pass.
- [ ] `/data-health` reports stale; nav reads "Data aging".
- [ ] Roster giveaway returns no decision score and names the 12-man minimum.
- [ ] No rendered value derives from an undisclosed default.
- [ ] **Evaluation responses for three fixed trades differ from `f16dedc` only in fields R1 deliberately changes.**
      A moved modelled number means R1 overreached; find it before merge.

---

## 5. R2 — Contracts, in three parts

The audit's "Small · Low risk · one HTML file and one env var" is wrong in three independent ways (C8, C9, C10).
Scoped honestly, the *first* part is still the best available value — and it needs no contract data at all.

### R2a · Performance and instrumentation `[Sonnet]` — ships alone, no data required

1. **Batch-load payroll.** Request-scoped resolver: memoize `load_cap_params` (**1,197 identical calls per
   request**), batch `Contract`+`ContractYear` per roster, cache payroll per `(team, season, league_year)`. Fix the
   function-local private imports at `evaluation.py:397,404` and the lazy-load N+1 at `score.py:46`.
2. **Coverage instrumentation, before any import.** `sync_contracts` must report
   `roster_players_total`, `roster_players_with_salary_for_cap_league_year`, `teams_with_complete_payroll`,
   `seasons_present_in_snapshot`, and the **roster-side** unmatched list — not the BBRef-side one, which can read
   98 % while roster coverage is 60 %.
3. **Harden the identity join** (C13): unaccent as a *fallback tier only* — the DB is internally inconsistent
   (`Bogdan Bogdanović` keeps diacritics, `Alperen Sengun` does not), so a blanket normalize breaks as many as it
   fixes — plus suffix-insensitive matching and disambiguation preferring a player with a current `RosterEntry`.
   Emit an explicit ambiguity warning; never silently pick.
4. `make import-contracts`; resolve the default `CONTRACT_DATA_FILE` against the repo root, not CWD.

*Accept:* `/trades/generate` < 3,000 queries and < 1.2 s (**baseline 21,112 / 2.55 s**), same 8 candidates. A 2-for-2
evaluate < 25 queries (baseline 60). Query-count tests pin both.
**Commits:** `perf(cba): batch-load contract salaries and memoize cap parameters` ·
`feat(ingestion): instrument contract roster coverage before import`

### R2b · Import, with the fixes that must ship alongside `[Opus design, Sonnet implementation]`

Per C8, route through the **`file` CSV provider**, not `bbref_snapshot`. Use the BBRef parser as a bootstrap:
`app.cli export-contracts-csv` runs it, resolves `nba_player_id`, and writes the documented CSV with optional
columns blank for curation. Unmatched names go to `data_quality_issues` — never fuzzy-matched.

**Four fixes that cannot ship separately, because the import makes each one live:**

- **`ROSTER_SIZE` honesty regression (C9).** Do not let `types_known` flip on hardcoded `contract_type="standard"`.
  Gate it on genuinely-known types.
- **Two-way exclusion.** Until types are real, two-way salaries inflate `outgoing_salary` and therefore
  `maximum_incoming` — the engine would approve trades it should reject.
- **Band-math discontinuity (C13).** Scale `allowance` by `cap_ratio`, or the 2026-27 band edges jump ±$16,673 and
  band 2 is non-monotonic.
- **`trade-evaluator/page.tsx:1408`.** The salary and years cells are **hardcoded JSX literals**. Importing data
  will not populate them, and the bug becomes invisible the moment someone marks the import done.

Plus: real `unavailable` paths for `NO_TRADE_CLAUSE` and the three other silent rules, so `rule_results` stops
shrinking from 9 to 5; suppress the false `SALARY_DATA_AVAILABLE` pass on picks-only trades; make
`contract_provider_configured` require a readable file; record `source_date` from the page's as-of date, not the
file mtime; wire the dead `FreshnessBadge` to it.

**Season semantics is a product decision, not a bug fix** (C10). Choose explicitly and record an ADR: keep
`cap_league_year` and accept coverage loss; or use `current_season` for payroll and `cap_league_year` only for
traded players; or fall back season-by-season with disclosure. **Do not unify the two settings** — C12.

*Accept:* `seasons_present_in_snapshot` contains `cap_league_year`, or the import **fails loudly**;
`teams_with_complete_payroll ≥ 27/30`; zero ambiguous bindings, or each named; a knowingly-illegal deal returns
`verified_illegal` with dollar figures; **`ROSTER_SIZE` stays `(warning, medium)` for the 29 teams at 17–18
players — a `(pass, high)` result is a failed acceptance**; the salary cell renders a real number.

**Do not describe this release as "activating the engine" unless a fully-covered legal 2-for-2 actually returns
`verified_legal`.** With BBRef-only data it will not.

### R2c · Disclosed-coverage payroll `[Opus]`

The all-or-nothing gate is correct but makes partial real data useless. Replace the binary with a disclosed
coverage model — payroll shown with an explicit "computed from 16 of 18 contracts; 2 unknown" — rather than
fabricating the gap. Only after R2b proves the join works.

---

## 6. R3 — Impact units and calibration `[Opus throughout]`

**Depends on:** R1. **Blocks:** R4, R5. **Branch:** `feat/r3-impact-calibration`

### R3-1 · Promote the index; retire the ridge — **first**

Four reasons, in descending order of force:

1. **The ridge has no team-level validity.** R² = 0.004 in levels, 0.003 change-on-change. The index gets 0.750 and
   0.624 on identical data. This alone is decisive and needs no calibration to act on.
2. It is a **volume metric**: corr 0.716 with usage, 0.632 with minutes, 0.100 with net rating.
3. Train/serve z-distribution mismatch (C5).
4. **The index is computable per-season; the ridge is not** — without this step R3-2 has n = 30, on a metric with
   no signal.

Remove the constant band and the false `# bootstrap` comments. **Note:** with the index forced, the band is *still*
3.1553, sourced from `ridge_residual_std` — an interval derived from a retired model. R3-4 must land in the same
release.

**Documentation blast radius is the largest of any P0 item**: seven documents carry "held-out MAE 0.637", and
`docs/methodology.md:44-64`, the model card's title, and the in-product methodology page all describe a model that
will no longer exist.

### R3-2 · Fit the conversion

Add a historical-scoring entry point — none exists (`train.py:143` hardcodes `season=current_season`;
`score_players` has no season parameter). Score the index per season, reconstruct rotations from
`player_season_stats.team_id` + `minutes`, and fit **change-on-change** (n = 60), not levels.

**Freeze the allocator first.** The fitted `b` is valid only for the exact regressor construction. R3-3's
denominator change, the replacement-level change, and the availability-discount decision each redefine it. Fitting
before they settle produces a silently wrong coefficient with no error surfaced.

Watch the **highest-probability silent failure**: a coefficient fitted on single-season-z features is **27 % too
large** applied to production window-z TEI (21.29 vs 16.71 on identical teams). Nothing in the codebase would catch
it; every number would look plausible and every projected win would be inflated by a quarter.

Apply the coefficient at **both** `evaluation.py:235` and `uncertainty.py`, or the point estimate and the band
disagree by ~14.5×. Delete `PLAYERS_ON_COURT` or demote it to a comment. Never multiply by 5.

Add to the model card the falsification note: *if TEI were already in correct additive per-player net-rating units
the fit would return ≈ 5; it returns 15, which is the quantitative statement of how far off the current scale is.*

Separately, fix the **label** on `wins ~ net_rating` (report LOO, not in-sample) but **leave the model alone** —
LOO R² = 0.9505 vs 0.9527 in-sample. It is the best-calibrated thing in the pipeline.

### R3-3 · Replacement level and the denominator — **atomic with R3-2**

Normalise by 240 and attribute the shortfall to replacement level; derive replacement empirically rather than the
hardcoded −2.0 (the **4.5th percentile**, not replacement). Remove the duplicate constant in `uncertainty.py`.

**This cannot ship after the calibration.** Applying ~14.5× on today's allocator drives the roster-gut performance
score from 56.4 to **99.8, with 96.7 % of teams clipped** — a correct calibration would ship as a dramatic visible
regression on the audit's own headline defect.

Note the audit's stated mechanism for W5 is wrong (C12): the `or 1.0` guard is dead code in the empty-roster path;
0.0 comes from `weighted = 0.0`. The real defect is normalizing by allocated minutes instead of team minutes.

### R3-4 · Per-player intervals and Monte Carlo repair

Replace the constant band with **σ² = 0.163 + 182.7/m**, estimated from 725 same-player season pairs — σ ranges
0.47–1.04 against today's constant **2.462**. Fix the Monte Carlo's unnormalised `minutes_share` (summing to
1.69–1.79) and its **double-discounted availability** (C2).

Do **not** adopt §7.4's suggested slope sigma (C12) — the slope's parameter SE is 0.0531; the existing hardcoded
value is already 6.3× too wide, and 2.894 would be ~55× too wide.

Two framing hazards to handle in the release note: narrower bands will **read as overconfidence** when they are the
opposite; and σ(minutes) estimated from season-to-season variability is the right quantity for a forward-looking
interval and the **wrong quantity to call "measurement error"** — mislabelling it repeats the W1 class of error.

### R3-5 · One definition of `delta_net`

Make the Monte Carlo draw over the same rotation reallocation the point estimate uses. A unit test must assert the
two paths agree to 1e-9 on a fixed 15-player fixture. This is the check that would have caught the whole class.

### R3 gate

- [ ] `model_versions` row `tei_to_net_rating` with slope, SE, n, per-fold slopes, LOTO OOS RMSE, and a
      regressor-construction string. Slope **t > 5** (measured 11.00).
- [ ] LOTO OOS RMSE **< 4.5** net-rating points and **< 75 %** of predict-zero on the same fold (measured 3.774 vs
      5.805 = 65 %).
- [ ] Per-fold slopes within ±15 % of pooled (measured 15.28 / 14.72 vs 14.98).
- [ ] Roster-gut performance **< 25** on all 30 rosters.
- [ ] Clamp binds on **< 5 %** of a 600-trade realistic sample and **< 10 %** of an 870-pair star-for-scrub sample.
      *Watch the tail:* realistic trades clip 2 %, star-for-scrub 17 %, 3-for-3 blockbusters **93 %** — QA will pass
      while the trades users actually build become binary.
- [ ] Performance-component sd rises from **1.27** to **> 8**.
- [ ] `COUNT(DISTINCT ROUND(tei_high - tei_low, 4)) > 400` of 512; band width monotone in minutes
      (Spearman ρ < −0.95).
- [ ] `grep` finds no literal 5 multiplying `team_tei_per_minute`.
- [ ] No doc, model card or UI string asserts "points per 100 possessions" unless the coefficient is 1.0 —
      **including `frontend/app/methodology/page.tsx:90-91`**, the most exposed surface and the one a
      markdown-only sweep would miss.

---

## 7. R4 — Basketball methodology

### R4-1 · The free fixes, which carry most of the credibility `[Opus design, Sonnet implementation]`

- **`fit.py` per-skill aggregation.** Accumulate per *skill* before applying severity. Fixing the proxies without
  this leaves `perimeter_defense` double-counted for 9 of 21 teams — most of the measurement error would survive
  the data improvement while credit was claimed.
- **`ball_security → turnover_avoidance = pct_inv(TM_TOV_PCT)`.** There is **no inversion mechanism in the skill
  path** to copy — the two that exist are team-side severity and a negative index weight, neither reusable. Add a
  named `pct_inv` helper, not a bare literal. Sign verified empirically: Hauser 0.992, Haliburton 0.911, Jokić
  0.505, Green 0.024, Payton 0.015. Confirms the bug's direction — corr(`pct(AST_PCT)`, `pct_inv(TM_TOV_PCT)`)
  = −0.18, and 8 of the top 12 by assist rate sit below median in turnover avoidance.
- **Split `defense_overall` from `point_of_attack_defense`** so two distinct needs stop sharing one number.
- **Split `shooting` into volume and shrunk accuracy.** `FG3_PCT` needs shrinkage: 37 % of player-seasons have
  under 50 total 3PA and 219 are exactly 0.000 or ≥ 1.000. Unshrunk, accuracy ranks small-sample non-shooters at
  both extremes and is *worse* than today's TS_PCT blend.
- **Add every new column to `MODEL_FEATURES`** (C7) — otherwise `pct()` returns a silent 0.5 for all 632 players.

### R4-2 · A real defensive input `[Opus]`

Team-demeaned on-court differential (`player DEF_RATING − team DEF_RATING`, shrunk by minutes) as the primary term;
event rates minor; foul rate negative. Raw `DEF_RATING` is 65.1 % team fixed effects and must never be used
unadjusted.

**Acceptance criteria — replacing the audit's, which are gameable (C7):**

- **A′ (rank correlation).** Spearman correlation between the new `team_defense` skill and actual team
  `DEF_RATING`, over minutes-weighted rosters across the 90 team-seasons, must **exceed** the steals proxy's on the
  same 90 rows. Report with a bootstrap CI.
- **A″ (decile monotonicity).** Among players with ≥ 1000 window minutes, the top decile's mean on-court
  `DEF_RATING` must be **≥ 3.0 points lower** than the bottom decile's, and that gap must exceed the steals proxy's.
- **A‴ (anti-overfit, procedural).** The weight vector is **committed and documented before any named-player check
  runs**, and no named player may be used to select weights. Named players go in a face-validity appendix that is
  never gated on.
- **B (achievable, and the strongest argument for the cheap path).** Luka Dončić's `perimeter_defense` percentile
  must fall **below 0.50**. Today he sits at **0.845** — the tool literally tells users acquiring Dončić upgrades
  their point-of-attack defense. With `DEF_RATING` at ≥ 50 % weight he drops to 0.558 on the window frame and
  0.269–0.405 on 2025-26 alone. Jokić 0.821 → 0.519; Trae Young 0.568 → 0.256.

**Honest fallback:** if team-context contamination is judged disqualifying, ship R4-1 alone and make the limitation
**louder** rather than papering over it. The proxy notes already exist in `needs.py` but render only in a hover
`title` attribute — invisible on touch, unreliable for screen readers, absent from the executive report. Promote
them to visible body copy on every surface that renders a defensive skill.

### R4-3 · Rule-based roles `[Opus]`

**Size gates must come first.** A creation-first chain — the intuitive ordering, and the one k-means effectively
uses — was measured to label **Wembanyama "secondary creator"** and produce "point-of-attack guard" at 0.9 %.
Size-first passes all seven non-degeneracy tests: every branch fires (11/11 vs k-means reaching 5 of 10), max label
15.3 % (vs 35.9 %), min 3.6 %, zero numeric suffixes (vs **249 of 632 rows, 39.4 %**), Herfindahl 0.106 (vs 0.261),
byte-identical across runs.

Do not sweep `k` or chase silhouette — at 0.156 no separated structure exists and any `k` produces mush.

### R4-4 · Age, timeline, and small corrections `[Opus]`

Continuous age curve replacing hard boundaries — the buckets are **3 and 4 years, not 4–5**, and the collapse only
reproduces under `contend`; the **default** strategy gives 20.0, not 50.0 (C13). Exclude self from
`needs._percentile`. Remove the unreachable cap-redistribution loop. Reconcile the top-9 vs whole-roster rotation
definitions.

### R4 gate

- [ ] A′, A″, A‴ and B all pass. **A‴ is procedural and must be evidenced by commit order.**
- [ ] No skill in `SKILL_KEYS` is constant — > 1 distinct value and sd > 0.05 across the 632-player frame. *This is
      the test that catches the silent-0.5 trap.*
- [ ] Coverage does not regress: 632 scored, 43 without a vector.
- [ ] Face-validity review of the top and bottom 50 by a person who watches basketball. Subjective **on purpose** —
      it is the check the audit's worst findings were all caught by. Reported, never gated.
- [ ] Frontend severity thresholds re-checked: `team-outlook`'s 0.35 and 65th-percentile cutoffs were tuned to the
      current distribution and will mis-render if it shifts.

---

## 8. R5 — Decision engine · R6 — Differentiation · R7 — Polish

**R5** — `[Opus]` component redesign: **do not fold `risk` into `performance`** (C12, it is backwards). Fix the
double-count by making `risk` orthogonal — availability and legality exposure only — and let R3's calibration give
`performance` real variance (it is currently sd 1.27, contributing **1.2 %** of composite variance against risk's
67 %). Scaling work should target `fit` (×120), the only component that plausibly clips. `sensitivity.py` needs
**no changes**; `comparisons.py:17`'s hardcoded 5-axis Pareto list, the `scenario_weights` EAV migration, and
Strategy Lab's `(performance, risk)` scatter do.
Also: empirical pick valuation (unblocks `STEPIEN_FUTURE_FIRSTS`); rebuild the generator (salary-matched,
`ORDER BY`, truncation disclosed — it currently reaches **13.8 %** of counterparties); `recency_weighted_features`
is the real cold-cache hotspot at **0.796 s**, not `player_skill_vector` at 0.345 s; modelling-path coverage to
> 70 %, starting with `ingestion/jobs.py` at **0 %**; `make worker` and a `data_quality_issues` upsert to stop
unbounded growth.

**R6** — comparable-trade retrieval (the strongest differentiator, and the only feature that replaces model output
with evidence); need-driven entry; lineup-aware fit — where the deferred tracking work lands, noting
`TeamPlayerOnOffDetails` is **Large**: it requires changing `client.fetch_dataframe`'s single-dataset contract that
all six existing endpoints flow through, plus a `uq_pss` key change; decision-memo export.

**R7** — `EFF` reclassification **with a third field category** (C12); minimum-GP filter *and* percentile-population
fix in Player Explorer; favourite-team persistence including a `storage` listener; component extraction from the
2,679-LOC page; rename TradeLab → RosterLab in the 10 stale docs; rewrite or delete `docs/demo-script.md`; relabel
`docs/rosterlab-enhancement-plan.md` as historical.

---

## 9. Regression-test charter

Coverage inversion is the real problem: the code producing user-visible numbers is least tested. Three classes.

**Class 1 — QA pinning**, one test per finding, xfail-first (R0):
`tests/integration/test_api.py` → QA-2 (plus a builder-level test, since that is where the fix lives), QA-3, QA-5,
QA-7, QA-13 · new `tests/unit/test_evaluation_sanity.py` → QA-1, QA-6, QA-8 · new `tests/unit/test_data_health.py`
→ QA-4 · vitest → QA-9, QA-12 · `test_stats_csv.py` → QA-11.

**Class 2 — Property tests:**

| Property | Pins |
| --- | --- |
| Empty trade scores 50, `prob_positive is None` | QA-5 |
| Roster gut scores < 25 on the modelling path, gate removed | QA-1 / R3-3 |
| A trade with an unmodelled player never returns a neutral score | R1-4 |
| Interval width monotone decreasing in minutes (ρ < −0.95) | R3-4 |
| MC median reproduces the point estimate to 1e-9 | **C2 / R3-5** |
| A turnover need never recommends a higher-turnover player — asserted over all 632, not spot-checked | R4-1 |
| Every skill has > 1 distinct value and sd > 0.05 | **C7 silent-0.5 trap** |
| `verified_legal` never returned when any rule is `unavailable` | protects §3.1 |
| `nba_fresh` never true while any NBA table is stale | R1-1 |
| Drivers sum to `utility − 50` | C13 |
| Query counts: generate < 3,000; evaluate < 25 | R2a |
| No entity name matches `/(test\|smoke\|e2e)/i` | R1-7 |

**Class 3 — Invariants** that make a *class* unrepeatable: freshness consistency, no-undisclosed-defaults,
point-estimate/interval agreement, no-constant-skill. Worth more than any coverage number.

**Tests that will break and must be updated deliberately:** `test_analytics.py:52` (pins `composite_utility → 0.0`),
anything asserting the current `_assets` formula or constant band width, ridge selection assertions, and any
evaluation-response snapshot.

---

## 10. Documentation matrix

Per C12, **at least eight of the ten P0 items cannot merge under house rules without doc diffs** —
`CONTRIBUTING.md` rules 4–5 and the PR honesty checklist require them, and the audit's `Files:` lines contain only
code paths.

| Change | Documents made false |
| --- | --- |
| R1-1 | `docs/data-sources.md`; regenerate `docs/screenshots/data-health.png` and the 7 QA viewports |
| R1-3/4 | `docs/limitations.md`, `docs/methodology.md`, `docs/product-requirements.md`, `docs/demo-script.md` |
| R2b | `docs/limitations.md:8-11`, `docs/cba-rule-coverage.md:25-28,44-53,69-77,83-88`, `docs/data-sources.md:36-44`, `README.md:21,33`, `docs/model-card-market-value.md:3`, `product-requirements.md:60,71`, new ADR |
| **R3-1** | **`README.md:47`, `docs/methodology.md:44-64`, `docs/model-card-player-impact.md` (title, :3, :37-44), `docs/decision-log.md:106`, `docs/interview-guide.md:48`, `docs/product-requirements.md:63`, `docs/resume-bullets.md:22`** |
| R3-2/4 | `docs/methodology.md:25,100-110,139-140`, `docs/model-card-team-projection.md`, `frontend/app/methodology/page.tsx:90-92,118-123` |
| R4 | `docs/limitations.md`, `docs/methodology.md`, `docs/model-card-player-impact.md` |
| R5 | `docs/product-requirements.md`, `docs/architecture.md` |

Do **not** blind-edit `limitations.md:52`'s coverage figure — re-measure first; the audit's "64 %" came from 19 of
76 files and the true value is 68 %.

---

## 11. Recommended first implementation release

**Ship R0 + R1 as the first release. Start R2a immediately after, and begin contract-data acquisition in parallel
on day one.**

### Why not the contracts import first

The audit names it the single best next action. That was right on the evidence available then; measurement changes
it:

1. **Its stated outcome is unreachable.** With full coverage simulated, the badge does not change — `RECENTLY_SIGNED`
   pins `overall_status` at `conditionally_valid`. The team would ship, screenshot the same string, and discover
   the headline outcome was never achievable.
2. **It would make one rule actively less honest** — 30/30 teams flipping to `(pass, high)` on falsified contract
   types, and that will read as progress in the diff.
3. **It depends on an artifact nobody has yet**, and two go/no-go unknowns cannot be resolved without it.
4. **R1 is the only release with zero modelling risk**, and its gate — *no modelled number changed* — is only
   meaningful if it runs before anything else moves.

None of this delays contract work: **R2a delivers a 2.9× speedup with no data at all** and is where the real
blocker (the identity join and coverage measurement) gets instrumented.

### Scope

| # | Item | Model |
| --- | --- | --- |
| R0-1…6 | Sanity fixtures, xfail scaffolding, CI teeth, coverage floor, Playwright in CI, visual-QA exit code | Sonnet |
| R1-1 | Freshness from `nba_api` retrieval times; timezone; empty-vs-derived; issue totals | Sonnet |
| R1-2 | Validation in `build_trade_context`; `Strategy` literal; `?format=` | Sonnet |
| R1-3 | Legality gate; `None`-not-zero; weights; driver reconciliation | **Opus** |
| R1-4 | No defaults as measurements, including `fit.py`'s empty-side 0.5 | **Opus** |
| R1-5 | Rotation sort + `ORDER BY` | Sonnet |
| R1-6 | Conditional no-pressing-needs render | Sonnet |
| R1-7 | E2E DB isolation, demo seed, scenario labelling | Sonnet |
| R1-8 | Hide the generator | Sonnet |
| R1-9 | Labels, hygiene, `.env.example`, compose bootability, zod decision | Sonnet |
| R1-D | Documentation sweep | Sonnet |

### Order

```
R0 ── tests + CI first, xfail(strict=True) on every known-wrong behaviour

Lane A (sequential — evaluation.py / schemas.py / reports.py)
  A1. R1-3  legality gate + composite None semantics        [Opus]
  A2. R1-4  no silent defaults                              [Opus]
  A3. R1-2  validation (build_trade_context + schemas)      [Sonnet]
  A4. R1-5  rotation sort                                   [Sonnet]

Lane B (parallel — disjoint files)
  B1. R1-1  freshness            (data_health.py)           [Sonnet]
  B2. R1-6  team outlook         (team-outlook/…)           [Sonnet]
  B3. R1-8  hide generator       (frontend + trades.py)     [Sonnet]
  B4. R1-9  labels / hygiene     (format.ts, api.ts, …)     [Sonnet]

Then ── R1-7 (changes the dev DB the others test against)
Then ── R1-D docs
```

**A1 before A2** — the gate defines the contract for *"we are not answering this"*, and the silent-defaults work
extends it to partial answers. Reversed, you get two incompatible ways of saying "unavailable", which is the defect
class the release exists to remove. Both Opus for that reason.

### Gate before R2b or R3 merges

- [ ] CI green across all checks, with `alembic check` and the coverage floor now able to fail.
- [ ] Every R0 xfail has flipped to pass; none flipped early.
- [ ] `/data-health` reports stale against the current DB.
- [ ] Roster giveaway returns no decision score and names the 12-man minimum.
- [ ] No rendered value derives from an undisclosed default.
- [ ] **Three fixed trades' evaluation responses differ from `f16dedc` only in the fields R1 deliberately changes.**

### What R1 buys

RosterLab still cannot check salary matching, and its win projections are still uncalibrated — R2 and R3. But every
claim on screen becomes true, every refusal becomes explicit, and the audit's five most serious credibility risks
reduce to two: the unit problem and the defensive proxy. Both now have measured, falsifiable paths — a coefficient
of 14.98 with t = 9.80, and a defensive signal that demonstrably moves Dončić from the 85th to below the 50th
percentile. That is the position from which the rest of this plan is worth executing.

---

*Plan authored against commit `f16dedc`. Audit findings were re-verified against the live database and source, and
the regressions in §1.3 were run rather than reasoned about. Every departure from the audit carries its
measurement.*
