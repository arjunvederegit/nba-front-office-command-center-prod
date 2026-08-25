# RosterLab R1–R7 — closing handoff

The canonical closing document for the RosterLab generation. It is written so a fresh
context can understand the completed system without reading any release chat.

**Repository state**

| | |
| --- | --- |
| Branch | `feat/rosterlab-autonomous-roadmap` |
| Head | `f9c8e38` |
| Base of the generation | `f16dedc` (the audited/planned commit on `main`) |
| Remote | `origin` → `github.com/arjunvederegit/nba-front-office-command-center-prod` |
| `main` | untouched; nothing force-pushed, no history rewritten |
| Migration head | `f2c8b41d6a05` |
| Releases | R0, R1, R2a, R2c, R2b, R3, R4, R5, R5.5, R6, R7 |

---

## 1. What RosterLab is

A decision-support simulator for NBA roster and trade decisions. It answers "should we make
this trade?" by keeping the question in pieces — on-court impact, roster fit, contract value,
competitive window, downside risk, future flexibility — under a CBA rules engine, with
uncertainty attached and precedent from completed trades beside it.

Its organising value is **data honesty**: a missing input is an explicit unavailable state,
never an estimate, and no verdict is upgraded by a check that could not run. That is not a
slogan — it is enforced by tests that assert the *absence* of numbers, and several releases
were spent removing numbers the product had no right to display.

---

## 2. Final architecture

```
Next.js 16 (App Router, 13 routes) ── /api/v1 ──> FastAPI
                                                  ├─ CBA rules engine (four-state honesty)
                                                  ├─ Evaluation (6 components + Monte Carlo
                                                  │              + sensitivity)
                                                  ├─ Analytics (TEI, archetypes, needs,
                                                  │             projection, rotation
                                                  │             allocator, pick valuation)
                                                  ├─ Comparable-trade retrieval (10 seasons)
                                                  ├─ Need-driven acquisition
                                                  ├─ SQLAlchemy + Alembic (35 tables,
                                                  │                       full provenance)
                                                  ├─ Media asset manifest
                                                  └─ Integrations (see §3)
```

**Backend** `backend/app/` — `api/v1` (7 routers), `cba` (builder, engine, rules),
`analytics` (features, impact, archetypes, needs, projection, picks, comparables + its
validation battery, train, score), `services` (evaluation, candidates, acquisition,
comparables, reports, payroll, data_health, and the acquisition/adversarial batteries),
`ingestion` (jobs, identity, quality, runs, contracts, draft_picks, transactions, stats_csv,
demo_seed), `integrations` (nba_api provider, contracts providers, kaggle).

**Frontend** `frontend/` — `app/` (routes), `components/` (shell, ui, charts, court, media,
precedent, acquisition, suggested-deals, evaluation-tabs, brand, toast), `lib/` (api,
schemas, types, format, teamIdentity, needs, shareState, playerStats, scenarioLabels,
favoriteTeam, evaluationDetail).

**Every provider-derived row carries provenance** — `source_provider`, `source_record_id`,
`source_retrieved_at`, `valid_from/to`, `ingestion_run_id`. Every ingestion is wrapped in a
`DataSyncRun`, and since R7 that wrapper is also where the derived-value cache is
invalidated.

---

## 3. Final data sources and provenance

| Source | What it supplies | Status |
| --- | --- | --- |
| `nba_api` → NBA.com | teams, players, rosters, standings, player/team season stats, game log | **primary**, rate-limited, circuit-broken |
| `LeagueGameLog` → `season_calendar` | first and last regular-season game per season | ingested, 10 rows |
| User CSV (`data/imports/`) | 2025-26 season totals, `PLAYER_ID`-keyed | imported, 573 rows |
| Basketball-Reference contracts snapshot | contracts and salaries | **optional, unconfigured by default** |
| Basketball-Reference transaction pages | 565 completed trades, 2016-17…2025-26 | local snapshots, gitignored |
| RealGM future-drafts snapshot | pick ownership | 92 verified of 394 parsed |
| Kaggle basketball DB | player bio/draft enrichment | optional |

**No raw dataset is committed.** Snapshots, databases, caches and QA screenshots are all
gitignored; the only data-adjacent tracked files are the cap-parameter YAML reference set and
clearly-marked synthetic test fixtures.

**The season windows are two settings, not one.**

