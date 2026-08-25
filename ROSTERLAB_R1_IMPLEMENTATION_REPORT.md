# R1 — Correctness and honesty

**Branch:** `feat/rosterlab-autonomous-roadmap` · **Base:** `f16dedc` · **After R0:** `af236d0`
**Goal:** every displayed number is correct or explicitly unavailable.

---

## 1. Scope completed

| Item | Commit | What changed |
| --- | --- | --- |
| **R1-3** legality gate, composite `None` semantics, weights, driver reconciliation | `c101d56` | QA-1, QA-5, QA-8, three C13 findings |
| **R1-4** no defaults rendered as measurements | `da1e2d4` | `tei`/`availability`/`minutes`/`tei_sigma` optional; `pct()`; `fit.py` |
| **R1-2** trade construction validation | `402baab` | QA-2, QA-3, QA-7, QA-13, `?format=` |
| **R1-5** rotation chart | `18df54a` | QA-6 |
| **R1-1** freshness attribution | `682e672` | QA-4 + timezone, empty-vs-derived, issue totals |
| **R1-6** + **R1-8** Team Outlook state, generator hidden | `58a4c6b` | QA-9, QA-10 disclosure |
| **R1-9** labels, confidence, hygiene, the zod decision | `433677d` | QA-12, `-0.0`, C13 ×3, model versions, security |
| **R1-7** test-data isolation | `ae07f71` | fixture purge, dropdown identity |
| **R1-D** documentation | this commit | `limitations.md`, `methodology.md`, stale-doc banners, screenshots |

All pushed to `origin/feat/rosterlab-autonomous-roadmap`.

## 2. Before and after, measured on the live database

| Finding | Before | After |
| --- | --- | --- |
| **QA-1** BOS sends all 16 players to LAL | `composite_utility 72.85`, confidence medium, assets 82.0, verdict *"Proceed with further diligence"* | `composite_utility null`, `decision_status suppressed_illegal`, ROSTER_SIZE named with the 12-man minimum |
| **QA-2** LAL player sent *from* BOS | HTTP 200, LAL scored **61.67 / +0.45 wins** for acquiring its own player | 422 *"these players are not on the roster they are being traded from: Deandre Ayton"* |
| **QA-3** identical move listed twice | HTTP 200, player counted twice | 422 *"the same player appears in more than one move: Jayson Tatum"* |
| **QA-4** `/data-health` | *"Current NBA data ✓ fresh · updated Jul 27, 2026, 1:45 AM"*, nav 🟢 "Live data" | **stale**, last update **Jul 21 02:04**, nav "Data aging", 7 stale tables listed |
| **QA-5** empty trade | composite 46.36, `prob_positive 0.0` | composite **50.0**, `prob_positive null` |
| **QA-6** Giddey ↔ Curry chart | *"Giddey 20.4 → 0.0; **Jalen Smith 0.0 → 12.4**"*, Curry absent | Curry present at **+24.2**, Jalen Smith −0.1, both lists minutes-sorted |
| **QA-7** `strategy: "win_now_lol"` | HTTP 200, silently different weights | 422 naming the seven valid values |
| **QA-8** report, no incoming players | *"Historical availability of incoming players: **85 %**"* | line absent; `incoming_availability: null` |
| **QA-9** Atlanta Team Outlook | "Defensive rebounding 67th" under **both** Strengths and Needs | Strengths only; explicit *"No pressing needs"* |
| **QA-11** `EFF` | 2146.0 in the per-game view | *unchanged — deferred to R7 (needs a third field category, C12)* |
| **QA-12** verdict labels | 46 → "High-risk upside", 52 → "Mixed outcome" | 46 → "Net negative", 52 → "Roughly neutral" |
| **QA-13** `draft_year: 2034` | `"[{'type': 'less_than_equal', 'loc': (…), 'ctx': {'le': 2033}}]"` | `"pick_moves[0].draft_year: Input should be less than or equal to 2033"` |
| **C13** driver reconciliation | utility − 50 = 7.06 vs summed drivers 4.94 | **1.31 vs 1.31** |
| **C13** `tei = 0.0` for 43 unmodelled players | rendered as a measurement at the 63rd percentile | `null`, players named, confidence low |
| **C13** open quality issues | 50 shown, total unknowable | **562** total, per-check breakdown, "512 further … not listed" |
| **C13** `model_versions` | `v202607210204` ×3 per model, 9 rows / 6 distinct | content hashes, 6 rows / 6 distinct, `UNIQUE(model_name, version)` |
| **C13** superseded estimates | 1,536 rows, +512 per train, never collected | GC on every train; migration removed the 512 the de-dup orphaned |
| **C13** test entities in the dev DB | 22 trades, 16 scenarios, 50 comparison sets, undisclosed | purged, `make purge-fixtures`, documented in `data/README.md` |
| **W8/QA-10** generator coverage | ~21 % claimed | **13.8 %** stated in `docs/limitations.md` and in every response's `coverage` block |

