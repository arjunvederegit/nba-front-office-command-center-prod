# RosterLab R5 — Decision Engine

**Branch:** `feat/rosterlab-autonomous-roadmap` · **Base:** `296a568` (end of R4)

R5 found that four of the six evaluation components were not measuring what they claimed.
One was **85–94 % the same quantity as another**, one was a **placebo with three possible
values**, one **destroyed ordering information a quarter of the time**, and the candidate
generator surfaced deals its own model said would hurt the counterparty — **38 of 40** of
them.

Every one of those is a measurement, taken before anything was changed. The measurements
are in §1, and each fix is reported with the number that motivated it and the number it
produced.

Two things R5 built and then **removed after measuring them**: a legality-exposure risk
term (it is a property of the contract dataset, not of the deal) and a payroll term in
`assets` (it made `assets` 0.837-correlated with `contract` — a second double count in
place of the one just removed). Both are reported rather than buried, because a release
that only lists what worked is not a measurement report.

---

## 1. The baseline, measured before anything changed

800 evaluations — 400 two-team trades, both sides, five package shapes, all seven
strategies, deterministic seed — against the 30 ingested rosters at commit `296a568`.

| Component | n | missing | mean | sd | at 0 | at 100 | **tied at a boundary** |
| --- | --- | --- | --- | --- | --- | --- | --- |
| performance | 482 | 0 | 49.23 | 16.55 | 2 | 0 | 0.4 % |
| fit | 440 | 42 | 48.03 | 32.55 | 58 | 48 | **24.1 %** |
| contract *(no provider)* | 0 | 482 | — | — | — | — | never available |
| contract *(BBRef snapshot)* | 168 | 314 | 50.00 | 25.84 | 8 | 8 | 9.5 % |
| timeline | 482 | 0 | 48.18 | 22.96 | 12 | 8 | 4.1 % |
| assets | 482 | 0 | 50.00 | **1.16** | 0 | 0 | 0 % |
| risk | 480 | 2 | 55.36 | 23.09 | 1 | 1 | 0.4 % |

Correlations on the 440 evaluations where every non-contract component scored:

| pair | Pearson | Spearman |
| --- | --- | --- |
| **risk × performance** | **0.864** | **0.937** |
| prob_positive × performance | 0.921 | — |
| fit × performance | 0.263 | 0.291 |
| everything else | \|r\| < 0.19 | |

Share of composite variance: fit 0.347, performance 0.255, **risk 0.244**, timeline 0.161,
**assets −0.006**.

**Three defects, stated precisely.**

1. **`risk` was `performance` in a costume.** Its dominant term was `prob_positive`, the
   Monte Carlo's probability that Δwins > 0 — the performance projection restated as a
   probability. A quarter of the composite's variance came from a component 86–94 %
   identical to another, so `performance` carried roughly twice the weight the vector
   declared.
2. **`assets` was a placebo.** Three values, {48, 50, 52}, and a variance contribution of
   −0.006 while holding 15 % of the weight. Both informative inputs were structurally
   unavailable: picks were *counted* (8 points each regardless of which pick), and payroll
   came from `payroll_after − payroll_before`, which are `None` unless every rostered
   player is priced — 0 of 30 teams.
3. **Truncation destroyed ordering.** `max(0, min(100, x))` gave every deal past the
   boundary the same number. 106 of 440 fit scores carried no ordering information at all.

---

## 2. What changed

| # | Change | Commit |
| --- | --- | --- |
| R5-1a | Unbounded components squashed, not truncated | `fd3b45e` |
| R5-1b | `risk` becomes availability exposure; performance taken back out | `3f257f8` |
| R5-2 | Empirical pick valuation + verified ownership + Stepien certification | `0ec2bab` |
| R5-1c | `assets` prices draft capital; salary scored once, by `contract` | `269664e` |
| R5-3 | Candidate generator: whole-league search, mutual benefit, basketball checks | `46c9520` |
| R5-4 | Window collapse vectorised, simulation skipped where unread, issue table bounded | `57bd580` |
| R5-5 | Modelling / ingestion / CLI coverage; floor 68 → 85 | `ae38ac1` |
| R5-6 | Pareto axes; front-end copy R5 falsified | `bef6a94` |
| QA | Browser-QA fixes | `57c3edd` |

---

## 3. Component design, and the reasoning behind each

### 3.1 The scale contract (R5-1a)