- `HISTORY_SEASONS` = 2023-24 … 2025-26 — the **modelling** window. Every served estimate is
  fitted and served on exactly these.
- `CORPUS_SEASONS` = 2016-17 … 2025-26 — what the **comparable-trade corpus** may be
  described by.

They read the same table and ask different questions, and their isolation is measured, not
assumed: `test_corpus_window_isolation.py` pins the three structural reasons, and a full
retrain on the ten-season database reproduces **every model's content hash** —
`player_impact`, `player_archetype`, `team_projection` and `tei_to_net_rating` all
re-register byte-identical.

---

## 4. Final analytical systems

**TEI — RosterLab Estimated Impact.** A transparent weighted z-score index over
recency-weighted three-season features. The acronym is historical (it was coined as
"TradeLab Estimated Impact") and is kept because it names a column, an API field and every
registered model version. A ridge challenger was **retired** in R3-1: it won on player-level
MAE (0.637 vs 0.645) and explained R² 0.004 of team net rating against the index's 0.751 —
it was a volume metric, not an impact one.

**The TEI → net-rating conversion.** Fitted change-on-change over 60 team transitions:
coefficient **14.977** (SE 1.528, t 9.80, R² 0.624), per-fold 14.716 / 15.276, LOTO OOS RMSE
2.944 / 3.773 at 56.6 % / 65.0 % of predicting zero. Registered with its regressor
construction, because the coefficient is valid only for that construction.

**Skills (R4).** Four measured defensive/shooting skills replaced two shared ones.
`team_defense` stability 0.838 against the steals proxy's 0.669. Three-point shrinkage k=300
in *attempts*, from three agreeing estimators. Roles are a deterministic size-first chain,
not k-means — label churn under a 10 % drop fell 65.7 % → 1.77 %.

**Projection and the rotation allocator (R5.5).** 240-minute reallocation with availability
discounting. A departure's minutes go **unfilled at replacement level**, because outside a
team's top ten the signal share of served TEI is 0.000. Shedding is proportional; gaining and
shedding are genuinely asymmetric and are modelled separately.

**The composite (R5).** Six components, missing ones excluded with the weights renormalized
and the exclusion disclosed. `risk` does not read the outcome distribution (re-adding it
restores a 0.86 correlation with `performance`). `assets` does not score salary (0.837
correlation with `contract`). Nothing is truncated — `bounded_score` has unit derivative at
50, so every documented scale constant still holds.

**Pick valuation (R5-2).** Empirical, and honest about what it cannot do: the curve does
**not** beat a round-only rule (+0.0405, p = 0.22). What is established is the gradient
inside the first round (0.3277, p = 0.0023). A conditional pick has no point estimate.

**Comparable-trade retrieval (R6-2, widened R7-2).** See §6.

**Need-driven acquisition (R6-3).** Filter and rank are two stated rules, never merged,
because nothing here labels a target as good so the weight between them cannot be fitted.
Every candidate is run through the trade evaluator before it is shown.

---

## 5. Final user-facing workflows

| Route | What it does |
| --- | --- |
| `/` | Overview, favourite-team shortcuts, honest freshness badge |
| `/team-outlook` · `/team-outlook/[id]` | Roster by position group, measured strengths and needs, competitive window, payroll status, strategy, and the need-driven acquisition panel |
| `/trade-evaluator` | 2–3-team construction, live backend rules check, evaluation with seven tabs (impact, fit, cap, timeline, risk, precedent, rotation consequences), save and share |
| `/strategy-lab` | 2–5 saved deals side by side, live re-weighting, Pareto frontier on all six components, rank stability |
| `/player-explorer` | 573 imported stat lines, totals and per-game never mixed, qualified league percentiles, 2–4-player comparison |
| `/salary-cap-center` | Payroll by season; fully honest empty state until contracts are imported |
| `/data-health` | Seven sources with coverage, freshness and a next step each |
| `/methodology` | Plain-language and technical layers over every number |
| `/about` | What the product is, what it deliberately does not ship |
| `/trades/[id]` · `/players/[id]` | Saved trade with the decision memo; player detail |

---

## 6. Comparable-trade methodology

**The retrieval unit is a side, not a trade.** "Boston traded Smart for Porziņģis" and
"Washington traded Porziņģis for Smart" are one transaction and two decisions. A three-team
trade contributes three sides, and at most one side of any trade appears in a result list.

