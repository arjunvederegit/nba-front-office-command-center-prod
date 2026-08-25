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
| Backend tests | **114 passed**, 1 warning, 4.32 s (now **908 passed / 1 skipped / 0 xfailed** at `a76cff3`) |
| Backend coverage (`--cov=app`) | **68 %** (4263 statements, 1375 missed); now **88.46 %**, floor 85 |
| Frontend unit tests | **15 passed** (2 files); now **82 passed** (9 files) |
| `data/external/` | **does not exist** — the Kaggle `nbadb` dataset is NOT present. A copy on this machine (`~/Downloads/nbadatabase/nba.sqlite`) ends **2023-06-12**, before the first modelled season, so it cannot serve R6's lineup question either. |

## Datasets present (inspected)

| Path | Bytes | Nature |
| --- | --- | --- |
| `data/cba/nba_cap_parameters.yml` | ~4 K | Cap/tax/apron/MLE 2026-27 (**confirmed**, NBA Communications) → 2032-33 (estimates/projections, SalarySwish). Carries an explicit `status` per season. |
| `data/imports/contracts/players.html` | 454 K | Basketball-Reference contracts snapshot, saved 2026-07-28 |
| `data/imports/draft_picks/realgm_future_drafts.html` | 291 K | RealGM "NBA Future Drafts Detailed", page datetime 2026-07-28 00:49:32. **Consumed by `make import-draft-picks` since R5**: 394 entries → 92 verified picks, 103 unresolved, 0 unparsed, 0 unmatched team names. |
| `data/imports/nba_player_stats_2026.csv` | 820 K (dir) | 2025-26 season totals, already wired to `make import-stats-csv` |
| `data/imports/transactions/NBA_<year>_transactions.html` | ~3.9 M (10 files) | Basketball-Reference season transaction pages, 2016-17 … 2025-26, fetched by `make fetch-transactions` (3.5 s apart, honouring the source's published `Crawl-delay: 3`). Gitignored. **Consumed by `make import-transactions` since R6**: 565 trades, 2,568 asset legs, 1,341/1,500 player legs resolved, 0 unparsed trades, 0 unresolved franchise abbreviations. `provenance.json` beside them records URL + SHA-256 + retrieval time per page. |
| `data/external/` | — | **absent — Kaggle `nbadb` unavailable** |

**Since R7, `player_season_stats` holds ten seasons** (2016-17 … 2025-26), ingested by
`make sync-corpus-stats` — 11,307 rows, **0 unresolved identities**, plus standings and ten
`season_calendar` rows. This is the **corpus** window (`CORPUS_SEASONS`), not the modelling
window (`HISTORY_SEASONS`), which is still 2023-24 … 2025-26.

---

## Current position

**Releases complete:** R0, R1, R2a, **R2c**, **R2b** (feasible scope), **R3**, **R4**, **R5**,
**R5.5** (the rotation allocator), **R6** (differentiation), **R7** (hardening and close-out).
**The RosterLab generation is complete.** See `ROSTERLAB_FINAL_R1_R7_HANDOFF.md` for the
canonical closing document and `ROSTERLAB_R7_IMPLEMENTATION_REPORT.md` for this release.

**R2b's original gate was invalid and has been replaced** — see "R2b gate, reassessed".
**Three of R4-2's four acceptance criteria were also invalid and have been replaced** —
see "R4-2 gate, reassessed".
**One R6 comparable-trade criterion was replaced too** — see "R6 mirror criterion,
reassessed".
**R7 withdrew `perturbation_stability` as a gate** — both nulls pass it, and the
random-hash null scores a perfect 1.0000. See "R7 — the criterion two nulls passed".

**Next:** nothing in RosterLab. The next product generation ("Pivot") starts from
`ROSTERLAB_FINAL_R1_R7_HANDOFF.md`, whose closing section states the boundary.

**Status:** working tree clean, pushed through `a76cff3`. Backend **908 passed / 1 skipped /
0 xfailed**, coverage **88.46 %** (floor 85). Frontend **82 passed** (9 files); eslint, `tsc`
and the production build (13 routes) clean. Migrations apply, reverse to base and re-apply on
a fresh database, and `alembic check` reports no drift. Playwright **6 passed** (including a
new database-identity guard); visual QA **105 shots clean** in `docs/qa/r7/`. Adversarial
battery **11 of 11**; both R6 batteries pass. **All 23 QA findings are closed and no strict
xfail remains.**

### The R3 gate survived a full retrain on ten seasons, bit-for-bit

R7 widened `player_season_stats` from three seasons to ten for the comparable-trade corpus.
The served window frame is byte-identical (632 rows x 33 columns, same hash) on a season frame
that grows from 1,714 rows to 5,483. A full `make train` reproduced **every model's content
hash** — `0c89cb6a46a8`, `c621d2abcc85`, `131594164c5d`, `7f98efcb3a6e` — so the registered
artifacts are byte-identical, not merely equivalent. (A fifth model, `pick_value_curve`, is
newly active because the RealGM snapshot had never been imported here; `make
import-draft-picks` reproduces R5's figures exactly at 92 verified of 394.)

`CORPUS_SEASONS` and `HISTORY_SEASONS` are separate settings, and
`test_corpus_window_isolation.py` pins the three structural reasons rather than the numbers.

### R7 found a live look-ahead in the comparable corpus

`feature_season_for` decided a trade's feature season from the calendar **month**, and was
wrong for **57 of 565 trades (10.1 %)** — November 2020 (the season began 22 December),
draft-night June 2024 (filed under the season about to start), and early-October preseason.
`is_in_season`, a scored feature, was wrong on 163. The June-2024 group was inside the
three-season window R6 shipped, so this was live rather than latent.

`season_calendar` now holds each season's first and last regular-season game, from
`LeagueGameLog`. With no calendar ingested the month rule still answers and
`coverage.calendar_backed` reports `false`.

### R7 — the criterion two nulls passed

Widening the corpus took `perturbation_stability` from 0.6479 to 0.5949 against a 0.60 gate.
Investigating condemned the criterion, not the release:

- **It is a statistic about corpus size.** 0.707 / 0.676 / 0.651 / 0.611 at n = 200 / 337 /
  600 / 1,151 on random subsamples of one corpus. Subsampling the ten-season corpus back to
  337 sides reproduces the three-season number (0.651 vs 0.648).
- **Both nulls pass it.** Random-hash null **1.0000**, shuffled-feature null 0.6181, shipped
  distance 0.6110. A ranking keyed only on identity cannot move when its features do.

Replaced by the same wobble read by **rank**: the unperturbed top five must still average
inside the top ten of the perturbed ranking. Measured **4.33** against a ceiling of 10, and
stable in n (4.72 at 200 vs 5.32 at 1,151).

R7 also separated **validity** criteria (which the nulls must fail) from **robustness**
criteria (which a zero-information ranking trivially passes). Applying R4-2's rule literally
to every check would have deleted half the battery.

### `make e2e` was testing the wrong database

Playwright's `reuseExistingServer` defaulted to true, so the target seeded a dedicated demo
database and then attached to whatever uvicorn a developer had running. Every test passed
while this happened. Reuse is now opt-in and `guards.spec.ts` measures which database is under
test. If e2e fixtures appear in the dev database again, that guard is the thing that broke.

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
| **data** — committed the cap-parameter reference set | `c2dcab0` | `data/cba/nba_cap_parameters.yml` + README; 5 tests pin status/source/agreement with the seeded YAML |
| **QA find** — provider factory thread-safe and file-backed | `627f151` | `/teams/{id}/payroll` 500 under concurrent load with a provider configured; `base.py` breaks the cycle; a missing file no longer counts as configured |
| **R2c** — disclosed-coverage payroll | `3d85c59` | teams showing a payroll **0/30 → 30/30**; teams verifying one 0/30 → 0/30 (unchanged by design); 23 new tests |
| **R2b** — contract-activation honesty | `3cc0fbc` | `contract_type` NULL not "standard"; ROSTER_SIZE **(warning, medium) on all 30 teams**; 7 rule codes not 5; salary cell renders real numbers; allowance scales with the cap |
| **R3** — impact units and calibration | `c103812` `8f943cf` | ridge retired (team R² 0.0039 vs index 0.7505); train/serve scale unified (r 0.387 → 0.911); conversion fitted at **14.977** (t 9.80, n 60); roster-gut **56.4 → ≤ 14.7** on all 30; performance sd **1.27 → 18.2** |
| **R4-1a** — fit scores each skill once | `27729db` | 19 of 30 teams had a skill claimed by ≥2 active needs; inflation mean **1.625×**, max **2.67×** |
| **R4-1b** — turnover avoidance measured, not mapped to assists | `77cb7fb` | corr(assist pct, turnover avoidance) **−0.255**; 10 of top 12 by assist rate below median; their mean **0.285** |
| **R4-1e** — R4 inputs reach the served frame; cache deploy hazard fixed | `ed068f8` | 27 columns were being dropped by the collapse; two-stage shrinkage sd **0.676 vs 0.398**; skills cache key now fingerprints the skill contract |
| **R4-1c/1d/2** — four measured skills replace two shared ones | `20986d7` | `team_defense` stability **0.838** vs steals 0.669; A″ team-quality share **0.99** vs 1.51; FG3 shrinkage k=**300** from three agreeing estimators |
| **R4-2** — point-of-attack claim withdrawn | `2bda9f8` | its class check came out **0.630 / 75 %** against the steals proxy's 0.611 / 70 % — worse than what it replaced |
| **R4-3** — deterministic size-first roles replace k-means | `4e88bdf` | label churn under a 10 % drop **65.7 % → 1.77 %**; 14/14 roles fire; 217 numeric suffixes → **0**; 49 fabricated heights → labelled |
| **R4-4** — continuous curves, self-excluded percentiles, capped rotations | `f495271` | age-30 cliff **0.70 TEI → <0.02**; percentile ceiling **96.7 → 100.0**; allocator returned **39.14** minutes against a 36 cap |
| **R4-2** — weights re-justified by construct; UI vocabulary named | `969d2c2` | `TS_PCT`, with no defensive content, beats `DREB_PCT` on every criterion — so the criteria cannot select weights |
| **R4-4** — one rotation depth | `a89d655` | three cutoffs (9 / 10 / 12) reduced to one claim plus one display constant |
| **R5-1a** — components squashed, not truncated | `fd3b45e` | fit ties **106 of 440 → 2**; contract 16 → 0; timeline 20 → 0; no scale constant changed (unit derivative at 50) |
| **R5-1b** — performance taken back out of risk | `3f257f8` | corr(risk, performance) **0.851 → −0.022**; risk available 480 → **482 of 482**; legality-exposure term built, measured (0.063 ± 0.071, ceiling 0.143) and left unscored |
| **R5-2** — empirical pick valuation + verified ownership | `0ec2bab` | curve LOCO **0.4624** (8/8 classes, t 15.36) but **+0.0405 vs round-only, p = 0.22**; first-round gradient **0.3277, p = 0.0023**; 394 entries → **92 verified picks, 103 unresolved, 0 unparsed** |
| **R5-1c** — assets prices draft capital | `269664e` | 3 distinct values → **23**; payroll term built, measured at **0.837 corr with contract**, and removed |
| **R5-3** — generator rebuilt | `46c9520` | coverage **13.8 % → 100 %**; counterparty above neutral **2 of 40 → all**; both-above-50 has a **9.5 % base rate** over 241 random trades |
| **R5-4** — perf and unbounded growth | `57bd580` | collapse **1.045 s → 0.045 s** (exact to 9.1e-13); generate **2.34 s → 1.03 s at 7× the coverage**; issue table upserted + pruned |
| **R5-5** — modelling / ingestion / CLI coverage | `ae38ac1` | jobs.py **0 → 77 %**, train.py 36 → **97 %**, cli.py **0 → 92 %**, total 78 → **88 %**; found and fixed a `KeyError` crash in `calibrate_wins_per_net_rating` |
| **R5-6** — Pareto axes and falsified copy | `bef6a94` | domination judged on all six components, `axes_compared` published |
| **R5.5-1** — a departure's minutes are a replacement's | `bef1d66` | above-replacement removals scored as gains **191 of 370 → 0**; rotation players (≥15 mpg) **152 → 0**; MEM strip-best-3 **−3.73 → −6.03 wins**; QA-1 **32.15 → 23.06** |
| **R5.5-2** — one-way `fit` baseline, measured | `457f3eb` | `REPLACEMENT_SKILLS` on n=187; scoring **0.391** (t −5.99) vs rebounding **0.528**; spread 0.136 against a 0.031 level shift; two-sided deals untouched (baseline `None` ×240) |
| **R5.5-3** — the property pinned through the service | `9efe8d7` | the defect was in calling the allocator twice, so an allocator-only test would have passed throughout |
| **R6-1** — ten seasons of completed trades ingested | `e2a3a03` | 565 trades / 2,568 asset legs / **0 unparsed trades**; 1,341 of 1,500 player legs resolved (89.4 %); conveyance 580 unconditional / 194 swap / 44 protected / 41 conditional |
| **R6-2** — comparable-trade retrieval | `9b82540` `623134f` | archetype precision@5 **0.797** vs a 0.414 base rate (random null 0.397, shuffled-feature null 0.405); direction confusion **0.019**; best single-dimension null 0.089 |
| **R6-3** — need-driven acquisition | `eb5e718` | distinct players across the league's top fives **26 → 72** once each candidate is run through the trade evaluator; shuffled-need null changes 84 % of a list |
| **R6-4** — rotation shape; lineup fit deferred on measurement | `3a7b16e` | five-man median group **20.2 minutes**, implied sd **16.1** net-rating points per 100 against a ±10 league spread |
| **R6-5** — the decision memo | `d83ef29` | eight entries in "What is not known" on a live deal, every one of which existed before and none of which was collected anywhere |
| **R6-UI** — precedent, rotation consequences, targets, memo | `553d0d0` | 98 visual-QA shots clean; three defects found by driving it (duplicate sides, "3th percentile", a deep link built to a private encoding) |
| **R6-perf** — the league role reference batched | `e6a0d00` | cold `/trades/evaluate` **37 → 8** queries for one team; the budget file now asserts the shape, not a number |

| **R7-1** — a trade is described by a season that had been played | `313d7a9` | 57 of 565 trades were look-ahead; `season_calendar` from `LeagueGameLog`, 10 rows |
| **R7-2** — the corpus widened to ten seasons | `6a2d3d6` | 337 → **1,151** rankable sides, 154 → **535** trades; R3 bit-identical, served window byte-identical |
| **R7-3** — a criterion two nulls passed, withdrawn | `ff2bdbd` | random-hash null **1.0000** vs the shipped 0.6110; replaced by rank displacement 4.33 (ceiling 10) |
| **R7-4** — the battery made runnable again | `6d12bd6` | >10 min (killed) → **68 s** at 3.4× the corpus; caught a seam that would have measured nothing |
| **R7-5** — QA-11, the last strict xfail | `d79ceb5` | `EFF` moved to a third field category; the pin itself queried a `stat_type` that never existed |
| **R7-6** — percentiles over a population that supports them | `f09cf97` | 67 players at exactly 0 %/100 % from three were pinning both ends of the scale |
| **R7-7** — cross-tab favourite team | `fcb64ce` | `storage` listener, guarded storage access, stable snapshot identity |
| **R7-8** — a failed search no longer reads as an empty one | `7041894` | `construction_errors` typed, counted and published |
| **R7-9** — precedent states the coverage it has | `8508445` | `trades_rankable` 535, not `trades_ingested` 565; `calendar_backed` surfaced |
| **R7-10** — the seventh data-health source | `2d9ad5c` | the Precedent panel traced to a source the provenance page did not list |
| **R7-11** — unambiguous scenario labels, agreeing counts | `a38691b` | 16 identical dropdown options; `lib/teamTheme.ts` deleted as dead |
| **R7-12** — documentation and the rename | `90743ce` | 11 docs; About missing 3 shipped tools; demo script rewritten against the running product |
| **R7-13** — the 2,964-line page, and e2e isolation | `f589907` | 2,964 → 2,375 LOC; `make e2e` had been testing the developer's database |
| **R7-14** — the adversarial battery, committed | `a28d7c8` | 11 scenarios; writing it found three checks that could not fail |
| **R7-15** — cache invalidation on any ingestion | `f9c8e38` | `bump_data_version` moved into `sync_run`; every non-`sync_all` path had been serving stale skills |
| **R7-16** — the memo claimed the corpus, not the coverage | `a76cff3` | "565 completed trades" where 535 are rankable, on the artifact a front office reviews offline |

Remaining xfail pins: **0** (23 of 23 flipped)
- QA-11 `EFF` classification flipped in R7 (`d79ceb5`), with the third field category C12
  required. The pin itself was also wrong — it queried `stat_type == "csv_totals"`, which the
  importer has never written.

Flipped in R3: QA-1 roster-gut `performance < 25` (R3-3) and C2/R3-5 Monte-Carlo /
point-estimate agreement (R3-5).

## Commits

```
a76cff3 fix(memo): the decision memo claimed the corpus, not the coverage
748d572 docs: close the RosterLab generation — R7 report and the R1-R7 handoff
f9c8e38 fix(cache): invalidate on any ingestion, not only on a full sync
a28d7c8 test(adversarial): commit the hostile-trade battery R6 ran by hand
f589907 refactor(trade-evaluator): lift the evaluation tabs out of a 2,964-line page
90743ce docs: rename the product, and correct what R5-R7 made false
a38691b fix(ui): make a scenario option unambiguous, and a count agree with its noun
2d9ad5c fix(data-health): list the completed-trade corpus, which a screen already traces to
8508445 fix(precedent): state the coverage the retrieval has, not the corpus it was given
7041894 fix(search): a search that could not run must not read as a search that found nothing
fcb64ce fix(favorites): a team chosen in one tab reaches the others
f09cf97 fix(player-explorer): a percentile needs a population that can support it
d79ceb5 fix(stats): EFF is a season total, not a rate — QA-11, the last strict xfail
6d12bd6 perf(comparables): rank on the distance alone, and compute a side's vector once
ff2bdbd fix(validation): withdraw a criterion two nulls pass, and gate the rank instead
6a2d3d6 feat(comparables): widen the corpus to ten seasons, behind the R3 gate
313d7a9 fix(comparables): describe a trade by the season that had actually been played
0669f42 docs: record R6 — differentiation, and the two claims it refused to make
623134f fix(comparables): a protected first is not the same asset as an unconditional one
ae9e1cb docs: record what R6 measured, and what it refused
e6a0d00 perf(evaluation): load the league's rosters once, not once per team
553d0d0 feat(ui): put precedent, rotation consequences and the memo in front of a user
d83ef29 feat(memo): turn the report into a decision artifact a front office can review
3a7b16e feat(roster-shape): report what a trade does to the rotation, and defer the lineup model
eb5e718 feat(acquisition): start from the need, and end at a trade you can evaluate
9b82540 feat(comparables): retrieve the completed trades a proposal actually resembles
e2a3a03 feat(transactions): ingest ten seasons of completed trades as evidence
4f3bdf0 docs: record R5.5 — the rotation allocator, and the two changes it did not make
9efe8d7 test(evaluation): pin the giveaway property through the service, not just the allocator
457f3eb feat(fit): score one-way deals against a measured replacement, not a constant
bef1d66 fix(projection): charge a departure's minutes to a replacement, not to the roster
f217710 docs: record R5 — the decision-engine release, and what it measured before changing anything
57c3edd fix(ui): restore a lost space and soften a panel that quoted a release number
bef6a94 fix(comparisons): judge domination on every shared axis, and correct the copy R5 falsified
ae38ac1 test: cover the modelling, ingestion and operational paths, and ratchet the floor
57bd580 perf: vectorise the window collapse, skip the unread simulation, bound the issue table
46c9520 feat(candidates): search the whole league, and refuse the deals the composite permits
269664e feat(assets): price draft capital empirically, and stop scoring salary twice
0ec2bab feat(picks): empirical pick valuation and verified ownership, with the precision it refuses
3f257f8 fix(evaluation): take performance back out of risk
fd3b45e fix(evaluation): squash unbounded components instead of truncating them
296a568 test: add post-R4 R3 calibration gate
a89d655 refactor(rotation): one definition of rotation depth, and name the display cutoff
969d2c2 fix(r4): justify the defensive weights by construct, and name the new vocabulary in the UI
4e88bdf feat(roles): replace k-means archetypes with a deterministic size-first chain
f495271 fix(analytics): continuous age curves, self-excluded percentiles, capped rotations
2bda9f8 fix(skills): withdraw the point-of-attack claim rather than restate it wrongly
20986d7 feat(skills): split the shared defence and shooting skills into measured ones
ed068f8 feat(features): plumb the R4 skill inputs into the served window frame
4febfbf style(tests): satisfy ruff C420 in the fit aggregation fixture
77cb7fb fix(skills): measure turnover avoidance instead of mapping it to assists
27729db fix(fit): score each skill once, not once per need that claims it
6fd719e docs: final report for the R2c / R2b / R3 run
8f943cf fix(methodology): keep the band formula out of a paragraph
c103812 feat(analytics): put team impact in net-rating points, fitted not assumed
d63c463 docs(state): record R2c, R2b, and the gate that had to be replaced
3cc0fbc fix(cba): stop asserting contract types no provider reports
3d85c59 feat(cba): disclose partial payroll coverage instead of withholding payroll
627f151 fix(contracts): make the provider factory thread-safe and file-backed
c2dcab0 data(cba): commit the league-wide cap parameter reference set
5d7ab52 docs: R2a release report and the autonomous run's final report
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
5. **(resolved in R5.5) `fit` was withheld when one side of a deal is empty** rather than
   scored against a fabricated 50th-percentile player. R1 deferred the measured baseline to
   R5; R5 deferred it again, because it changes a scored component and no measurement had
   been taken of what it does to the fit distribution. **R5.5 took both measurements.**
   `REPLACEMENT_SKILLS` (n = 187, players outside their team's top ten) is the arriving
   baseline when nothing arrives; the roster's own minutes-weighted profile is the departing
   baseline when nothing departs — R5-1b's `risk` construction, applied to skills. The two
   differ for the same reason the allocator's two directions differ. Two-sided deals are
   untouched (baseline `None` on all 240 sampled).
6. **The phantom-move check only fires when the player is on some current roster.** A
   player on no roster is an unknown-roster case, not a phantom move; refusing it would
   block every offseason signing.
7. **The e2e full-flow assertion was widened**, because the deal it builds is now
   *correctly* refused when the counterparty already carries 18 players. It accepts either
   a fan verdict or the explicit refusal, and requires the refusal to name its rule.

## R2b gate, reassessed after R2c

The plan's R2b gate required **`teams_with_complete_payroll ≥ 27/30`**. That criterion is
**invalid** and has been replaced. It is not that the release failed it — it is that the
criterion does not test the release.

**Why it is invalid.** A complete payroll needs a salary for *every* rostered player, so
the metric is a cliff, not a slope: the plan's own sensitivity table puts 20 % missing at
0/30. The Basketball-Reference offseason snapshot misses 26 % — 138 of 530 rostered
players, almost all expired deals. 27/30 is therefore unreachable from this artifact at
**any** quality of implementation, and reaching it would require a different dataset, not
different code. A gate that no correct implementation can pass measures the data, not the
work, and blocks every downstream release behind an acquisition nobody has scheduled.

**What replaced it.** Six criteria, each measured against the real import (401 contracts
bound from 886 rows, 0 ambiguous):

| # | Criterion | Measured | Verdict |
| --- | --- | --- | --- |
| 1 | `cap_league_year_present_in_snapshot`, or the import fails loudly | 2026-27 present (of 2026-27 … 2031-32) | ✅ |
| 2 | `teams_with_disclosable_payroll ≥ 27/30` — the display-side successor | **30/30** | ✅ |
| 3 | `teams_with_complete_payroll` **reported, not gated** | 0/30, cause named per team | ✅ reported |
| 4 | Zero ambiguous bindings, or each named | 0 ambiguous; 842 unmatched rows filed as warnings | ✅ |
| 5 | **`ROSTER_SIZE` stays `(warning, medium)`** — a `(pass, high)` is a failed acceptance | (warning, medium) on all 30 | ✅ |
| 6 | `rule_results` stops shrinking from 9 to 5 | **7 codes** on a 1-for-1 | ✅ |
| 7 | The salary cell renders a real number | Vučević $2,449,421 · 1 yr | ✅ |
| 8 | A knowingly-illegal deal returns `verified_illegal` with figures | 21-man roster → `verified_illegal`, ROSTER_SIZE names the 18-spot ceiling | ✅ |
| 9 | `overall_status` is never `verified_legal` on BBRef-shaped data | `conditionally_valid` | ✅ |

Criterion 3 is the substantive change: the number is still computed, still published and
still gates every *verdict*; it simply no longer gates the *release*. Criteria 5, 6 and 9
are new, and all three assert that something did **not** improve — they are what stops the
release being declared a success on falsified fields.

**What R2b did not achieve, measured.** The audit's headline — "trades move from Incomplete
check to real verdicts" — is unreachable through this provider, exactly as C8 predicted.
Of 401 imported contracts: `contract_type` NULL ×401, `signed_date` NULL ×401,
`no_trade_clause` NULL ×401. Those three fields are why `overall_status` stays
`conditionally_valid`, and no implementation quality changes that. A hand-curated CSV at
`data/contracts/contracts.csv` with `CONTRACT_DATA_PROVIDER=file` unlocks `verified_legal`
for the teams it covers; nothing else does.

Two consequences worth stating plainly:

- **R2c's refutation path needs real contract types.** A lower-bound payroll can prove a
  second-apron aggregation illegal, but only once the rule can establish that the deal
  aggregates at all — which needs types. Under BBRef-only data the rule correctly reports
  `unavailable` before reaching it. The path is unit-tested with typed fixtures.
- **Salary-matching violations are not refutable under BBRef data.** With types unknown the
  matching sum is withheld, so an illegal deal fails on roster rules or not at all.

## R4-2 gate, reassessed

The plan's R4-2 criteria were **A′** (team-aggregate rank correlation must beat the steals
proxy), **A″** (decile gap in on-court `DEF_RATING` ≥ 3.0), **A‴** (weights committed
before any named-player check) and **B** (Dončić's percentile below 0.50).

**Three of the four are invalid**, by the same test the R2b gate was replaced under: they
do not test the release. Every criterion was re-run against three published nulls — a
*placebo* scoring each player by his own team's rating (zero player information), a
*circular* metric (−player `DEF_RATING`), and deterministic *noise*:

| Criterion | Gate | Placebo scores | Verdict |
| --- | --- | --- | --- |
| A′ | beat −0.374 | **−1.000** | INVALID |
| A″ | ≥ 3.0 | **10.97**, 99 % of it team quality | INVALID |
| change-on-change (the supporting design) | — | **R² 0.904** | INVALID |
| A‴ | procedural | cannot be gamed by data | **VALID, kept verbatim** |
| B | Dončić < 0.50 | — | INVALID as a gate |

A′ is additionally degenerate by construction for a demeaned quantity: possessions are
charged to five on-court players, so the possession-weighted roster mean of on-court
`DEF_RATING` **is** the team rating, and aggregation destroys 94.7 % of the dispersion. Its
sign flips (+0.342 vs −0.292) depending only on whether the baseline includes the player,
for a quantity that is the same to r = 0.998.

**B is self-contradictory with A‴.** B publishes a threshold on a named player, so its
weight implication is knowable before any weight is chosen — which means satisfying B *is*
selecting weights using a named player, which A‴ forbids. B is also unstable: Dončić's
within-season percentile on the prescribed metric ranges 0.243 → 0.908 across the three
seasons, so the gate flips on window choice with no code change.

**What replaced them.** A‴ unchanged. A′, A″ and B become **reported, never gated**, each
published alongside all three nulls. The gates are:

| # | Criterion | Baseline to beat | Measured | |
| --- | --- | --- | --- | --- |
| 1 | Stability — year-over-year percentile correlation, ≥1000 min both seasons (n=391) | steals **0.669** | **0.838** | ✅ |
| 2 | Incremental validity — partial rank correlation with next-season differential, controlling for its own persistence | steals **0.106**, null floor ~0.090 | **0.126** | ✅ |
| 3 | A″'s **team component** must not exceed the steals proxy's | **1.51** | **0.99** | ✅ |
| 4 | Every criterion run against three nulls; any criterion a null passes is inadmissible | — | A′/A″/CoC all inadmissible, and reported as such | ✅ |
| 5 | Pre-registered class check, no named players — high-usage, high-assist, sub-6′8″, ≥1500 window minutes | steals **0.611 / 70 %** | **withdrawn**, see below | — |

**Criterion 5 failed and the response was to withdraw the claim, not reweight.** The
point-of-attack composite scored **0.630 mean / 75 % above median** on its own class
against the steals proxy's 0.611 / 70 % — worse than the thing it replaced. A steals-led
composite necessarily rates ball-dominant guards highly. `point_of_attack_defense` is gone
from `SKILL_KEYS` and `NEED_TO_SKILL`; the team-side need is still measured and displayed,
with the reason no player skill claims to address it.

**And the criteria cannot select the weights either.** Holding the shipped vector fixed and
swapping only the 0.22 term for `TS_PCT` — an offensive statistic with no defensive content
— beats `DREB_PCT` on *every* non-circular criterion (A′ −0.542 vs −0.499, partial t −2.58
vs −1.84). So the weights are justified by **construct** — every term is a defensive act —
and the measured table above establishes only that the composite is not worse than the
proxy it replaced. `docs/limitations.md` and `features.py` both say so.

**What R4-2 did not achieve, measured.** No defensive metric here is validated. Every
target available in this repository derives from on-court `DEF_RATING`, so every test is
circular to some degree, and on the one genuinely non-circular question — do the 100
players who changed team improve their new team's defensive rating — every candidate's
confidence interval crosses zero. Honest validation needs the matchup and tracking data
deferred to R6.

## Active blockers

### (resolved) R2b — its original acceptance criterion could not be met

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

The **join works** — 886 rows bound, zero ambiguous, and the snapshot carries the league
year that governs trade legality. The gap was coverage: 138 rostered players (26 %) have
no 2026-27 salary in an offseason snapshot, mostly expired deals, and payroll was
all-or-nothing so one missing player removed a whole team. The plan's sensitivity table
put 20 % missing at 0/30; at 26 % it landed where predicted.

**Resolved by R2c**, which made the same snapshot useful for 30 teams instead of 0 without
loosening a single verdict. The unreachable criterion was replaced rather than waived —
see "R2b gate, reassessed" above. A hand-curated CSV at `data/contracts/contracts.csv`
with `CONTRACT_DATA_PROVIDER=file` remains the only route to `verified_legal`, because it
is the only source that carries `signed_date`, `no_trade_clause` and `contract_type`.

### (answered in R6) Kaggle `nbadb` absent — and it would not have helped

Expected at `data/external/` (also `KAGGLE_DATA_DIR`; consumed by
`backend/app/integrations/kaggle_nba/importer.py` via `make import-kaggle`). Still absent.

R6 measured what it was blocking, and the answer is that it was never the blocker. A copy
on this machine (`~/Downloads/nbadatabase/nba.sqlite`, 2.3 GB) holds no lineup or on/off
table at all, and its `play_by_play` **ends 2023-06-12** — before the first season this
product models. The real question was answered elsewhere; see "R6 — lineup-aware fit,
refused on measurement".

## R3 gate — re-measured on the POST-R5.5 path, 19 of 19 criteria met

Re-run in full after R5.5 rather than carried forward. Every calibration figure is
**bit-identical** to R3, R4 and R5, for a structural reason now worth stating: R5.5 changed
only the *counterfactual* path, `_team_tei_transitions` builds `d_tei` from
`player_season_stats` weighted by season minutes and **never calls `allocate_rotation`**,
and the level model that produces the served `before` allocation is untouched.

| Criterion | Gate | Post-R5.5 | At R5 |
| --- | --- | --- | --- |
| Coefficient | — | **14.976967** | 14.976967 |
| Slope significance | t > 5 | **9.802** | 9.802 |
| LOTO out-of-sample RMSE | < 4.5 | **2.944 / 3.773** | same |
| …as a share of predicting zero | < 75 % | **56.6 % / 65.0 %** | same |
| Per-fold slopes vs pooled | ±15 % | **14.716 / 15.276 (±2 %)** | same |
| Served constant matches the fit | ±2 % | **14.977 vs 14.977** | same |
| R² · n | — | **0.6236 · 60** | same |
| Roster-gut (whole roster) | < 25 on all 30 | **max 9.72**, 0 ≥ 25 | max 9.72 |
| **QA-1 strip the best three** | < 25 on all 30 | **max 23.06 (MEM)**, 0 ≥ 25 | **32.15 — over the line** |
| Distinct band widths | > 400 of 512 | **510 of 512** | 510 |
| Band width monotone in minutes | ρ < −0.95 | **−1.0000** | −1.0000 |
| Performance-component sd | > 8 | **18.489** | 14.744 |
| Performance boundary ties | 0 | **0 of 800** | 0 |
| Fit boundary ties | < 3 % | **0 of 800** | 2 of 440 |
| Above-replacement giveaway never gains | 0 violations | **0 of 370** | **191** |

Two band criteria are properties of the **player impact estimate**, not of the allocator —
"512" is the number of scored players and the quantity is `tei_high − tei_low` against
`total_minutes_window`. Measuring them against the simulated *outcome* interval, or against
last season's minutes rather than the window, reports spurious failures; both mistakes were
made and corrected while re-running this gate.

## R3 gate — re-measured on the POST-R4 database, all criteria met

Re-run after R4, because R4 changed the skill and feature path. Every figure below is from
the post-R4 code path; the R3-era values are in the right-hand column for comparison and
are identical wherever the quantity is the same one.

| Criterion | Gate | Post-R4 measured | At R3 |
| --- | --- | --- | --- |
| Coefficient | — | **14.976967** | 14.977 |
| Slope significance | t > 5 | **9.802** | 9.80 |
| LOTO out-of-sample RMSE | < 4.5 | **2.944 / 3.773** | same |
| …as a share of predicting zero | < 75 % | **56.6 % / 65.0 %** | same |
| Per-fold slopes vs pooled | ±15 % | **14.716 / 15.276 (±2 %)** | same |
| Served constant matches the registered fit | ±2 % | **14.977 vs 14.977** | — |
| Roster-gut performance component | < 25 on all 30 | **max 0.00, 0 teams ≥ 25** | max 14.70 |
| Distinct band widths | > 400 of 512 | **507 of 512** | same |
| Band width monotone in minutes | ρ < −0.95 | **−1.0000** | same |
| Performance-component sd | > 8 | **18.101** | 18.211 |

The coefficient is preserved **because the new measurement independently supports it**, not
because it passed before. It holds for a structural reason that is now asserted in
`test_r3_gate_after_r4.py`: R4 added columns to `MODEL_FEATURES` and derived new
post-collapse quantities but touched neither `INDEX_WEIGHTS` nor `Z_SOURCE_COLS`.

Feeding the new defensive term into TEI was tested and **rejected** — team-level R² 0.7505
(current) vs 0.5655 (replace the event trio), 0.7263 (add at 0.10), 0.6753 (add at 0.20).

A gap was closed on the way: `test_the_served_coefficient_matches_the_registered_fit`
**skips** when the database has no registered fit, which is every CI run, so the gate's
central assertion never executed. `test_r3_gate_after_r4.py` adds 15 tests that do not skip.

## R3 gate — as recorded at R3 (for reference)

| Criterion | Gate | Measured | |
| --- | --- | --- | --- |
| `tei_to_net_rating` registered with slope, SE, n, per-fold slopes, LOTO, construction | present | all present | ✅ |
| Slope significance | t > 5 | **9.80** | ✅ |
| LOTO out-of-sample RMSE | < 4.5 | 2.944 / **3.773** | ✅ |
| …as a share of predicting zero | < 75 % | 56.6 % / **65.0 %** | ✅ |
| Per-fold slopes vs pooled 14.977 | ±15 % | 14.716 / 15.276 (**±2 %**) | ✅ |
| Roster-gut performance | < 25 on all 30 | max **14.70**, 0 teams ≥ 25 | ✅ |
| Clamp binds on a realistic sample | < 5 % | **2.7 %** of 150 | ✅ |
| Performance-component sd | > 8 (was 1.27) | **18.211** | ✅ |
| Distinct band widths | > 400 of 512 | **507 of 512** | ✅ |
| Band width monotone in minutes | ρ < −0.95 | **−1.000** | ✅ |
| No literal ×5 on `team_tei_per_minute` | none | `PLAYERS_ON_COURT` deleted; test greps for it | ✅ |
| No doc/UI asserts "points per 100" unless b = 1.0 | none | 7 docs + the in-product page rewritten | ✅ |

## R6 mirror criterion, reassessed

The comparable-trade battery originally asserted that a side whose two directions are
genuinely different must resemble its own **mirror image** less than two unrelated sides
resemble each other. It failed when written, at 0.679 against a 0.672 median.

It was replaced **because it does not test retrieval**, not because it failed. Similarity
*levels* on this corpus compress into p05 0.521 … p95 0.873, so hundredths of level are not
evidence about a list — and the clearest proof is that the same statistic now reads 0.676
against a 0.685 median, i.e. it would pass, purely as a side effect of splitting first-round
picks by conveyance for an unrelated reason. A criterion that flips on a change made
elsewhere is not measuring what it claims to.

**What replaced it.** Direction confusion, on real corpus trades: of the top-5 neighbours
returned for a side that **sold** on-court value for first-round picks, at most 5 % may be
sides that **bought** it. Measured **1.9 %**. The mirror is still reported, by rank rather
than by level: injected into the corpus it is nearest for 2 of 141 asymmetric sides, top-five
for 11, median rank **89 of 338**.

## R6 — lineup-aware fit, refused on measurement

Not deferred on a schedule. `nba_api`'s `LeagueDashLineups` **is** reachable and returns real
five-man data; the samples are the problem. 2024-25 totals, top 2,000 groups by minutes:

| group size | median minutes | share ≥ 200 min | implied sd(net rating) |
| --- | --- | --- | --- |
| 2 | 376.9 | 88.4 % | 3.7 per 100 |
| 3 | 249.4 | 66.6 % | 4.6 per 100 |
| 5 | **20.2** | **1.6 %** | **16.1** per 100 |

16 points per 100 against a ±10 league spread, at the median of the *top* 2,000 groups. Two-
and three-man groups are estimable and still do not give a **trade** fit model: a trade
prices combinations that have never played together, so observed groups can only support a
synergy model, and nothing here holds a held-out target to validate one against — and any
target from on-court net rating is R4-2's circularity again.

Confirmations: the local Kaggle play-by-play ends 2023-06-12; Basketball-Reference's
`robots.txt` disallows `*/on-off/` and `*/lineups/`.

`make lineup-availability` re-runs it. **Do not re-open this without new data**, and if you
do, run that command first — the deferral is falsifiable by design.

## Six things R6 established that R7 must not undo

1. **The retrieval unit is a side, not a trade.** Direction lives on the asset. It is what
   made `direction_confusion` measurable at all, and a per-team representation cannot express
   a three-team trade where one franchise both sends and receives.
2. **Query and corpus sides are built by ONE function** (`services/comparables.py::_side`). A
   retrieval engine whose halves are constructed differently measures the construction.
   `test_query_and_corpus_sides_are_built_by_one_function` pins it.
3. **Counts carry a declared unit; only continuous quantities are scaled from the corpus.**
   295 of 337 sides receive no first-round pick, so the IQR is 0, the MAD is 0, and an
   estimated scale degenerates to the standard deviation — the statistic this module rejects.
4. **First-round picks are split by conveyance.** With a single `conditional_pick_share` a
   top-4 protection changed *nothing*: max 0.033 of distance against a corpus spanning 0.52
   to 0.87. R5-2 refuses to price a protected pick; the similarity must not treat it as the
   same asset.
5. **Salary, cash, trade exceptions and outcomes are never scored.** A feature the query can
   only answer "no" to penalizes the 37 % of completed trades that include one.
6. **`roster_shape` reads the allocation the projection produced.** Re-deriving it is R5.5-1's
   defect wearing a different hat.

## Exact next step

**None in RosterLab. The generation is complete.**

`ROSTERLAB_FINAL_R1_R7_HANDOFF.md` is the canonical closing document: final architecture,
data sources, analytical systems, workflows, CBA coverage, methodology, test status,
performance, limitations, deferred external dependencies, the lessons, what to preserve, what
to replace, and the exact repository state. Its closing section, "Foundation for Pivot",
states which systems are ready to be inputs to the next product generation **without designing
that generation**.

To verify this state from a clean checkout, follow §16 of the handoff.

Two items were deliberately **not** taken in R7 and are documented rather than dropped:

1. **Draft picks in a suggested acquisition package.** The valuation exists (R5-2) including
   its refusals; adding them is a feature change to a validated production path, and R7's
   objective was to finish rather than to add. This is the cleanest single piece of deferred
   work in the repository.
2. **The trade-evaluator board region** (~900 lines, coupled to the builder's drag state).
   The tab panels came out cleanly; this did not, and a close-out release is the wrong place
   to take that regression risk.

**Do not re-open the rotation allocator's level model without new data.** R5.5 measured
three alternatives out of sample over 60 team-season transitions and every one lost:
proportional-to-baseline **5.803** MAE against a depth-chart cascade at **8.641**, a soft
cascade at 8.367, `mpg × availability` at 6.437, and an equal-minutes null at **8.148**. A
fitted compression exponent chose the shipped value on all 30 leave-one-team-out folds.
`test_rotation_absorption.py::test_the_level_model_is_untouched_by_the_release` pins it.

The level model *is* still implausible in levels — ~13 players above 10 minutes against a
real ~10, and the best player at ~22 minutes against a real ~30. That is deviation 1 of the
R5.5 report and it is a **larger** change than it looks: the fix needs a *load*-shaped
estimand, which means separating a player's role from his availability throughout the
projection, and the R3 coefficient is fitted on the current meaning of `minutes`.

Six things R5.5 established that R6 must not undo:

1. **The after-roster is priced against the before-allocation**, never re-derived. Calling
   `allocate_rotation` independently on both rosters is the defect itself, and the allocator's
   own arithmetic was never wrong — so an allocator-only test cannot catch a regression here.
   `test_evaluation_sanity.py` guards the service path.
2. **A departure's minutes go unfilled, at `REPLACEMENT_TEI`.** The absorbers cannot be told
   apart from a replacement: outside a team's top ten the signal share of served TEI is
   **0.000** (spread 1.031, mean estimation sd 1.409) against **0.529** inside.
3. **Shedding stays proportional.** The two directions are genuinely asymmetric — gaining
   loses to a permutation of its own weights (4.081 vs 3.437), shedding beats every
   alternative (2.813 vs 3.375 uniform, t −7.49).
4. **Departures and arrivals have different thresholds, deliberately.** Losing anyone above
   replacement always hurts; gaining a free player only helps if he beats whom he displaces.
   A free below-average player making a good team slightly worse is correct, not a defect.
5. **One-way `fit` uses a measured profile, not a scalar.** The mean is 0.469 against the
   0.5 R1 removed, but the per-skill spread is 0.136 — the shape carries the information.
6. **`_team_tei_transitions` must never call `allocate_rotation`.** That independence is why
   every R3 figure survived this release bit-identical, and it is what makes the calibration
   robust to projection changes.

**Do not start R6 by re-tuning the composite.** R5 established that its components are now
distinct (max |r| 0.372, down from 0.864), that its ordering survived the release
(**0.9459** rank correlation before against after, mean absolute change 2.95 points), and
that its weakest link is the projection feeding `performance`, not the weighting on top.

Five things R5 established that R6 must not undo:

1. **`risk` must not read the outcome distribution.** It is not handed `uncertainty` any
   more, and `test_risk_orthogonality.py` asserts no executable line in `_risk` mentions
   `prob_positive`. Re-adding it restores a 0.86 correlation with `performance`.
2. **`assets` must not score salary.** Measured at 0.837 correlation with `contract`. The
   delta is reported with `payroll_scored: false` and the number that decided it.
3. **A conditional pick has no point estimate.** `precision` is `range` or `unknown`, and
   `test_pick_valuation.py` pins each refusal. A midpoint is how a protected pick acquires a
   false decimal.
4. **The pick curve does not beat a round-only rule** (+0.0405, p = 0.22). What is
   established is the gradient *inside* the first round (0.3277, p = 0.0023). The model
   version carries the failing diagnostic alongside the passing ones.
5. **No component may be truncated.** `bounded_score` has unit derivative at 50, so every
   documented scale constant still holds; truncation cost 106 of 440 fit scores their
   ordering.

## Push status

`origin/feat/rosterlab-autonomous-roadmap` is up to date through **`a76cff3`** (R7) plus the
R7 report, the R1–R7 handoff and this state file. `main` untouched; no history rewritten;
nothing force-pushed; no `git stash` used at any point.

**No raw dataset is committed.** The R7 diff adds one migration, one ingestion job, one
validation module, one component module, three small lib modules, tests and documentation.
Transaction snapshots, contract snapshots, databases and QA screenshots remain gitignored,
and `git ls-files` matches no `.db`, `.sqlite`, `.csv` or backup path.
