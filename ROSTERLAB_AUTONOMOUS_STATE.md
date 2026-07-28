# RosterLab — Autonomous Run State

**Purpose:** resumable state for the autonomous roadmap execution described in
`ROSTERLAB_IMPLEMENTATION_PLAN.md`. A fresh session can read this file alone and continue safely.

---

## Environment

| Fact | Value |
| --- | --- |
| Repo root | `/Users/arjunvedere/Desktop/nba-front-office-command-center-prod/nba front office command center prod` |
| Working branch | `feat/rosterlab-autonomous-roadmap` |
| Base commit | `f16dedc` (main, the audited/planned commit) |
| Remote | `origin` → `https://github.com/arjunvederegit/nba-front-office-command-center-prod.git` |
| `gh auth` | ✅ `arjunvederegit`, scopes `gist, read:org, repo, workflow` |
| Backend venv | `backend/.venv` (Python 3.11.14) |
| Node | v25.5.0, `frontend/node_modules` present |
| DB backup | `<scratchpad>/backups/tradelab.db.baseline` (17 MB, taken before any change) |

## Baseline measurements (commit `f16dedc`)

| Metric | Value |
| --- | --- |
| Backend tests | **114 passed**, 1 warning, 4.32 s |
| Backend coverage (`--cov=app`) | **68 %** (4263 statements, 1375 missed) |
| Frontend unit tests | **15 passed** (2 files) |
| `data/external/` | **empty** — the Kaggle `nbadb` dataset is NOT present |

## Datasets present (inspected)

| Path | Bytes | Nature |
| --- | --- | --- |
| `data/cba/nba_cap_parameters.yml` | ~4 K | Cap/tax/apron/MLE 2026-27 (**confirmed**, NBA Communications) → 2032-33 (estimates/projections, SalarySwish). Carries an explicit `status` per season. |
| `data/imports/contracts/players.html` | 454 K | Basketball-Reference contracts snapshot, saved 2026-07-28 |
| `data/imports/draft_picks/realgm_future_drafts.html` | 291 K | RealGM "NBA Future Drafts Detailed", page datetime 2026-07-28 00:49:32 |
| `data/imports/nba_player_stats_2026.csv` | 820 K (dir) | 2025-26 season totals, already wired to `make import-stats-csv` |
| `data/external/` | 0 | **empty — Kaggle `nbadb` unavailable** |

---

## Current position

**Releases complete and pushed:** R0, R1, R2a. Each gate passed; see the per-release reports.
**R2b is BLOCKED on a data artifact** — measured, not assumed (see below).
**Next:** R2c (disclosed-coverage payroll), inverting the plan's order — its precondition is met.
**Status:** stopped at a documented blocker with a clean, pushed tree.

## Completed work

| Item | Commit | Evidence |
| --- | --- | --- |
| **R0** — test scaffolding, CI teeth, demo seed, Playwright in CI, visual-QA gate | `af236d0` | 125 passed / 23 xfailed / cov 69.07 %; e2e 5 passed on a fresh demo DB; visual QA 98 shots clean |
| **R1-3** — legality gate, composite `None` semantics, weights, driver reconciliation | `c101d56` | QA-1 72.85 → suppressed; QA-5 46.36 → 50.0; QA-8 0.85 → null; drivers 1.31 = 1.31 |
| **R1-4** — no defaults rendered as measurements | `da1e2d4` | `tei` null not 0.0; `unmodeled_players` disclosed; new `test_no_silent_defaults.py` (11 tests) |
| **R1-2** — trade construction validation, `Strategy`/`ReportFormat`, QA-13 | `402baab` | phantom/duplicate/strategy/2034-pick/format all 422 with readable messages |
| **R1-5** — rotation sort + `ORDER BY` + always include traded players | `18df54a` | Curry now present at +24.2; both lists minutes-sorted |
| **R1-1** — freshness from `nba_api` retrieval times | `682e672` | `/data-health` stale, Jul 21 not Jul 27; nav "Data aging"; 562 open issues reported |
| **R1-6 + R1-8** — no-pressing-needs state; generator hidden | `58a4c6b` | Atlanta no longer double-lists; generator discloses 13.8 % coverage |
| **R1-9** — labels, one confidence, hygiene, zod decision | `433677d` | monotone verdicts; content-hashed model versions + migration; `hmac.compare_digest` |
| **R1-7** — test-data isolation | `ae07f71` | 22 trades / 16 scenarios / 50 comparisons purged; dropdown disambiguated |
| **R1-D** — documentation + gate | `01d2c02` | `limitations.md`, `methodology.md`, stale-doc banners, 7 screenshots regenerated |
| **R2a-1** — batch loading, memoization | `8b0fe82` | generate 21,326 → **46** queries / 2.15 s → 0.36 s; evaluate 61 → **15**; same 8 candidates |
| **R2a-2** — coverage instrumentation, identity join | `dc645d5` | roster-side coverage; 4-tier identity resolver; `make contract-coverage` / `import-contracts` |

Remaining xfail pins: **3** (20 of 23 flipped)
- QA-1 roster-gut `performance < 25` → R3-3 (unreachable before the calibration; C12)
- C2/R3-5 Monte-Carlo/point-estimate agreement → R3-5
- QA-11 `EFF` classification → R7 (needs a third field category; C12)

## Commits