**One constructor.** `services/comparables._side` builds the query side and every corpus
side. A retrieval engine whose halves are built differently measures the construction.

**The season a trade is described by** comes from `season_calendar` — a trade between a
season's first and last regular-season game is described by that season; otherwise by the
most recently completed one. R7 replaced a calendar-month rule that was describing 57 of 565
trades by a season that had not started.

**The distance.** Fifteen features in six dimensions; each dimension's distance is the mean
over the features both sides state, and the total is the weighted mean over surviving
dimensions. `|Δ| / (|Δ| + s)` — bounded, monotone, scale-free, nothing truncated. Counts get
a declared unit; continuous quantities get the corpus interquartile range. First-round picks
are split by conveyance, because with a single share a top-4 protection changed nothing.

**Weights** are chosen by construct and reported with every result: player value 0.30, draft
capital 0.25, structure 0.20, age 0.10, team context 0.10, timing 0.05. Nothing here labels
two trades as similar, so there is no target to fit them against.

**Deliberately excluded**: salary (no historical contract source), cash and trade exceptions
(the query can only answer "no", which penalizes 37 % of completed trades), and **what
happened next** — resemblance is not consequence, and the panel says so.

**Validation** (`make comparable-validation`, 1,151 sides, 68 s): archetype precision@5
**0.917** against a 0.433 base rate, random null 0.444, shuffled null 0.424; direction
confusion 0.025 (ceiling 0.05); best single-dimension null 0.060 (ceiling 0.75); scale-form
0.761 and distance-form 0.717 (floor 0.50); perturbation rank displacement 4.33 (ceiling 10).

---

## 7. Final CBA and contract coverage

**The four-state honesty standard.** Every rule returns `pass`, `fail`, `warning` or
`unavailable`, and `overall_status` is never `verified_legal` while any rule is
`unavailable`. This is the load-bearing property of the whole product.

**What is covered**: expanded/standard TPE bands (verified 2025-26 and 2026-27 figures),
apron restrictions, aggregation prohibition, roster limits, recently-signed windows, Stepien.
Rule-by-rule detail in `docs/cba-rule-coverage.md`.

**What is unavailable, and why it cannot be fixed from the current sources.** The
Basketball-Reference snapshot carries no `contract_type`, `signed_date` or `no_trade_clause`
— NULL on all 401 imported contracts. Those three fields are why `overall_status` stays
`conditionally_valid`, and no implementation quality changes it. A hand-curated CSV at
`data/contracts/contracts.csv` with `CONTRACT_DATA_PROVIDER=file` is the only route to
`verified_legal`.

Consequences worth carrying forward: a second-apron aggregation cannot be refuted without
contract types, and **salary-matching violations are not refutable** — an illegal deal fails
on roster rules or not at all.

R2c made the same snapshot useful for **30 teams instead of 0** by disclosing partial payroll
coverage, without loosening a single verdict. `teams_with_complete_payroll` is still 0/30,
still computed, still published, and no longer gates the release.

---

## 8. Trade-decision methodology

A trade produces one evaluation **per team**, never a single verdict. Each carries:

- a **decision score** 0–100 where 50 is the composite's own definition of "changes nothing";
- a `decision_status` of `scored`, `suppressed_illegal` or `insufficient_data`;
- the components that were **not** scored and the note that the remaining weights were
  rescaled;
- the players who have no impact estimate, named, left out of the projection rather than
  given a league-average stand-in, and still counted against roster limits;
- a **wins band** from 2,000 draws — median, p10–p90, P(positive) — because the midpoint
  alone would overstate what the model knows;
- rotation consequences by role, from the allocation the projection produced;
- precedent, and a consolidated statement of what is not known.

**A verified-illegal trade carries no decision score.** Eleven scenarios in
`make adversarial-validation` assert these properties on the live database.

---

## 9. Test and QA status at close

```
backend pytest             906 passed · 1 skipped · 0 xfailed
backend coverage           88.45 %, floor 85 (CI-enforced)
frontend vitest             82 passed, 9 files
ruff · mypy (97 files) · eslint · tsc                 clean
production build           13 routes
migrations                 clean DB → head → base → head; `alembic check` no drift
Playwright                   6 passed, including a database-identity guard
visual QA                  105 shots, 15 routes, 7 viewports — clean
adversarial battery         11 / 11
comparable battery          every gated criterion
acquisition battery         4 / 4 gated
R3 gate                    bit-identical, including after a full retrain
```