## 3. Release gate

### ☑ CI green; every R0 xfail that R1 owns has flipped

```
pytest -q --cov=app --cov-report=term --cov-fail-under=68
179 passed, 3 xfailed, 1 warning
TOTAL   4643   1297   72%      Required coverage of 68% reached: 72.07%

ruff check app tests   → All checks passed!
mypy app               → Success: no issues found in 78 source files
alembic upgrade head && alembic check → No new upgrade operations detected.
```

Frontend: `36 passed`, lint clean, `tsc --noEmit` clean, `npm run build` succeeds.
End to end, on the CI path (`make e2e`, dedicated demo database): **5 passed**.
Visual QA: **98 screenshots**, 14 routes × 7 viewports — *CLEAN: no horizontal overflow,
no console errors, no empty pages*, exit 0.

**20 of the 23 R0 pins have flipped.** The three that remain are correctly deferred:

| Pin | Why it is still xfail |
| --- | --- |
| roster-gut `performance < 25` | Unreachable before R3-3. C12 measured the audit's own P0-4 prescription at 50.1–55.0 because `risk` is untouched; the number only moves with the calibration. |
| MC median = point estimate | R3-5. The two paths use different models by construction (C2). |
| `EFF` classification | R7. C12: moving it to `_TOTAL_FIELDS` switches it to `_required_float` and starts rejecting rows with a blank value — it needs a third category. |

### ☑ No rendered value derives from an undisclosed default

`tests/unit/test_no_silent_defaults.py` (11 tests) asserts it two ways: behaviourally (a
missing column omits the skill; no skill is constant across the population) and
structurally (an AST scan for the five literals that produced the audit's findings —
0.5, 0.75, 12.0, 0.85, 1.5 — with a self-test proving the scan can fire).

### ☑ Three fixed trades differ from `f16dedc` only in fields R1 deliberately changed

Run against a copy of the live database from a `git worktree` at `f16dedc`, using the
same interpreter and the same database file. Four cases; the fourth is the sharp one,
because every player on both sides is modelled and R1 therefore has no licence to move
anything.

**Case 4 — fully-modelled 2-for-2, BOS ↔ LAL:**

| Field | Before | After | Verdict |
| --- | --- | --- | --- |
| `fit` | 84.59 / 32.22 | 84.59 / 32.22 | **identical** |
| `assets` | 50.0 / 50.0 | 50.0 / 50.0 | **identical** |
| `timeline` | 83.14 / 16.86 | 83.14 / 16.86 | **identical** |
| `contract` | null | null | **identical** |
| `performance` | 52.80 / 47.06 | 53.10 / 46.84 | R1-4 |
| `delta_net_rating` | +0.25 / −0.26 | +0.28 / −0.28 | R1-4 |
| `risk` (LAL) | 33.08 | 33.23 | R1-5 |
| `decision_status` | absent | `scored` | R1-3, new field |
| `has_unmodeled_players` | absent | `true` | R1-4, new field |

Both movements are accounted for:

- **`performance` and `delta_net_rating` move because the *roster* still contains
  unmodelled players**, even though the deal does not. BOS carries three. R1-4 removes
  them from the 240-minute allocation instead of giving them `tei = 0.0` and 12 baseline
  minutes, so the remaining minutes redistribute. This is the deliberate judgment the
  plan specifies for R1-4 — exclude from *impact*, keep in the *roster count*, and say
  so — and it is disclosed on every response and on screen.
- **`risk` moves through `prob_positive` (0.2125 → 0.2150) because the player order
  changed**: `outgoing_tei` went from `[1.11, 3.49]` to `[3.49, 1.11]`. `_roster_cards`
  had no `ORDER BY` (R1-5), so it returned whatever the database produced;
  `simulate_delta_wins` draws sequentially from a seeded RNG, so order shifts the draws.
  The order is now deterministic, so this is a one-time shift into a stable state. It
  also shows the Monte Carlo is order-sensitive under a fixed seed — noted for R3-5,
  which rewrites it.