Each component is on 0..100 with 50 neutral. Two kinds of quantity now map differently,
and the distinction is the point.

**Naturally bounded quantities map affinely and reach the endpoints.** Availability is a
share of games; a package of players who never miss a game really is the top of that scale.

**Unbounded quantities pass through a strictly monotone squash:**

```
bounded_score(x) = 50 + 50·tanh((x − 50)/50)      d/dx = 1 exactly at x = 50
```

Truncation was not a scale choice, it was an *information* choice. The unit derivative at
50 means **no scale constant anywhere in the engine changed** — 5 points per projected win,
×120 on raw fit, ×250 on cap-share surplus, 8 per reference pick all keep the slope their
documentation states. Only the saturating tail bends, and a +15-win deal stops scoring
identically to a +10-win one.

Measured on the same 800 evaluations: boundary ties fall from 106 to 2 for fit, and from
16, 20 and 2 to **zero** for contract, timeline and performance.

`float64` `tanh` saturates 900 linear points from neutral. That is 190 projected wins, a
raw fit of −7.5 against a measured range of ±0.42, or 3.6 whole salary caps of surplus;
`test_component_scale.py` asserts the bound against each component's real range rather than
claiming an open interval the arithmetic cannot keep.

### 3.2 `risk` — availability exposure, and only that (R5-1b)

```
R = 50 + 50·( a_in − a_out )        a = minutes-weighted availability of a package
```

Three choices are deliberate:

- **A change, not a level.** "Are these players durable" is not a question about the trade.
  "Is the team taking on more games-missed exposure than it is shedding" is.
- **Minutes-weighted.** Thirty minutes of a 60 %-available starter is more exposure than
  eight minutes of one.
- **An empty side is priced at the roster's own measured availability** — the minutes an
  arriving player does not play are played by the roster already there, and that roster's
  availability is a measurement this pipeline already makes. When even that is unmeasurable
  the component is withheld.

| | post-R4 | post-R5 |
| --- | --- | --- |
| corr(risk, performance) | 0.851 Pearson · 0.937 Spearman | **−0.022 · −0.048** |
| available on | 480 of 482 | **482 of 482** |
| sd | 23.09 | 12.80 |
| mean | 55.36 | **49.88** |

The mean moving to neutral is a correction, not a coincidence: the old component was an
availability *level* averaging 0.66, so it read as mildly positive on a deal that changed
nothing.

`prob_positive` is not lost — still computed, still returned under `uncertainty`, still
driving the displayed interval. It is simply not scored a second time. The removal is
pinned structurally, not by a correlation threshold: `_risk` is no longer *handed* the
uncertainty dict, and a test asserts no executable line in it mentions `prob_positive`.

**A legality-exposure term was built, measured and left unscored.** The share of
implemented CBA rules reaching a definite verdict runs **0.063 ± 0.071 with a ceiling of
0.143** across 482 evaluations, and what moves it is which contract fields the provider
supplies — a property of the dataset, not of the deal. Scoring it would have added a
near-constant offset, which is what `assets` already was. It is published on every
evaluation with `scored: false` and the measurement that decided it. **This is a deviation
from the plan**, which specified "availability and legality exposure only".

### 3.3 `assets` — draft capital, and salary scored once (R5-1c)

Picks are valued by the empirical curve (§4) rather than counted. The anchor is unchanged:
a mid-first-rounder is still worth 8 composite points and everything else is priced
relative to it. A pick the curve refuses to price — protected, swapped, or of unverified
ownership — is **not** midpointed into the score; it is listed with the range it would have
spanned and the component says it understates the package.

Measured on 92 pick-bearing evaluations built from the verified ownership rows: **23
distinct values** where the component had 3, sd 2.31, spanning 33.42–48.26, and what moves
it is *which* pick left rather than how many. Withheld on the 11 where the pick could not
be priced.

**The payroll term was built, measured and removed.** A first pass computed the delta from
the moved players' own salaries — exact whenever those players are priced, a far weaker
requirement than pricing two rosters, and available on 168 of 482 where the old
whole-roster route was available on 0. Scoring it made `assets` correlate **0.837** with
`contract` (0.779 Spearman), because with no pick moving both reduce to the same salary
delta. Removing one double count and introducing another is not progress. The delta is
reported with `payroll_scored: false`; `contract` divides salary by impact, which is the
question it asks.