All 23 QA findings from the original audit are closed; **0 strict xfails remain**.

---

## 10. Performance characteristics

| Path | Measured |
| --- | --- |
| `POST /trades/evaluate` (2-for-2) | 61 → **≤ 25** queries (budgeted) |
| `POST /trades/generate` | 21,326 → **< 3,000** queries; 2.15 s → ~1.0 s at 7× the coverage |
| Cold `/trades/evaluate`, league role reference | 37 → **8** queries |
| Player directory (`/players/season-totals`) | 573 → **≤ 6** queries, constant in rows |
| Feature-window collapse | 1.045 s → **0.045 s** (exact to 9.1e-13) |
| `make comparable-validation` | **68 s** on 1,151 sides |

Budgets are expressed in **queries**, not seconds: SQLite hides the round-trip cost that
dominates on the compose Postgres path.

---

## 11. Known limitations

Carried forward verbatim into the next generation. The full list is in
`ROSTERLAB_R7_IMPLEMENTATION_REPORT.md` §11; the ones that constrain design decisions:

1. **No contract data by default.** Salary matching, aprons and payroll are unavailable
   product-wide, and no amount of implementation changes it.
2. **No validated defensive metric.** Every available target derives from on-court
   `DEF_RATING`, so every test is circular to some degree.
3. **No lineup-aware fit.** Refused on measurement, not deferred on schedule: the median
   five-man group has 20.2 minutes and an implied ±16 net-rating standard error against a
   ±10 league spread. `make lineup-availability` re-runs it.
4. **The rotation allocator is implausible in levels.** Fixing it needs a load-shaped
   estimand, which means separating role from availability throughout the projection — and
   the R3 coefficient is fitted on the current meaning of `minutes`.
5. **30 of 565 trades remain unrankable**, and era comparability degrades before 2016-17.
6. **The pick curve does not beat a round-only rule.**
7. **Draft-pick ownership is 92 verified of 394.**

---

## 12. Deferred external-data dependencies

None of these is a code problem. Each is an acquisition nobody has scheduled.

| Wanted | Unlocks | Notes |
| --- | --- | --- |
| Contract types, signed dates, no-trade clauses | `verified_legal`, salary-matching refutation, second-apron aggregation | hand-curated CSV is the only known route |
| Matchup / tracking data | an honest defensive metric | every in-repo target is circular |
| Five-man lineup data with usable samples | lineup-aware fit | reachable but under-powered; measured and refused |
| Pre-2016 transaction pages + player seasons | the last 30 unrankable trades | diminishing returns, worsening era comparability |
| Historical contracts | a contract-prediction model | deliberately not shipped; RosterLab ships no fake models |

---

## 13. Major lessons from R1–R7

1. **A criterion a null can pass is not a criterion.** Applied to A′/A″ in R4-2, to the
   mirror in R6, and to `perturbation_stability` in R7 — where the zero-information null
   scored a *perfect* 1.0000 against the shipped distance's 0.6110.
2. **Distinguish validity from robustness.** R7 nearly over-applied lesson 1 and deleted
   half the battery. Robustness checks are necessary and never sufficient; they must be
   labelled, not gated as though they proved something.
3. **A gate no correct implementation can pass measures the data, not the work.** R2b's
   original 27/30 criterion was unreachable from the available artifact at any quality.
4. **Withdraw a claim rather than restate it weakly.** The point-of-attack composite scored
   *worse* than the proxy it replaced on its own pre-registered class, so it was deleted and
   the team-side need now says no player skill addresses it.
5. **Measure before optimising, and after.** Every performance change in this repository is
   accompanied by an equality assertion, because the one that was not nearly shipped a
   validation check that compared the shipped ranking against itself.
6. **A silent catch turns infrastructure failure into a modelling result.** A bare
   `except Exception: continue` made a migration-behind database look like a league with no
   good trades in it.
7. **A test that cannot fail is worse than no test.** Three were found while writing R7's
   adversarial battery — a key spelled wrong, scenarios that built nothing, and a false
   assumption about sort order that made the model look inverted.
8. **Check what the test is testing.** `make e2e` was passing against the wrong database for
   an unknown number of releases.
9. **Two windows on one table need two settings and a test.** Widening the corpus was safe
   *because* the modelling window was separately named and separately proven.

---

