# Wave 2 overnight maintenance — 2026-10-30 (executed 2026-11-02)

Status vocabulary: **Confirmed** (reproduced or read in code) · **Implemented** · **Tested** · **Suspected** · **Proposed**. Nothing here is "validated" in the model sense. Nothing was pushed or merged.

## 1. Starting state and safety checks

| Item | Observed |
|---|---|
| `/Users/arjunvedere/pivot-work` | **Not** a git repo. The repo is `pivot-work/pivot`, checked out on `feat/r8-canonical-data-foundation` (`5cada84`, one untracked `docs/r8.zip`). `e0b7363` is **not** its ancestor, so that checkout was left alone (audit-only per the brief). |
| Wave 2 worktree | `/Users/arjunvedere/pivot-maint-w2-worktree`, `maint/application-integrity-w2`, HEAD `664c4b297a5a`, `status --porcelain` empty, no stash, no lock files; `e0b7363` is an ancestor; 12 commits `e0b7363..664c4b2`. |
| Other worktrees | 11 total. Dirty (untouched): `pivot` (R8, 1 untracked), `pivot-r8-2-worktree` (1), `pivot-r9-1-worktree` (1). Live processes: uvicorn from the R8 checkout and `next dev -p 3093` from the R9.3A worktree (owner preview). Nothing but this session used the Wave 2 worktree. |
| Disk | ≈11 GiB free at the end (was 12). |
| Backup | Bundle of `664c4b2` exists (`~/pivot-backups/git/pivot-maint-application-integrity-w2-664c4b2-2026-10-22.bundle`, per W2.8). **The two new commits are not in any bundle.** |
| New branch | `maint/wave2-correctness-overnight` from `664c4b2`, in a **new worktree** `/Users/arjunvedere/pivot-wave2-overnight-worktree` (the existing Wave 2 worktree was not switched or modified). |

The brief's "last known state" (Oct 21) was stale: Wave 2 stages W2.1–W2.7 had already been implemented locally on Oct 21–22.

## 2. Audit of Issues A–E (at `664c4b2`)

| Issue | Status at `664c4b2` | Evidence | Residual |
|---|---|---|---|
| **A** unsafe train/score instructions | **Fixed** by `345cd6d` | No `make train`/`make score` text remains in `backend/app`, `frontend/app|components|lib` (`git grep`). README line 111 and 165–175 frame them as disposable-DB/destructive. | In-app hints still say `make seed-config` (`cba/builder.py:31`, `ingestion/quality.py:320`), `make sync-data`, `make refresh`. These are not training/scoring; `sync-data` is a network call. Low; owner decision (also noted in `W2_CLOSEOUT_REVIEW.md` §7). |
| **B** trade validation-before-commit | **Fixed** for `POST /trades` by `54ec97f` (`flush` not `commit`; 11 tests in `test_trade_create_atomicity.py`) | `trades.py:create_trade` | **Two siblings were not covered — see §3.** |
| **C** cap-parameter season | **Fixed** by `f2410e6` for the quality check. All other cap lookups already key on `settings.cap_league_year`; no request-level season parameter exists, so "requested season" is the configured cap year. `cap_params_row` returns `None` for a missing year with no fallback. | `git grep LeagueCapParameters`, `cba/resolver.py:83` | The cap year is a config value (`CAP_LEAGUE_YEAR`, default `2026-27`); it does not roll over automatically. Not a defect, but a pinned-default risk. |
| **D** evaluator integrity | **Fixed** by `dae97c9` (response schemas) and `f5f2ee0`…`664c4b2` (stale-state hook, reveal ownership, rules-check failure notice). 646 frontend tests passed at the tip per `W2_9_VERIFICATION_HANDOFF.md` (not re-run by me). | Handoffs | Page never mounted in a browser. Saved-trade responses validated only by `tradeDetailSchema`. `adopt()` has no caller. Deferred by the owner. |
| **E** TEI "VALIDATED" | **Fixed** by `594d8fa` (`Confidence.HEURISTIC`). Formula untouched. README and `docs/limitations.md` already say "interpretable heuristic". | `services/intelligence.py`, README line 72 | `main` and the R-lineage branches still carry `VALIDATED` until this lands. `docs/resume-bullets.md:48` says "validated impact modeling" (a doc, not product UI). |