Cases 1–3 move more, and every movement traces to the same two mechanisms plus the
intended `fit` withholding: `fit: 100.0 → null` on a deal whose outgoing side is a
single unmodelled player with no skill vector, and `outgoing_tei: 0.0 → null` for that
player. `assets` and `contract` never moved in any case.

**Gate result: pass.** No modelled number moved for a reason outside R1's stated scope.

## 4. Deviations from the plan

| # | Deviation | Why |
| --- | --- | --- |
| D1 | QA-8 landed in the R1-3 commit, not R1-4 | The availability default and the `prob_positive` default are the same expression in `_risk`. A strict xfail must flip in the same commit as its fix. |
| D2 | `fit` is **withheld** when one side is empty, rather than scored against a replacement baseline | The plan says to remove the 0.5; it does not say what replaces it. Inventing a replacement percentile in R1 would be a modelling change in the release whose gate is "no modelled number changes for the wrong reason". R5 introduces a measured baseline; until then the component is excluded and disclosed. Information is lost, and the loss is visible. |
| D3 | The phantom-move check only fires when the player is on *some* current roster | A player on no roster is an unknown-roster case, not a phantom move. Refusing it would block every offseason signing, which is a larger defect than the one being fixed. |
| D4 | `_risk` was restructured into weighted terms rather than patched twice | Two independent defaults (`prob_positive` 0.5, `avail_in` 0.85) in one expression. Dropping unmeasurable terms and renormalizing reuses the composite's own contract instead of inventing a second one. |
| D5 | The e2e full-flow assertion was widened | The deal it builds is now *correctly* refused when the counterparty already carries 18 players. It accepts either a verdict or the refusal, and requires the refusal to name its rule. |
| D6 | The candidate generator gained a `coverage` block and deterministic ordering | The plan says hide it and correct the docs. It stays reachable by API, so leaving it silent about a 13.8 % sweep would have left the defect live for any API consumer. |
| D7 | zod is **used**, narrowly, rather than deleted | The plan required a decision. Schemas cover only the responses that carry decision numbers, with `.passthrough()` so additive changes never break the client. It caught a real error in its own schema within minutes (a suppressed evaluation returns `uncertainty: {}`), surfacing as an end-to-end failure rather than an `undefined` on screen. `react-hook-form` and `@hookform/resolvers` had zero imports and were removed. |
| D8 | `purge_fixtures` also repairs comparison sets | Deleting a proposal leaves comparison sets pointing at nothing, and the comparison then fails as a whole. Found by running the purge against the real development database: 49 sets were left dangling before the repair existed. |
| D9 | `docs/demo-script.md` and `docs/rosterlab-enhancement-plan.md` got banners, not rewrites | R7 owns the rewrite. A document that does not run is less harmful when it says so. |

## 5. Database and migration changes

`b1a7c93f4e02` — de-duplicate `model_versions`, add `UNIQUE(model_name, version)`.

Verified three ways: clean database (`alembic upgrade head` then `alembic check` →
"No new upgrade operations detected"), a copy of the development database (9 rows over 6
distinct pairs → 6 rows; 1,536 estimates → 1,024), and the development database itself
after a backup.

Estimates belonging to dropped version rows are **deleted, not re-pointed**: rows sharing
a version string came from different training runs and carry different numbers, so
re-pointing would merge two models' outputs under one identity. Nothing reachable was
lost — only the active version is ever read.

## 6. Known limitations after R1

- **The impact metric is unchanged.** R1 changed no model. The ridge's R² = 0.004 against
  team net rating is R3-1's problem, and everything downstream of it still inherits that.
- **`performance` has almost no variance** (sd 1.27, ~1.2 % of composite variance). The
  legality gate stops the worst headline, but the roster-gut `performance` score is still
  ~50 because the units are wrong. R3-3.
- **`fit` is withheld on every one-way deal** until R5 provides a measured replacement
  baseline.
- **Salary matching is still unavailable** — `contracts` is 0 rows. R2.
- **The Monte Carlo is order-sensitive under a fixed seed.** Now deterministic because the
  order is, but the underlying fragility remains until R3-5 rewrites the draw.
- **`ingestion/jobs.py` is still 0 % covered** — the pipeline that writes the `DataSyncRun`
  rows behind the freshness fix. R5.

## 7. Next eligible release

**R2a — performance and instrumentation.** It requires no contract data, and the
measured baseline to beat is `/trades/generate` at **21,112 queries / 2.55 s** and a
2-for-2 evaluate at **60 queries**.
