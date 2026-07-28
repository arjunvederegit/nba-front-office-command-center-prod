# RosterLab — Autonomous Implementation Report

**Branch:** `feat/rosterlab-autonomous-roadmap` → pushed to `origin`
**Base:** `f16dedc` (main) · **Head:** `dc645d5` + this report
**Scope executed:** R0 → R1 → R2a. R2b is **blocked on a data artifact**, measured rather than assumed.

---

## 1. Releases completed

| Release | Status | Commits |
| --- | --- | --- |
| **R0** — test scaffolding and CI teeth | ✅ complete, gate passed | `af236d0` |
| **R1** — correctness and honesty | ✅ complete, gate passed | `c101d56` `da1e2d4` `402baab` `18df54a` `682e672` `58a4c6b` `433677d` `ae07f71` `01d2c02` |
| **R2a** — performance and instrumentation | ✅ complete, acceptance met | `8b0fe82` `dc645d5` |
| **R2b** — contract import | ⛔ **blocked**: its gate is unreachable with the available artifact (§6) | — |
| R2c, R3–R7 | not started | — |

Reports: `ROSTERLAB_R0_IMPLEMENTATION_REPORT.md`, `ROSTERLAB_R1_IMPLEMENTATION_REPORT.md`,
`ROSTERLAB_R2A_IMPLEMENTATION_REPORT.md`. Resumable state: `ROSTERLAB_AUTONOMOUS_STATE.md`.

## 2. Commits by release

```
R2a  dc645d5  feat(ingestion): instrument contract roster coverage before import
     8b0fe82  perf(cba): batch-load contract salaries and memoize cap parameters
R1   01d2c02  docs: bring limitations, methodology and screenshots in line with R1
     ae07f71  chore(dev): isolate the e2e database and purge test entities
     433677d  fix(app): monotone verdict labels, one confidence, and R1 hygiene
     58a4c6b  fix(team-outlook): no-pressing-needs state; hide the candidate generator
     682e672  fix(data-health): derive NBA freshness from nba_api retrieval times
     18df54a  fix(evaluation): sort rotation detail and always include traded players
     402baab  fix(api): reject phantom, duplicate and unknown-strategy trade moves
     da1e2d4  fix(evaluation): never substitute league-average defaults for missing data
     c101d56  feat(evaluation): suppress the decision score for verified-illegal trades
R0   af236d0  test+ci: add sanity scaffolding, enforce coverage, and give CI gates teeth
     f16dedc  (main) baseline
```

**GitHub push status: all commits pushed.** `feat/rosterlab-autonomous-roadmap` tracks
`origin/feat/rosterlab-autonomous-roadmap` and is in sync. `main` was not touched, no
history was rewritten, no force-push, no PR opened or merged.

## 3. Before and after

Every row reproduced live against `localhost:8000` on the ingested development database.

| Finding | Before | After |
| --- | --- | --- |
| **QA-1** BOS sends all 16 players to LAL | `composite_utility 72.85`, confidence medium, *"Proceed with further diligence"* | `null`, `decision_status suppressed_illegal`, ROSTER_SIZE named with the 12-man minimum |
| **QA-2** LAL player sent *from* BOS | 200; LAL scored **61.67 / +0.45 wins** for acquiring its own player | 422, *"not on the roster they are being traded from: Deandre Ayton"* |
| **QA-3** duplicate move | 200, counted twice | 422, *"the same player appears in more than one move: Jayson Tatum"* |
| **QA-4** `/data-health` | *"✓ fresh · updated Jul 27, 1:45 AM"*, nav 🟢 "Live data" | **stale**, Jul 21 02:04, nav "Data aging", 7 stale tables named |
| **QA-5** empty trade | 46.36, `prob_positive 0.0` | **50.0**, `prob_positive null` |
| **QA-6** Giddey ↔ Curry chart | Curry absent; **Jalen Smith 0.0 → 12.4** fabricated | Curry present at **+24.2**; Jalen Smith −0.1; minutes-sorted |
| **QA-7** `strategy: "win_now_lol"` | 200, silently different weights | 422 naming the seven valid values |
| **QA-8** report, no incoming | *"Historical availability of incoming players: **85 %**"* | line absent |
| **QA-9** Atlanta outlook | "Defensive rebounding 67th" under Strengths **and** Needs | Strengths only; explicit *"No pressing needs"* |
| **QA-12** verdict labels | 46 → "High-risk upside", 52 → "Mixed outcome" | 46 → "Net negative", 52 → "Roughly neutral" |
| **QA-13** `draft_year: 2034` | `"[{'type': 'less_than_equal', 'loc': …}]"` | `"pick_moves[0].draft_year: Input should be ≤ 2033"` |
| **W8/QA-10** generator reach | ~21 % claimed | **13.8 %** measured, stated in the docs *and* in every response |
| **C13** driver reconciliation | utility − 50 = 7.06 vs drivers 4.94 | **1.31 = 1.31** |
| **C13** 43 unmodelled players | `tei = 0.0`, the 63rd percentile | `null`, named, confidence low |
| **C13** open quality issues | 50 shown, total unknowable | **562** total + per-check breakdown |
| **C13** `model_versions` | `v202607210204` ×3, 9 rows / 6 distinct | content hashes, 6/6, `UNIQUE` constraint |
| **C13** superseded estimates | 1,536 rows, +512 per train, never collected | GC'd on every train |
| **C13** test entities in dev DB | 22 trades, 16 scenarios, 50 comparisons, undisclosed | purged; `make purge-fixtures`; documented |
| **C11** `/trades/generate` | **21,326 queries / 2.15 s** | **46 queries / 0.36 s** |
| — `/trades/evaluate` (2-for-2) | 61 queries | **15** |
| — `app.cli score` | **crashed** on any second run | 93 queries / 0.07 s, idempotent |