```
dc645d5 feat(ingestion): instrument contract roster coverage before import
8b0fe82 perf(cba): batch-load contract salaries and memoize cap parameters
01d2c02 docs: bring limitations, methodology and screenshots in line with R1
ae07f71 chore(dev): isolate the e2e database and purge test entities
433677d fix(app): monotone verdict labels, one confidence, and R1 hygiene
58a4c6b fix(team-outlook): show no-pressing-needs state; hide the candidate generator
682e672 fix(data-health): derive NBA freshness from nba_api retrieval times
18df54a fix(evaluation): sort rotation detail and always include traded players
402baab fix(api): reject phantom, duplicate and unknown-strategy trade moves
da1e2d4 fix(evaluation): never substitute league-average defaults for missing player data
c101d56 feat(evaluation): suppress the decision score for verified-illegal trades
af236d0 test+ci: add sanity scaffolding, enforce coverage, and give CI gates teeth
f16dedc (main) baseline
```

All pushed to `origin/feat/rosterlab-autonomous-roadmap`.

## Decisions and deviations

1. **`make seed-demo` pulled forward from R1-7 into R0** — the CI Playwright gate cannot
   run without a database. Team identity comes from `nba_api`'s bundled *static* table
   (offline); everything else is synthetic, stamped `source_provider="demo_seed"`, and the
   seeder refuses to run where `nba_api` rows exist.
2. **Coverage floor** — the plan's "measured 68 %" is the rounded display; the precise
   baseline was 67.74 %, so a floor of 68 fails at `f16dedc`. Covered `demo_seed.py`
   instead of lowering the floor. Now 69.46 %.
3. **`scripts/visual_qa.mjs` could not run at all** — ESM resolves bare specifiers from the
   importing file's directory, and there is no `node_modules` at the repo root. Both
   harness scripts now resolve through `createRequire` against `frontend/package.json`.
4. **QA-8 landed in the R1-3 commit, not R1-4** — the availability default and the
   `prob_positive` default are the same expression in `_risk`, and a strict xfail must flip
   in the same commit as its fix.
5. **`fit` is withheld when one side of a deal is empty** rather than scored against a
   fabricated 50th-percentile player. R5 introduces a measured replacement baseline so
   one-way deals can be scored again; until then the component is excluded and disclosed.
6. **The phantom-move check only fires when the player is on some current roster.** A
   player on no roster is an unknown-roster case, not a phantom move; refusing it would
   block every offseason signing.
7. **The e2e full-flow assertion was widened**, because the deal it builds is now
   *correctly* refused when the counterparty already carries 18 players. It accepts either
   a fan verdict or the explicit refusal, and requires the refusal to name its rule.

## Active blockers

### R2b — its acceptance criterion cannot be met with the available artifact

Measured on a scratch copy of the dev database against
`data/imports/contracts/players.html` (BBRef, saved 2026-07-28). Nothing was written to
the dev database.

```
matched                                       886 rows
  exact_name 867 · suffix_insensitive 10 · unaccented 9
unmatched                                     154 rows
ambiguous                                       0 rows
seasons present                     2026-27 … 2031-32   (cap league year present ✓)
roster players with a 2026-27 salary      392 / 530     (74.0 %)
teams with a computable payroll             0 / 30      ← R2b requires ≥ 27/30
```

The **join works** — 886 bound, zero ambiguous, and the snapshot carries the league year
that governs trade legality. The gap is coverage: 138 rostered players (26 %) have no
2026-27 salary in an offseason snapshot, mostly expired deals, and `_team_payroll` is
all-or-nothing so one missing player removes a whole team. The plan's sensitivity table
put 20 % missing at 0/30; at 26 % it lands where predicted.

Unblocking needs **either** R2c's disclosed-coverage model (no new data; precondition
met) **or** a hand-curated CSV at `data/contracts/contracts.csv` with
`CONTRACT_DATA_PROVIDER=file`, carrying `nba_player_id`, `signed_date`,
`no_trade_clause` and `contract_type` — the three fields that per C8 otherwise keep
`overall_status` pinned at `conditionally_valid` at any BBRef coverage level.

### Kaggle `nbadb` absent

Expected at `data/external/` (also `KAGGLE_DATA_DIR`; consumed by
`backend/app/integrations/kaggle_nba/importer.py` via `make import-kaggle`). Blocks R6's
lineup-aware fit and any tracking/play-type work. **Blocks nothing in R0–R5.**

## Exact next step

**Run R2c — the disclosed-coverage payroll model — before R2b**, inverting the plan's
order. The plan gates R2c on "only after R2b proves the join works"; the measurement
above proves it. With disclosed coverage the existing snapshot becomes useful for 30
teams instead of 0.

```bash
git checkout feat/rosterlab-autonomous-roadmap
cd "nba front office command center prod"
make contract-coverage        # the 0/30 baseline R2c has to beat
```

1. Replace `_team_payroll`'s all-or-nothing return with a payroll **plus its coverage**:
   `(payroll_of_known, players_known, roster_size)` is already the shape — stop discarding
   the sum when `known < total`, and carry the counts forward.
2. Thread the disclosure through `TeamContext.payroll_before/after` and into the API, so a
   figure is never rendered without "computed from 16 of 18 contracts; 2 unknown" beside
   it.
3. **The salary rules must still report `unavailable`.** A matching verdict computed from
   a partial payroll is exactly the failure R1 exists to prevent; disclosed coverage makes
   the *number* useful, not the *verdict*.
4. Acceptance: a team with one unknown salary shows a payroll and its coverage, and
   `SALARY_MATCHING` still reports `unavailable` for that team.

If R2c is not wanted, **R3 is the critical path** and depends only on R1. Start with R3-1
(promote the transparent index, retire the ridge) — fitting on ridge TEI yields a
coefficient indistinguishable from zero and would be misdiagnosed as a calibration bug
rather than a metric one.

## Push status

`origin/feat/rosterlab-autonomous-roadmap` is up to date through R2a. `main` untouched; no history rewritten.