## 3. New defects found and fixed

### Fix 1 — `a77c7b5` `fix(comparisons): validate before committing a comparison`
- **Confirmed (red run `red1`).** `POST /comparisons` committed the `ComparisonSet` before `get_comparison` evaluated the trades. If that raised (cap parameters gone → 409), the comparison stayed. Also, an unknown `scenario_id` returned **201**, was stored, and was silently replaced by default "custom" weights on read.
- **Change:** `backend/app/api/v1/comparisons.py` — unknown scenario → 404 `scenario <id> not found` (same wording as the trade endpoints); `flush` instead of `commit`; build the response; one `commit` after.
- **Tests:** `backend/tests/integration/test_comparison_create_atomicity.py` (4): valid create persists and reads back identically; unknown scenario → 404 and no row; unknown trade → 404 and no row (control, passed before too); evaluation rejected (cap rows deleted) → 409 and no row.
- **Severity:** medium. **Confidence:** high.

### Fix 2 — `5ec78ce` `fix(scenarios): reject an unknown focal team before saving the scenario`
- **Confirmed (probe + red run).** `POST /scenarios` with an unknown `focal_team_id` returned **500** after committing 1 scenario and 6 weight rows; `GET /scenarios` then returned **500** for every later request (`_scenario_out` reads `focal_team.abbreviation`). On SQLite (which does not enforce FKs here) this corrupts the list endpoint. PostgreSQL would raise an FK error instead; not exercised.
- **Change:** `backend/app/api/v1/scenarios.py` — 404 `team <id> not found` before anything is added.
- **Tests:** `backend/tests/integration/test_scenario_create_validation.py` (2): unknown team → 404, no scenario/weight rows, later `GET /scenarios` still 200; valid scenario creates, lists and reports its weights.
- **Severity:** medium-high for a dev SQLite database. **Confidence:** high.

A third fix was not made: the remaining candidates (saved-evaluation validation, `adopt()` cleanup, `make seed-config` wording) are owner-deferred product or wording decisions, not demonstrated correctness defects.

## 4. Tests executed

All backend runs went through a guarded launcher (`env -i`, in-memory `DATABASE_URL`, `python -I -B`, imports asserted to resolve inside the new worktree, per-test file-backed SQLite under pytest `tmp_path`). The launcher and logs live in the session scratchpad (non-durable): `…/scratchpad/w2o/`.

| Run | Result |
|---|---|
| `test_trade_create_atomicity.py` (baseline, harness check) | 11 passed |
| New comparison tests, **before fix** (`red1`) | 3 failed, 1 passed — two real defects, one my own wrong response key (corrected) |
| New scenario tests, **before fix** (`red2`) | 1 failed (500), 1 passed |
| Comparison + scenario + trade-atomicity + `test_api.py` after fixes (`green3`) | **38 passed** |
| `test_api.py` + `test_fixture_isolation.py` | 27 passed |
| `ruff check`, `ruff format --check` on the four touched files; `mypy app/api/v1/comparisons.py` | clean |
| Full `tests/integration`, new branch (`integ2`) | 148 passed, 14 skipped, **4 failed** |
| Full `tests/integration`, unmodified tip `664c4b2` (`integ_tip`, read-only run) | 142 passed, 14 skipped, **the same 4 failed** |