## 14. Systems to preserve during future development

These were established by measurement and should not be reopened without new data. Each has a
test that fails if it is.

1. **The four-state honesty standard** and `verified_legal` never surviving an `unavailable`.
2. **No defaults rendered as measurements** — `tei` is null, never 0.0; `prob_positive` is
   null on an empty trade, never 0.0.
3. **The R3 conversion coefficient and its registered construction.**
4. **Replacement-minute treatment**: a departure's minutes go unfilled at replacement.
5. **Risk orthogonality**: `risk` must not read the outcome distribution.
6. **`assets` must not score salary.**
7. **A conditional pick has no point estimate.**
8. **No component may be truncated.**
9. **The comparable side as the retrieval unit, built by one function**, with counts carrying
   declared units and firsts split by conveyance.
10. **`roster_shape` reads the allocation the projection produced**, never re-derives it.
11. **The refusal to ship lineup-aware fit** until the data supports it.
12. **The corpus/modelling window separation.**

---

## 15. Systems that should eventually be replaced

1. **The rotation allocator's level model** — right by every out-of-sample comparison
   available and still implausible in levels. Needs a load-shaped estimand.
2. **The defensive composite** — justified by construct, not validated, and honest about it.
3. **`fit` scaling** — the only component that plausibly clips; R5 squashed rather than
   truncated, which is a fix and not an answer.
4. **The BBRef contract path** — a snapshot parser standing in for a contract database.
5. **The trade-evaluator page's board region** (~900 lines, coupled to drag state).
6. **`docs/rosterlab-enhancement-plan.md`** — labelled historical, retained for provenance;
   delete when nothing references it.

---

## 16. Reproducing this state from a clean checkout

```bash
make setup
make migrate
make sync-data                                # NBA.com
make sync-corpus-stats                        # ten seasons + season calendars
make import-stats-csv
make import-draft-picks
make fetch-transactions FROM=2017 TO=2026
make import-transactions
make train && make score
make test && make lint
make adversarial-validation
make comparable-validation
make acquisition-validation
make e2e
make visual-qa OUT=docs/qa/run
```

Two environment notes that cost real time and are not obvious:

- **If the generator returns nothing, check `alembic current` before the ranking.** A
  database one migration behind used to present as a modelling outcome; since R7 it presents
  as `coverage.construction_errors` with the exception type named.
- **If the frontend toolchain hangs at 0 % CPU, check for iCloud-evicted `node_modules`.**
  `find node_modules -type f -flags +dataless | wc -l`; the fix is to read the files
  (`… -print0 | xargs -0 -P 32 -n 30 cat > /dev/null`), not `brctl download`.

---

## Foundation for Pivot

*Describing what exists, not designing what comes next. The purpose is a clean technical
boundary, so the next generation knows what it can build on and what it must not assume.*

**Ready to be inputs, with validation behind them.**

- **The provenance-carrying ingestion layer.** Every row knows where it came from, when, and
  under which run; every ingestion invalidates the derived cache. Any new consumer inherits
  this for free.
- **The comparable-trade corpus and its retrieval.** 565 completed trades, 1,151 rankable
  sides, ten seasons, side-level, with a validation battery that separates validity from
  robustness. This is the only part of RosterLab that answers a question with **evidence**
  rather than with model output, and it is the most directly reusable asset here.
- **The CBA rules engine and its four-state standard.** Its value is the honesty contract,
  not the rule count; anything built on top inherits "never legal from a partial check".
- **The season calendar.** Small, and it settles a question — "had this been played yet?" —
  that any historical analysis has to answer.
- **The evaluation contract**: per-team evaluations, excluded components disclosed,
  unmodelled players named, uncertainty as a band.
- **The validation-battery pattern itself** — thresholds stated before measurement, nulls
  published beside every result, and a command that exits non-zero.

**Available but conditional.** TEI and the R3 conversion are sound *for their fitted
construction*; anything that changes what `minutes` means invalidates the coefficient and
must re-run the gate. The skills are measured but the defensive ones are not validated.

**Do not assume.** Contract data, defensive validation, and lineup-level fit are all absent
for documented reasons, and each has a measurement showing why. Re-run the relevant command
before treating any of them as available.

**The boundary.** RosterLab R1–R7 is complete. Nothing in this document proposes work; the
next roadmap should be designed on its own terms, against the limitations in §11 and the
deferred dependencies in §12.
