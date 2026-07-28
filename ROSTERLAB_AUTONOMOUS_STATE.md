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

**Release:** R1 — **complete and pushed**. Gate passed; see `ROSTERLAB_R1_IMPLEMENTATION_REPORT.md`.
**Next:** R2a — performance and instrumentation (no contract data required).
**Status:** starting R2a

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
| **R1-D** — documentation + gate | (this commit) | `limitations.md`, `methodology.md`, stale-doc banners, 7 screenshots regenerated |

Remaining xfail pins: **3** (20 of 23 flipped)
- QA-1 roster-gut `performance < 25` → R3-3 (unreachable before the calibration; C12)
- C2/R3-5 Monte-Carlo/point-estimate agreement → R3-5
- QA-11 `EFF` classification → R7 (needs a third field category; C12)

## Commits

```
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

- **Kaggle `nbadb` absent.** Expected at `data/external/` (see `backend/app/integrations/kaggle_nba/importer.py`
  for the tables consumed). All lineup-aware fit, tracking and play-type work is deferred; nothing in R0–R5 is
  blocked by it.

## Exact next step

Begin **R2a — performance and instrumentation** (`ROSTERLAB_IMPLEMENTATION_PLAN.md` §5). It needs no
contract data and ships alone.

1. Measure the baseline first, with a query counter around `POST /trades/generate` and a 2-for-2
   `POST /trades/evaluate`. The plan's measured baseline is **21,112 queries / 2.55 s** for generate and
   **60 queries** for evaluate; confirm both on the current code before changing anything, because R1
   already touched `_roster_cards` and `candidates.py`.
2. Request-scoped resolver in `app/cba/builder.py`: memoize `load_cap_params` (1,197 identical calls per
   request), batch `Contract`+`ContractYear` per roster, cache payroll per `(team, season, league_year)`.
3. Fix the function-local private imports at `evaluation.py:397,404` and the lazy-load N+1 at
   `analytics/score.py:46`.
4. Instrument `sync_contracts` coverage **before** any import: `roster_players_total`,
   `roster_players_with_salary_for_cap_league_year`, `teams_with_complete_payroll`,
   `seasons_present_in_snapshot`, and the **roster-side** unmatched list.
5. Harden the identity join (unaccent as a fallback tier only — the database is internally inconsistent,
   `Bogdan Bogdanović` keeps diacritics while `Alperen Sengun` does not).
6. `make import-contracts`; resolve `CONTRACT_DATA_FILE` against the repo root, not CWD.

Acceptance: generate < 3,000 queries and < 1.2 s with the same 8 candidates; evaluate < 25 queries.
Pin both with query-count tests.

## Push status

`origin/feat/rosterlab-autonomous-roadmap` is up to date through R1.