**The 4 failures are pre-existing, not caused by these commits** (identical set at `664c4b2`): three in `test_r8_cross_tool_consistency.py::TestToolsStayConsistentAcrossTheSeasonRollover` (`test_the_traded_player_is_on_one_team_everywhere_and_keeps_last_seasons_line`, `test_the_rookie_is_a_member_with_no_history`, `test_before_the_stats_flip_the_roster_is_already_2026_27_and_the_statistics_are_not`) and `test_r93a_round4_regressions.py::test_an_older_schema_does_not_turn_cap_outlook_into_a_500`. CI passed the whole suite on 2026-10-24, so these are **suspected** to depend on today's date (2026-11-02, a day before the documented 2026-11-03 stats rollover) or on the launcher's pinned `CURRENT_SEASON`/`ROSTER_SEASON`/`CAP_LEAGUE_YEAR`. I did not investigate further; the cause is **unconfirmed**.

## 5. Not executed, and why
- Frontend tests: no frontend file changed. The tip's 646-pass result is from `W2_9`, not re-run.
- `next build`, browser or preview smoke tests: the only running previews serve owner data; no isolated preview was available.
- PostgreSQL tests (`test_postgres_compat.py`): require a test DB URL that was deliberately unset.
- Full unit suite and CI-equivalent run: not run (≈15 min on CI, storage and time); the changed code is covered by the targeted runs above.
- No training, scoring, ingestion, GOAT/BALLDONTLIE/NBA calls, or database access outside `tmp_path` SQLite files.

## 6. Behaviour and compatibility
- `POST /comparisons` with a non-existent `scenario_id`: **201 → 404** (`not_found`). Previously stored a dangling reference and used default weights silently.
- `POST /comparisons` whose trades cannot be evaluated: now returns the same error as before but **no longer leaves a row**.
- `POST /scenarios` with an unknown team: **500 → 404** (`not_found`), nothing stored.
- Valid requests, response shapes and all numerics are unchanged. No analytical output changed.
- Existing databases may already contain a scenario with a dangling `focal_team_id` created by the old bug; the fix does not repair it (and I did not touch any real database). `GET /scenarios` would still 500 on such a database.

## 7. Local commits (branch `maint/wave2-correctness-overnight`, parent `664c4b2`)
- `a77c7b5` fix(comparisons): validate before committing a comparison
- `5ec78ce` fix(scenarios): reject an unknown focal team before saving the scenario
- (this report, committed separately)

## 8. Known issues remaining
- Deferred (owner): saved-trade/saved-evaluation response validation and whether `?load=` should load stored evaluations; `adopt()` removal; `make seed-config`/`sync-data` hints in app messages.
- Not verified in a real browser: the evaluator page, failure notice and reveal behaviour.
- `docs/resume-bullets.md` uses "validated impact modeling".
- Legacy `fillna(0.0)` in `analytics/impact.py` and `analytics/features.py` (flagged in CLAUDE.md; reported, not changed).
- 4 integration tests fail under the guarded launcher at today's date, at `664c4b2` and on this branch alike (see §4); cause unconfirmed.
- Wave 2 is **not** declared complete: the page was never mounted, no browser/build run, nothing published, and the two new commits have no bundle.

## 9. Thesis data-readiness (read-only; no model built)

**Verified capabilities** are from code and docs; I did not query any database.