## 4. Datasets used

| Dataset | Status |
| --- | --- |
| NBA.com via `nba_api` (ingested dev DB: 5,121 players, 530 roster spots, 5,715 stat rows) | used throughout; last retrieved Jul 21 |
| `nba_api` **static** team table (offline, bundled) | used for the demo seed's team identity |
| `data/imports/contracts/players.html` (BBRef, saved 2026-07-28) | **inspected and measured**, on a scratch DB copy. 886 records, 2026-27 → 2031-32, 74 % roster coverage. Not imported into the dev DB — see §6 |
| `data/imports/nba_player_stats_2026.csv` | already ingested; used to prove the freshness filter (`user_csv` must not pass for an NBA sync) |
| `data/cba/nba_cap_parameters.yml` | **inspected, not wired in.** Cap/tax/apron/MLE 2026-27 (confirmed) → 2032-33 (estimates), with an explicit per-season `status`. The pick-valuation work that needs future cap years is R5; committing a user-supplied data file was left as the repository owner's decision, so it remains untracked |
| `data/imports/draft_picks/realgm_future_drafts.html` | **inspected, not used.** Future pick ownership belongs to R5's `STEPIEN_FUTURE_FIRSTS` work; using it now would add a data surface no release gate covers |
| Kaggle `nbadb` | **absent.** `data/external/` is empty — see §7 |

**No data was fabricated, synthesized, scraped, or fuzzy-matched.** Records that could not
be resolved to exactly one player are reported as ambiguous and left unbound.

## 5. Tests, builds and QA

| | baseline `f16dedc` | now |
| --- | --- | --- |
| Backend tests | 114 passed | **203 passed, 3 xfailed** |
| Backend coverage | 67.74 % (unenforced) | **74.14 %**, floor enforced at 68 |
| Frontend tests | 15 passed | **36 passed** |
| Playwright | never run in CI; needed a developer's DB | **5 passed in CI** on a dedicated seeded DB |
| Visual QA | could not import Playwright at all; could never fail | **98 screenshots**, 14 routes × 7 viewports, exits non-zero on problems |
| `alembic check` | swallowed by `\|\| true` | enforced; clean on a fresh DB and on the migrated dev DB |

Full CI-equivalent run at the end of this session, all green:

```
ruff check app tests                    All checks passed!
mypy app                                Success: no issues found in 81 source files
pytest --cov=app --cov-fail-under=68    203 passed, 3 xfailed · TOTAL 74.14 %
alembic upgrade head (clean DB)         3 migrations
alembic check                           No new upgrade operations detected.
npm run lint / tsc --noEmit             clean
npm run test -- --run                   5 files, 36 passed
npm run build                           ✓ Compiled successfully
make e2e (dedicated demo database)      5 passed
node scripts/visual_qa.mjs              CLEAN — no overflow, no console errors, no empty pages
```

Docker image builds are covered by CI only; `docker` is not installed on this machine.

**Branch hygiene:** 91 files changed. Nothing outside `backend/`, `frontend/`, `docs/`,
`scripts/`, `.github/`, `Makefile`, `docker-compose.yml`, `.env.example`, `data/README.md`
and the `ROSTERLAB_*` reports. No `.db`, `.env`, `.pem`, snapshot HTML or raw dataset is
tracked. `docs/qa/` (98 screenshots × 6 runs) is gitignored.