The consequence is stated rather than hidden: **on a player-only trade `assets` is now
withheld** — 0 of 482 in the random sample, all 482 disclosed under `excluded_components`.
Without pick data there is no measurable asset content in a player-only deal that
`contract` does not already price.

### 3.4 What the weights do and do not control — reported, not engineered

Component spreads are not comparable, and there is no measurement that says one standard
deviation of fit is worth one of performance: they are in different units, and only
`performance` has a fitted conversion to a real-world quantity. The scale constants were
therefore **not** re-anchored to equalise them, and the consequence is published instead.
Post-R5, on the 168 evaluations where every remaining component scores:

| component | weight (`custom`) | variance share |
| --- | --- | --- |
| fit | 0.18 | 0.340 |
| contract | 0.14 | 0.276 |
| timeline | 0.16 | 0.236 |
| performance | 0.22 | 0.130 |
| risk | 0.15 | 0.024 |

A slider at 0.22 buys 22 % of the *weight*, on a component whose spread is what it is. That
is in `docs/methodology.md` as well as here.

### 3.5 Component correlations after R5

On the 168 evaluations where every remaining component scores:

```
             performance      fit  contract  timeline      risk
performance        1.000    0.372    -0.280    -0.241    -0.022
fit                0.372    1.000    -0.049    -0.282    -0.048
contract          -0.280   -0.049     1.000     0.083     0.016
timeline          -0.241   -0.282     0.083     1.000    -0.142
risk              -0.022   -0.048     0.016    -0.142     1.000
```

The largest remaining pair is fit × performance at 0.372, which is a real relationship
(a package that addresses needs tends to be better) rather than a restatement.

---

## 4. Pick valuation: methodology, and the precision it refuses

A pick is four separate unknowns and `analytics/picks.py` keeps them separate: what the
slot is worth, where it will land, whether it conveys, and whether the team owns it.

### 4.1 The estimand and its construction

```
player value  =  Σ_seasons total_minutes · (TEI_season − REPLACEMENT_TEI),  floored at 0
relative      =  player value ÷ mean player value of that draft class
rel(k)        =  3.3855·exp(−0.08388·(k − 1)) + 0.2525      R² 0.7534 on slot means
```

**Absence is a measured zero.** A drafted player who never appears in the observation window
contributed nothing above replacement, and that is what a bust is worth. Averaging only over
players you can see is the survivorship error that makes every late pick look useful. The
estimation set is **448 drafted players from classes 2016–2023**, of whom **323 appeared**.

**Within-class normalisation removes the career-stage confound exactly.** The window is
three seasons, so a 2016 draftee is observed in years 7–9 and a 2023 draftee in years 0–2 —
different quantities. Slot is orthogonal to class by construction (every class has one
player at every slot), so dividing by the class mean removes the class effect and leaves the
slot effect. The **first-round grid is complete: 240 of 240 cells**. The second round is
missing 32 of 240 — slots whose selection never played an NBA minute *or* was never made,
indistinguishable here — which are excluded and reported, never imputed.

**Floored at zero** because a team is not obliged to play a bad player; 88 of 448 had
negative raw value.

### 4.2 Validation, including the check the curve does not win

Leave-one-class-out over the 8 classes, ranking the held-out class's 52–58 players by a
curve fitted without them:

| check | result |
| --- | --- |
| Curve ranks the held-out class | **0.4624** Spearman, 8/8 classes positive (0.369–0.613), t = 15.36 |
| Within-class permutation null | 0.0588 |
| **Curve vs a two-band round-only rule** | **+0.0405, paired t = 1.33, p = 0.22 — not significant**, 6/8 classes |
| Four-band model (1–5 / 6–14 / 15–30 / 31–60) | 0.4808 — indistinguishable from the curve |
| **Slot gradient inside the first round alone** | **0.3277, 8/8 classes positive, t = 4.67, p = 0.0023** |

The smooth curve ships because it is not worse than any alternative **and** because what it
adds is independently established: ordering inside the first round, which is where trade
currency lives. The claim that it beats a coarse round-only rule is **not made**, and the
model version registered by `make train` carries `curve_minus_round_only` alongside the
diagnostics that pass.

### 4.3 Why nothing returns a bare number

Bootstrapping the 8 classes 2,000 times, the 90 % interval at slot 1 is **[2.98, 5.64] on a
fitted 3.64 — 73 % of the value**; at slot 60 it is 150 %. A single pick's outcome is far
more skewed than its mean:

| slots | mean | median | share exactly zero |
| --- | --- | --- | --- |
| 1–5 | 3.249 | 3.278 | 12 % |
| 6–14 | 1.805 | 1.280 | 31 % |
| 15–30 | 0.965 | **0.150** | 38 % |
| 31–60 | 0.310 | **0.000** | 66 % |

The landing slot compounds it. Measured on the ingested standings, one-year rank drift has
sd **8.53** against a no-information ceiling of **8.66** (rank correlation 0.602 and 0.509
across the two available transitions). **A team's finish one year out is barely more
predictable than a coin flip on this data.** Multi-year drift is extrapolated as a random
walk — labelled an assumption, because three seasons contain no multi-year transition to fit
— and capped at the ceiling; from about four years out the cap binds and the support is the
whole round. The unfitted fallback for rank drift is the ceiling itself: an unfitted drift is
not a small drift.

The **lottery is not modelled.** Only its structure is used: four selections are drawn, so a
lottery team can fall at most four places and any lottery team can rise to first. That is a
fact about the draw, not an estimate of its odds, and the odds table is not reproduced
because this repository has no source for it.

### 4.4 Three precision levels

| level | when | point estimate |
| --- | --- | --- |
| `interval` | unconditional, ownership verified | yes, with the class-bootstrap band |
| `range` | protected, swapped, or conditional | **no** |
| `unknown` | ownership unverified | **no** |

A protection whose text cannot be parsed into a selection range is treated as *conditional*,
not as unprotected. The dangerous failure mode is unreadable terms silently becoming clean
ones.

### 4.5 Ownership coverage

From a local RealGM future-drafts snapshot (`make import-draft-picks`; `data/imports/` is
gitignored in full and nothing is redistributed). Of **394 entries** in the 2026-07-28
snapshot:

| conveyance | entries | outcome |
| --- | --- | --- |
| unconditional | 184 | **92 verified picks** |
| swap | 161 | recorded, `is_verified = false` |
| protected | 33 | recorded, `is_verified = false` |
| conditional | 16 | recorded, `is_verified = false` |
| **unparsed** | **0** | — |
| unresolvable team names | **0** | — |

Every unresolved entry keeps its source sentence verbatim and raises a named data-quality
warning. `STEPIEN_FUTURE_FIRSTS` now **certifies** the teams the source resolves, **fails** a
deal that empties consecutive drafts, and reports `unavailable` naming the clause for the
rest. Measured per draft year, first round:

| draft | teams retaining their own pick, verified | teams with an unresolved entry |
| --- | --- | --- |
| 2027 | 17 | **10** |
| 2028 | 19 | 10 |
| 2030 | 23 | 6 |
| 2032 | 29 | **0** |

One unresolved swap is enough to withhold the verdict. A trade sending away a pick the
source does not show the team holding is reported as a disagreement, not resolved in either
direction.

---

## 5. Candidate generator: design and search coverage

### 5.1 What was wrong, measured

Generating for five focal teams at the end of R4:

| | |
| --- | --- |
| Counterparties reached | **4 of 29 (13.8 %)** — budget spent on the first four alphabetically |
| Candidates surfaced | 40 |
| ...whose **counterparty** utility was above neutral | **2** |
| Salary matching applied | none |

`COUNTERPARTY_MIN_UTILITY` was **42.0** — below the 50 that means "this deal changes
nothing" — so **38 of 40 "recommendations" were deals the model said would hurt the other
team**. That is how "Sam Hauser for LaMelo Ball" arrived at focal 69.9 / counterparty 42.3.

### 5.2 What replaces it

**Coverage is complete by construction.** The evaluation budget is divided across the 29
counterparties (14 each = 406 evaluations, essentially the old global 400) instead of being
consumed by the first few. The response reports, **per counterparty**, pairs enumerated,
pairs surviving constraints, pairs evaluated, candidates found, and whether that
counterparty was truncated internally.

**Both sides must clear 50** — the composite's own neutral, not a tuned threshold. It is
genuinely restrictive rather than an artifact of an inflationary composite: over **241
random two-team trades** on the same rosters, both sides clear 50 only **9.5 %** of the
time, exactly one side does **76.8 %**, and the two utilities sum to **99.80 ± 7.32**
against the 100 of a strictly zero-sum scale.