1. **Lineup/stint observations: no.** `docs/limitations.md` ("Lineup-aware fit is deferred, on measurement") records that `LeagueDashLineups` returns real groups but five-man samples are noise (median 20 min; implied sd ≈ 16 per 100). `make lineup-availability` reads sample sizes and stores nothing. There is no stint table.
2. **Ten players on court: no.** BALLDONTLIE/GOAT `/lineups` returns **starting fives, not combinations** (`docs/r8-1/balldontlie-trial-readiness.md`, `docs/r8-3/data-coverage-matrix.md`; observed on 2 games). `/plays` was sampled on 1 game (~595 plays) and substitutions-to-stints reconstruction has not been attempted or verified.
3. **Possessions and margin:** game scores exist (`games.home_score/away_score` via `ingestion/jobs.py:sync_games`, NBA.com `LeagueGameLog`). Possession counts could be constructed from box-score totals, but no per-stint possessions exist. `PlayerGameStats` is a schema only; nothing writes it (`git grep`).
4. **Coverage:** season-level player/team stats over about ten seasons; completed-trade corpus 2016-17…2025-26. Game-level history exists only as the Kaggle `nbadb`, whose play-by-play **ends 2023-06-12**, before the seasons Pivot models. GOAT history samples reach back to 1995 per the executive report but are sampled, not ingested.
5. **Risks:** season alignment across separate roster/stats/contract clocks (CLAUDE.md §4); the rollover checkpoint 2026-11-03; present-state fields (`is_active`, position) leaking into history; box-score-only data cannot support adjusted plus-minus; five-man noise; the circularity R4-2 withdrew a claim over.
6. **Reproducible without uncontrolled API use:** partly. The BALLDONTLIE adapter caches under `data/imports/` and has an evaluation plan (13 probes), but lineups/plays/advanced endpoints are GOAT-restricted and metered. No retained play-by-play corpus exists locally.
7. **To build clean train/validation/test sets:** a game-level event or substitution source covering the target seasons, a stint constructor with an audit (ten players, period/clock continuity, score deltas reconcile to final scores), a possession definition, and season-forward splits using the existing as-of discipline.
8. **Reusable safely:** `modeling/panel.py` (`AsOfPanel`, `LeakageError`), `modeling/backtest.py` rolling-origin folds and the leakage audit, `modeling/registry.py` and `contract.py` (candidate ≠ validated), the preregistered holdout protocol (`docs/r9-1/`), `modeling/metrics.py`/`intervals.py`. Not reusable as a starting point: the retired player-level ridge in `analytics/impact.py` (documented as a volume metric with no team-level validity).
9. **Smallest next data-readiness task:** a read-only feasibility audit of one stint source for **one past season**: fetch (or locate, within an approved request budget) play-by-play with substitutions for ~20 games, build stints offline in a scratch directory, and report the fraction whose ten-player set and score delta reconcile to the box score. This answers #2 and #3 empirically before any data is ingested.
10. **Owner decisions before coding:** possession definition and weighting; handling of garbage time, overtime, and end-of-period stints; how to treat players with few possessions (penalty scaling, minimum exposure); season boundaries and whether multi-season pooling or priors are allowed; target (margin per 100 possessions vs per possession); how a one-player substitution difference is defined and what uncertainty is reported; the held-out period and whether the existing holdout ledger applies; permitted data sources and API budget; licensing of NBA.com-derived aggregates (already flagged open).

## 10. Recommended next engineering task
Run the **full backend suite and `tsc`/Vitest** against `maint/wave2-correctness-overnight` once, in the guarded launcher or CI after the owner authorises a push, then bundle the branch. If the owner wants one further correctness change, add a read-time guard so `GET /scenarios` tolerates (or the app reports) a pre-existing dangling-team scenario.

## 11. Items needing owner approval
- Pushing/merging the Wave 2 branch (and this one); a bundle of `maint/wave2-correctness-overnight`.
- Whether to reword the remaining `make seed-config` / `make sync-data` in-app hints.
- Checking or repairing any existing real database for scenarios with unknown `focal_team_id` (this session touched no real database).
- The thesis decisions in §9.10 and any API-budget use for the stint feasibility audit.

## 12. How to verify before merging
```bash
cd /Users/arjunvedere/pivot-wave2-overnight-worktree
git log --oneline 664c4b2..HEAD
git diff 664c4b2..HEAD --stat
git diff 664c4b2..HEAD -- backend/app
```
Then run the three new/related test modules against a disposable in-memory config (not an application database): `tests/integration/test_comparison_create_atomicity.py`, `test_scenario_create_validation.py`, `test_trade_create_atomicity.py`.