## 6. Blocked work, with the measurement that blocks it

### R2b — contract import

**R2b's acceptance criterion is `teams_with_complete_payroll ≥ 27/30`. The best available
artifact yields 0/30.** Measured, not predicted, on a scratch copy of the development
database:

```
matched                                       886 rows
  exact_name 867 · suffix_insensitive 10 · unaccented 9
unmatched                                     154 rows
ambiguous                                       0 rows
seasons present                     2026-27 … 2031-32   (cap league year present ✓)
roster players with a 2026-27 salary      392 / 530     (74.0 %)
teams with a computable payroll             0 / 30
```

This is not a matching failure — the join works, and the snapshot does carry the league
year that governs trade legality. It is coverage: 138 rostered players (26 %) have no
2026-27 salary in an offseason Basketball-Reference snapshot, overwhelmingly because their
deals expired. `_team_payroll` is all-or-nothing by design, so one missing player removes
a whole team. The plan's sensitivity table put 20 % missing at 0/30; at 26 % the
measurement lands where it said it would.

Shipping R2b on this artifact would produce a release whose gate cannot pass and whose
headline — "salary matching now works" — would be false for all 30 teams.

### Not started

R2c, R3, R4, R5, R6, R7. R3 is the critical path and depends only on R1, which is
complete.

## 7. Missing datasets and their exact expected paths

| Dataset | Expected path | What it unblocks | Required tables |
| --- | --- | --- | --- |
| Kaggle `wyattowalsh/basketball` (`nbadb`) | `data/external/` (also `KAGGLE_DATA_DIR`; consumed by `backend/app/integrations/kaggle_nba/importer.py`, run by `make import-kaggle`) | R6's lineup-aware fit, and any tracking/play-type/matchup work | lineup and on/off tables, play-type and shot-profile tables |
| A fuller contract artifact | `data/contracts/contracts.csv`, with `CONTRACT_DATA_PROVIDER=file` | R2b as specified (§6) | `nba_player_id`, `salary`, `season`, plus `signed_date`, `no_trade_clause`, `contract_type` — the three fields that per C8 otherwise keep `overall_status` pinned at `conditionally_valid` at *any* BBRef coverage level |

Nothing in R0, R1, R2a, R2c, R3, R4 or R5 is blocked by the Kaggle dataset.

## 8. Migrations and data changes

`b1a7c93f4e02` — de-duplicate `model_versions`, add `UNIQUE(model_name, version)`.
Verified on a clean database, on a copy of the development database (9 rows over 6
distinct pairs → 6 rows; 1,536 estimates → 1,024), and applied to the development database
after a backup. Estimates belonging to dropped version rows are **deleted, not
re-pointed**: rows sharing a version string came from different training runs and carry
different numbers, so re-pointing would merge two models' outputs under one identity.

Development-database changes (each backed up first, backups in the session scratchpad):
the migration above, and `make purge-fixtures APPLY=1` removing 2 scenarios, 21 trade
proposals and 1 comparison set by name, plus 49 comparison sets left dangling by the
proposal deletions.

## 9. Modelling and calibration evidence

**R1 changed no model, and that was its gate.** The evidence is a baseline-vs-now
comparison run from a `git worktree` at `f16dedc`, using the same interpreter against the
same database file, over four fixed trades. The sharpest is a fully-modelled 2-for-2,
where R1 has no licence to move anything:

| Field | Before | After | Verdict |
| --- | --- | --- | --- |
| `fit` | 84.59 / 32.22 | 84.59 / 32.22 | **identical** |
| `assets` | 50.0 / 50.0 | 50.0 / 50.0 | **identical** |
| `timeline` | 83.14 / 16.86 | 83.14 / 16.86 | **identical** |
| `contract` | null | null | **identical** |
| `performance` | 52.80 / 47.06 | 53.10 / 46.84 | R1-4 |
| `risk` (LAL) | 33.08 | 33.23 | R1-5 |

Both movements are accounted for by name: `performance` moves because the *roster* still
contains unmodelled players (BOS carries three) that R1-4 removes from the 240-minute
allocation instead of giving `tei = 0.0` and 12 baseline minutes; `risk` moves because
`_roster_cards` gained an `ORDER BY` and the seeded Monte Carlo was order-sensitive. That
sensitivity was then removed in R2a — each player now draws from a stream keyed on
identity — and a parametrized test proves order-independence.