**Two stated policies do the work the composite cannot.** Requiring both sides above neutral
still surfaced "Coby White for Cooper Flagg, Dallas at 55.0", because a `fit` gain can
outweigh a `performance` loss under the default weights. So: **neither side may project
worse than −2 wins**, and **the packages may not differ by more than 2 wins of modelled
value**. Both are in projected wins, converted through R3's fitted coefficient and the
calibrated wins slope — nothing new is calibrated.

The value band was **relative first, and that was the wrong unit**: 60 % of the larger side
passed "Tatum and Vučević for Cunningham" at a 39 % gap, which is a **9.9-win** transfer. A
share of a large number is a large number.

**Also real now:** salary matching against the CBA's expanded-TPE bands wherever both
packages are priced (skipped and disclosed otherwise, using the permissive below-apron band
because no team has a verified apron position under the available contract data);
roster-spot feasibility against the 18-spot ceiling the roster rule fails on; ranking by how
well each side addresses **the other team's** needs; and a total ordering with a player-id
tiebreaker at every stage.

### 5.3 Basketball sanity, before and after

| focal | before | after |
| --- | --- | --- |
| BOS | Sam Hauser → LaMelo Ball (cp 42.3) | Ron Harper Jr. ↔ Tyler Kolek; Tatum+Hauser ↔ Booker+Gillespie |
| CHA | Coby White → Cooper Flagg (cp 55.0) | PJ Hall ↔ Christian Braun; PJ Hall ↔ Tyus Jones |
| CLE | — | Harden ↔ Şengün; Nance ↔ Sims; Strus ↔ Jabari Smith Jr. |

The Cooper Flagg, LaMelo Ball and Tatum-for-Cunningham packages are gone. What survives are
star-for-star swaps and role-player swaps, each publishing its package values, its projected
win deltas for both teams, and the gap between the packages in wins.

---

## 6. Performance, before and after

| | post-R4 | post-R5 |
| --- | --- | --- |
| `recency_weighted_features` (cold) | **1.045 s** | **0.045 s** (23.6×) |
| `/trades/generate` ATL | 2.34 s at **13.8 %** coverage | **1.03 s at 100 %** |
| `/trades/generate` BOS | 1.46 s | 0.77 s |
| `/trades/generate` CLE | — | 0.76 s |
| `evaluate` queries | 15 | **19** (budget < 25) |
| `generate` queries | 18–62 (4 rosters) | **112–392** (29 rosters, budget < 3000) |

**The collapse rewrite is exact, not approximate.** `sum(w·x over the rows where x is
present) / sum(w over those same rows)` is what `np.average(x[mask], weights=w[mask])`
computes. On the real 1,714-row frame all 632 rows and 33 columns match the loop to
**9.1e-13** — float summation order on a sum of minutes. The loop survives as a test oracle
in `test_feature_collapse_equivalence.py`, re-derived on the cases where the two
formulations could come apart.

**The generator's remaining cost was a distribution nobody read.** Profiling put **1.10 s of
1.83 s** in the 2,000-draw Monte Carlo; nothing scored reads it after R5-1b removed
`prob_positive` from `risk`. `simulate=False` skips it and marks the `uncertainty` block
`skipped` rather than filling it with zeros — an all-zero draw array reports
`prob_positive = 0.0`, which reads as "certain to hurt" (QA-5).

**`data_quality_issues` grew without bound**: 560 rows for 280 findings after two
`index-assets` runs, plus 273 `kaggle_source_conflict`. Findings with a stable identity are
upserted on (check, entity); the rest are bounded by `prune_resolved_issues` (30-day
retention, open findings never touched). `validate_data` prunes as part of its sweep, and
the worker now schedules `validate_data` — which is what actually bounds the table on a
deployed instance.

---

## 7. Distribution comparison, post-R4 → post-R5

Same 800 evaluations, same seed, same rosters, contract provider configured:

| component | n | sd | ties | → | n | sd | ties |
| --- | --- | --- | --- | --- | --- | --- | --- |
| performance | 482 | 16.55 | 2 | | 482 | 14.74 | **0** |
| fit | 440 | 32.55 | **106** | | 440 | 28.70 | **2** |
| contract | 168 | 25.84 | 16 | | 168 | 21.86 | **0** |
| timeline | 482 | 22.96 | 20 | | 482 | 19.88 | **0** |
| assets | 482 | **1.16** | 0 | | **0** | — | — |
| risk | 480 | 23.09 | 2 | | **482** | 12.80 | **0** |

Composite: sd 11.31 → 10.75, mean 49.90 → 48.89. **Rank correlation of the composite before
against after: 0.9459**, mean absolute change 2.95 points, maximum 14.06. R5 repaired the
construction without upending the ordering, which is what a correctness release should look
like.

---

## 8. R3 gate, re-measured on the post-R5 path

R5 touched the feature collapse, so the calibration was re-run rather than assumed.

| Criterion | Gate | Post-R5 | At R4 |
| --- | --- | --- | --- |
| Coefficient | — | **14.976967** | 14.976967 |
| Slope significance | t > 5 | **9.802** | 9.802 |
| LOTO out-of-sample RMSE | < 4.5 | **2.944 / 3.773** | same |
| …as a share of predicting zero | < 75 % | **56.6 % / 65.0 %** | same |
| Per-fold slopes vs pooled | ±15 % | **14.716 / 15.276 (±2 %)** | same |
| Roster-gut performance component | < 25 on all 30 | **max 9.72, 0 teams ≥ 25** | max 0.00 |
| Distinct band widths | > 400 of 512 | **510 of 512** | 507 |
| Band width monotone in minutes | ρ < −0.95 | **−1.0000** | −1.0000 |
| Performance-component sd | > 8 | **14.744** | 18.101 |

Every calibration figure is **bit-identical**, which is the expected result: the collapse
rewrite is exact to 1e-13 and R5 touched neither `INDEX_WEIGHTS` nor `Z_SOURCE_COLS`.

**One number moved, and it is a property of the scale, not the projection.** The roster-gut
figure was recorded by stripping the *entire* roster, which truncation floored at exactly
0.00; `bounded_score` never reaches an endpoint, so the same rosters now land at 0.20–9.72.
`delta_wins` is unchanged. `test_evaluation_sanity.py` pins the new construction.

**A related measurement worth recording, which R5 did not cause.** Under the stricter
"strip the best three" construction the QA-1 test names, Memphis scores **32.15** post-R5 —
and **31.35** pre-R5, both above the 25 line. Memphis losing its three best players costs
only 3.73 projected wins because its remaining rotation absorbs the minutes. That is the
rotation allocator redistributing proportionally to baseline minutes, it predates R5, and
it belongs to R6.

---

## 9. Tests and QA evidence

| Check | Result |
| --- | --- |
| Backend suite | **690 passed**, 1 skipped, 1 xfailed |
| Backend coverage | **88 %** (was 78.17 %); floor raised 68 → **85** |
| ruff / mypy | clean (85 source files) |
| eslint / tsc | clean |
| Frontend unit tests | **43 passed** (6 files) |
| Production build | 12 routes, succeeds |
| Migrations, clean DB | upgrade → downgrade to base → upgrade, all clean; `alembic check` reports no drift |
| Playwright e2e | **5 passed**, including the full team-outlook → strategy → evaluator → rules → evaluate → save → compare flow |
| Visual QA | **98 screenshots, CLEAN** — no horizontal overflow, no console errors, no empty pages · `docs/qa/r5/` |
| Browser QA | Risk and Cap tabs driven live at 375 / 768 / 1280; two copy defects found and fixed |

New test files: `test_component_scale.py`, `test_risk_orthogonality.py`,
`test_pick_valuation.py`, `test_draft_pick_ownership.py`, `test_assets_component.py`,
`test_candidate_generator.py`, `test_feature_collapse_equivalence.py`,
`test_worker_and_issue_growth.py`, `test_ingestion_jobs.py`, `test_training_pipeline.py`,
`test_cli.py`.

Coverage of the paths the plan named:

| module | before | after |
| --- | --- | --- |
| `ingestion/jobs.py` | **0 %** | 77 % |
| `analytics/train.py` | 36 % | **97 %** |
| `cli.py` | **0 %** | 92 % |
| `analytics/picks.py` | — | 97 % |
| `ingestion/draft_picks.py` | — | 91 % |
| `analytics/features.py` | 89 % | 93 % |

### 9.1 Trade scenarios exercised end to end through the API