**No new metric was fitted, and none was presented in a measured unit.** R3 owns the
calibration; the plan's key finding (ridge TEI explains R² = 0.004 of team net rating
against the transparent index's 0.624) is untouched and remains the single most important
piece of work outstanding.

## 10. Deviations from the plan

Full detail sits in each release report. The ones that changed what shipped:

1. **`make seed-demo` was pulled forward from R1-7 into R0** — the CI Playwright gate
   could not run without a database. Team identity comes from `nba_api`'s bundled *static*
   table (offline); everything else is synthetic, stamped `source_provider="demo_seed"`,
   and the seeder refuses to run where `nba_api` rows exist.
2. **The coverage floor of 68 required raising coverage first.** The plan's "measured
   68 %" is the rounded display; the precise baseline was 67.74 %, so the floor fails at
   `f16dedc`. Covered the new seeding code rather than lowering the floor.
3. **`scripts/visual_qa.mjs` could not run at all** — ESM resolves bare specifiers from the
   importing file's directory, and there is no `node_modules` at the repo root. Fixed as a
   prerequisite for giving it an exit code.
4. **`fit` is withheld when one side of a deal is empty**, rather than scored against a
   fabricated 50th-percentile player. Inventing a replacement percentile would be a
   modelling change inside the release whose gate is "no modelled number moved for the
   wrong reason". R5 introduces a measured baseline; the loss is disclosed meanwhile.
5. **The phantom-move check only fires when the player is on some current roster.** A
   player on no roster is an unknown-roster case; refusing it would block every offseason
   signing — a larger defect than the one being fixed.
6. **zod is used, narrowly, rather than deleted.** Schemas cover only the responses that
   carry decision numbers, with `.passthrough()`. It caught a real error in its own schema
   within minutes, as an end-to-end failure rather than an `undefined` on screen.
   `react-hook-form` and `@hookform/resolvers` had zero imports and were removed.
7. **Two defects outside any release's scope were fixed where they were found**: `make
   score` crashed on any second run (pre-existing, reproduced at `f16dedc`), and the Monte
   Carlo depended on player order.
8. **R2b's go/no-go was measured rather than deferred.** The plan lists two unknowns that
   "cannot be resolved without the artifact"; the artifact is in the repository, so they
   were resolved on a scratch database copy.

## 11. Remaining risks

- **The impact metric is unchanged and remains the largest credibility risk.** Ridge TEI
  explains R² = 0.004 of team net rating; everything downstream inherits that. R3-1.
- **`performance` has almost no variance** (sd 1.27, ~1.2 % of composite variance), so the
  roster-gut score is still ≈ 50 on the modelling path even though the legality gate now
  stops the headline. R3-3.
- **Salary matching is still unavailable product-wide.** §6.
- **`fit` is withheld on every one-way deal** until R5 supplies a replacement baseline.
- **`ingestion/jobs.py` is 222 statements at 0 % coverage** — the pipeline that writes the
  `DataSyncRun` rows behind the freshness fix. R5.
- **The defensive proxy is unchanged**: `perimeter_defense = pct(stl_per_min)` still puts
  Luka Dončić at the 84.5th percentile for point-of-attack defense. R4-2.

## 12. Exact recommended next action

**Run R2c — the disclosed-coverage payroll model — before R2b, inverting the plan's
order.** The plan gates R2c on "only after R2b proves the join works"; §6 proves it (886
bound, 0 ambiguous, 74 % roster coverage, cap league year present). With a disclosed
coverage model the same snapshot becomes useful for 30 teams instead of 0, and the missing
26 % is stated rather than hidden — which is the entire point of the release.

Concretely, resuming from a fresh session:

```bash
git checkout feat/rosterlab-autonomous-roadmap
cd "nba front office command center prod"
make contract-coverage        # the 0/30 baseline this release has to beat
```

Then replace `_team_payroll`'s all-or-nothing return with a payroll plus its coverage —
`(payroll_of_known, players_known, roster_size)` — and thread that disclosure through
`TeamContext.payroll_before/after`, the salary rules (which must stay `unavailable` rather
than compute a matching verdict from a partial payroll), and the UI, so a figure is never
rendered without "computed from 16 of 18 contracts; 2 unknown" beside it. The acceptance
test is that a team with one unknown salary shows a payroll *and* its coverage, and that
`SALARY_MATCHING` still reports `unavailable` for that team.

If R2c is not wanted, **R3 is the critical path** and depends only on R1, which is
complete: promote the transparent index over the ridge (R3-1) before attempting any
calibration, since fitting on ridge TEI yields a coefficient indistinguishable from zero
and would be misdiagnosed as a bug in the calibration rather than in the metric.