| Scenario | Result |
| --- | --- |
| Realistic mid-rotation 1-for-1 | Both scored; `assets` withheld and disclosed |
| Extreme, two stars for one | `verified_illegal` (ROSTER_SIZE), both sides suppressed |
| Illegal, five out for one | `verified_illegal`, refusal names the rule |
| Missing data (no impact estimate) | confidence **low**; `fit` and `contract` withheld; the player named |
| Picks-heavy, verified pick | priced with an interval **[0.476, 5.635]** around 1.066 |
| Conditional pick (swap) | **no point estimate**; `assets` withheld; caveat quotes the source |
| Star for depth | BOS performance 25.0 / DEN 71.0 — correctly asymmetric, not "good for both" |
| Multi-player 3-for-3 | both above neutral, driven by fit |
| Empty trade | every component 50.0, `availability_delta` exactly 0 |
| One-way (player for nothing) | `verified_illegal` — the counterparty is at the 18-man ceiling |

### 9.2 A diagnosis worth recording

The frontend suite and `tsc` appeared broken at the start of this session — vitest timed
out waiting for its worker, `tsc --noEmit` sat at 0 % CPU for ten minutes. Neither was
caused by the release and neither was a sandbox restriction.

**`node_modules` had been evicted to iCloud.** `find frontend/node_modules -type f -flags
+dataless` returned **16,410 files**, `fileproviderd` was at 96 % CPU, reading 50 jest-dom
files took 21.7 s at 0 % CPU, and `import('jsdom')` took **659,821 ms**. Materialising the
tree (`find … -flags +dataless -print0 | xargs -0 -P 32 cat > /dev/null`) fixed both: vitest
now runs in 1.05 s and `tsc` completes.

`brctl download` reported success and materialised nothing; reading the files is what works.
If this recurs, check for dataless files before concluding anything about the toolchain.

---

## 10. Migrations and response-contract changes

**Migration `e5c81f4a7b30`** adds `draft_picks.conveyance` and `draft_picks.source_text`,
plus an index on `(draft_year, round_number)`. Nullable with **no back-fill**: an existing
row's conveyance is genuinely unknown, and defaulting it to `unconditional` would invent
the certainty the column exists to withhold. Reversible, verified up→down→up from a clean
database.

Response-contract changes, all additive except where noted:

| Path | Change |
| --- | --- |
| `detail.risk` | `prob_positive_outcome` **removed** (it is in `uncertainty`); adds `outgoing_availability`, `roster_availability`, `availability_delta`, `legality_verification`, `baseline_note`, `method` |
| `detail.assets` | adds `picks_priced`, `picks_not_priced`, `pick_units_net`, `pick_reference`, `payroll_delta`, `payroll_basis`, `payroll_scored`, `precision_note`, `unavailable` |
| `components.assets` | **may now be `null`** and appear in `excluded_components` |
| `detail.fit` | adds `raw_fit` |
| `uncertainty` | may carry `skipped: true` when a caller asked for point estimates only |
| `/trades/generate` `coverage` | adds `per_counterparty`, `pairs_rejected_by_constraint`, `salary_matching`, `counterparties_truncated`, `both_sides_above_neutral`, `max_projected_win_loss`, `max_value_gap_wins`; **removes** `share_searched < 1` as a normal outcome |
| `/trades/generate` candidates | adds `counterparty_components`, `package_value`, `projected_delta_wins` |
| `/comparisons/{id}` | adds `domination` beside `dominated_by` |
| `STEPIEN_FUTURE_FIRSTS` | may now return `pass` or `fail` where it only ever returned `unavailable` |

---

## 11. Commits and push status

```
57c3edd fix(ui): restore a lost space and soften a panel that quoted a release number
bef6a94 fix(comparisons): judge domination on every shared axis, and correct the copy R5 falsified
ae38ac1 test: cover the modelling, ingestion and operational paths, and ratchet the floor
57bd580 perf: vectorise the window collapse, skip the unread simulation, bound the issue table
46c9520 feat(candidates): search the whole league, and refuse the deals the composite permits
269664e feat(assets): price draft capital empirically, and stop scoring salary twice
0ec2bab feat(picks): empirical pick valuation and verified ownership, with the precision it refuses
3f257f8 fix(evaluation): take performance back out of risk
fd3b45e fix(evaluation): squash unbounded components instead of truncating them
```

All pushed to `origin/feat/rosterlab-autonomous-roadmap`. `main` untouched, no history
rewritten, nothing force-pushed, no `git stash` used.

---

## 12. Deviations from the plan

1. **Risk carries no legality-exposure term.** The plan specified "availability and legality
   exposure only". The term was built and measured: 0.063 ± 0.071 with a ceiling of 0.143
   across 482 evaluations, moved by which contract fields the provider supplies rather than
   by the deal. It is published unscored. §3.2.
2. **`assets` scores no payroll term.** The plan implies asset value includes flexibility. It
   was built, and scoring it made `assets` 0.837-correlated with `contract`. Reported,
   unscored. §3.3.
3. **`fit`'s ×120 constant was not changed.** The plan named it "the component that plausibly
   clips". It does — 24.1 % — but the defect was the *truncation*, not the constant, and
   R5-1a fixed it without touching a scale anywhere. Re-measured clip rate: 0.45 %.
4. **The `scenario_weights` EAV migration was not done.** It is listed in the plan's R5 line.
   The table is a clean `(scenario, component, weight)` with a unique constraint; nothing in
   R5 was blocked by it, and a schema change with no measured defect behind it is the kind
   of scope expansion this release was asked to avoid. Deferred with the reason stated.
5. **The pick-value curve does not beat a round-only rule.** Reported rather than tuned. §4.2.
6. **The coverage floor moved to 85, not to a modelling-path-specific gate.** The plan asked
   for "modelling-path coverage > 70 %"; every modelling module is now 93–99 % and the total
   floor is the ratchet that protects it.
7. **`fit` still has no replacement baseline for one-way deals.** R1 recorded that R5 would
   supply one. R5-1b built exactly the right construction for this case in `risk` — an empty
   side is priced at *the roster's own measured availability* — and the same shape is
   available to `fit` using the roster's own skill percentiles. It was **not** applied,
   because it changes a scored component and no measurement was taken of what it does to
   the fit distribution. Shipping it unmeasured, in a release whose entire subject is that
   unmeasured constructions are how placebos get in, would have been the wrong trade.
   Carried to R6 with `_risk` as the template.

---

## 13. Unresolved data limitations

1. **Half the traded picks cannot become ownership.** 161 swaps, 33 protections and 16
   conditional conveyances in the RealGM snapshot are not reducible to an owner by any
   implementation. They are recorded with their source sentence and the Stepien rule reports
   `unavailable` naming them. Resolving them needs a source that states outcomes, not terms.
2. **The pick curve rests on 8 draft classes and a 3-season observation window.** The 90 %
   band is 73 % of the fitted value at slot 1 and 150 % at slot 60. Narrowing it needs
   career-length outcome data, not a better estimator.
3. **Landing slots are nearly unknowable on this data.** One-year rank drift is sd 8.53
   against a 8.66 ceiling. From about four years out the support is the whole round.
4. **The lottery odds table is not in this repository** and is not reproduced from memory.
   Only the draw's structure is used.
5. **`contract` is available on 168 of 482 evaluations** and 0 of 30 teams have a verified
   payroll — unchanged from R2c, and the reason `assets` cannot use apron proximity.
6. **`draft_year` stops at 2023** in the player table, so the two most recent draft classes
   are absent from the estimation set and from any pick this product would value today.
7. **Kaggle `nbadb` is still absent** (`data/external/` empty). Blocks R6's lineup-aware fit;
   blocked nothing in R5.

---

## 14. Recommended R6 starting point

**Start with the rotation allocator, before comparable-trade retrieval.**

R5 measured two symptoms of one cause. Memphis loses 3.73 projected wins when its three best
players leave; and the generator repeatedly found deals where a team *improves* by giving
away a rotation player. Both come from `allocate_rotation` redistributing the 240 minutes
proportionally to baseline minutes: removing a mid-TEI player hands his minutes to whoever
remains, and if the next man up is above replacement the team gains. The allocator is
correct about the minutes constraint and wrong about who absorbs them.

Concretely, in order:

1. **Measure the allocator's replacement behaviour** — for each of the 30 rosters, the change
   in `team_tei_per_minute` from removing each player in turn, against the change a
   depth-chart-aware reallocation would give. The gap is the defect's size.
2. **Then** comparable-trade retrieval (the plan's R6 headline and the only feature that
   replaces model output with evidence), which will be judged against a projection that has
   this fixed.
3. Lineup-aware fit remains blocked on the Kaggle dataset; `TeamPlayerOnOffDetails` is
   **Large** and requires changing `client.fetch_dataframe`'s single-dataset contract.

Do **not** start R6 by re-tuning the composite. R5 established that its components are now
distinct (max \|r\| 0.372), that its ordering is stable (0.9459 rank correlation through a
release that changed four components), and that its weakest link is the projection feeding
`performance`, not the weighting on top of it.
