# RosterLab R5.5 — The Rotation Allocator

**Branch:** `feat/rosterlab-autonomous-roadmap` · **Base:** `f217710` (end of R5)

A prerequisite correctness release for R6. R5 measured two symptoms of one cause and
deferred the fix because fixing it is a projection change: Memphis lost only **3.73
projected wins** when its three best players left, and the rebuilt candidate generator kept
finding deals where a team improved by giving a rotation player away.

The cause was named correctly by R5 — `allocate_rotation` redistributing proportionally —
but the fix is not where R5 expected it. The allocator's arithmetic was never wrong. It was
being **called twice independently**, once on each roster, so a departure's minutes were
re-shared across everyone who stayed at the quality of everyone who stayed.

Two things were built and then **not** shipped after measuring them: a depth-chart cascade
replacing the level model (it lost to the model it would have replaced, and to an
equal-minutes null), and a fitted compression exponent (the data preferred exactly the
shipped value). Both are reported in §3, because a release that only lists what worked is
not a measurement report.

---

## 1. The defect, measured before anything changed

487 leave-one-out removals across the 30 ingested rosters: remove each modelled player in
turn, and record what the projection says it cost.

| | measured |
| --- | --- |
| Removals scored as an **improvement** | **308 of 487 (63.2 %)** |
| …of players **above replacement level** | **191 of 370 (51.6 %)** |
| …who were **rotation players** (≥ 15 mpg) | **152** |
| Largest such gain | CLE, Max Strus, −0.94 TEI at 28.4 mpg → **+3.21 wins to remove** |

The mechanism is exact, not statistical. With the level model sharing 240 minutes in
proportion to baseline minutes, removing player *j* changes team TEI by

```
d_teamTEI(remove j)  =  (w_j / W) · ( ebar_-j − e_j )
```

so a removal is scored as an improvement **exactly when the player sits below his own
team's minutes-weighted mean** — a rotation-quality bar, not a replacement one. That rule
predicted the sign on **487 of 487** removals.

Eight worst cases, all genuine rotation players:

| | TEI | mpg | R5 | R5.5 |
| --- | --- | --- | --- | --- |
| CLE Max Strus | −0.94 | 28.4 | **+3.210** | −0.347 |
| LAL Marcus Smart | −1.18 | 27.1 | +2.944 | −0.051 |
| MIA Davion Mitchell | −1.21 | 26.4 | +2.756 | −0.017 |
| SAS Harrison Barnes | −0.85 | 27.1 | +2.486 | −0.979 |
| BOS Baylor Scheierman | −1.18 | 17.6 | +2.426 | −0.053 |
| ORL Tristan da Silva | −1.20 | 23.7 | +2.377 | −0.023 |
| OKC Cason Wallace | −0.73 | 25.7 | +2.322 | −1.150 |
| NOP Herbert Jones | −1.13 | 29.7 | +2.132 | −0.132 |

---

## 2. Three measurements that decided the fix

All on the ingested history: 90 team-seasons, 59–60 usable transitions.

### 2.1 Who absorbs vacated minutes — the shipped shape loses to its own null

Each candidate is handed the same total the returners actually regained and asked only to
distribute it, so roster turnover, pace and arrivals drop out and only the **shape** is
scored.

| shape | MAE (mpg) | vs shipped | t | better on |
| --- | --- | --- | --- | --- |
| proportional-to-baseline **(shipped)** | **4.081** | — | — | 0/59 |
| uniform | 3.240 | +0.841 | 8.51 | 54/59 |
| headroom under a 36-minute ceiling | 3.037 | +1.044 | 5.44 | 44/59 |
| **depth chart, next man up** | **2.773** | +1.308 | 7.51 | 51/59 |
| *permutation null (shipped weights, shuffled)* | *3.437* | | | |

**The shipped shape is worse than a random permutation of its own weights.** Every
alternative beats it. That is a falsification, not a preference.

### 2.2 Who gives minutes up — the shipped shape is right, and stays

| shape | MAE (mpg) | vs shipped | t | better on |
| --- | --- | --- | --- | --- |
| proportional-to-current **(shipped)** | **2.813** | — | — | — |
| uniform | 3.375 | −0.562 | −7.49 | 9/59 |
| bottom of the chart first | 4.585 | −1.772 | −7.99 | 3/59 |
| *permutation null* | *3.517* | | | |

**The two directions are genuinely asymmetric**, and the release keeps the shed direction
exactly as it was. A player has room to gain up to a ceiling and room to lose down to zero;
those are different quantities and the data treats them differently.

### 2.3 The absorbers cannot be told apart from a replacement

| | spread of served TEI | mean estimation sd | **signal share** |
| --- | --- | --- | --- |
| inside a team's top 10 by minutes (n=300) | 1.210 | 0.831 | **0.529** |
| outside it (n=187) | 1.031 | 1.409 | **0.000** |

Outside the rotation, the entire spread of TEI is accounted for by estimation error.
Promoting a bench player at his own point estimate is promoting noise — which is what the
old code did every time a rotation player left.

This is also what the codebase already asserts and the allocator was contradicting:
`REPLACEMENT_TEI` is fitted as *"mean TEI of player-seasons outside their team's top 10 by
minutes"* and `ROTATION_DEPTH` is 10. The freed minutes belong to exactly that population.

---

## 3. What was built and then not shipped

### 3.1 A depth-chart cascade for the level model — it lost

The level model was suspected too, and with a plausible story: served baseline minutes sum
to **362.6** against a 240-minute budget on all 30 teams, so proportional scaling multiplies
everyone by 0.66 and credits Nikola Jokić — the highest-TEI player in the model — with
**21.8 minutes**. Denver's 17 modelled players each land between 10 and 22.

So four complete allocators were scored out of sample: hand each the season-*s* roster with
each player's season-*s* minutes, ask for a 240-minute allocation, and compare against what
the team actually did in season *s+1*. 60 transitions, 911 player-seasons.

| allocator | MAE | RMSE | top-1 error | > 10 min |
| --- | --- | --- | --- | --- |
| **proportional-to-baseline (shipped)** | **5.803** | 7.351 | +2.84 | 11.4 |
| depth-chart cascade (hard cut) | 8.641 | 10.961 | +10.82 | 8.8 |
| depth-chart cascade (soft, 10 min) | 8.367 | 10.633 | +10.85 | 8.7 |
| mpg × availability, rescaled | 6.437 | 8.523 | +5.44 | 9.9 |
| *null: everyone equal* | *8.148* | | | |
| *observed* | | | | *9.2* |

The cascade is **worse than an equal-minutes null**, and overshoots the top player by 11
minutes, because the quantity a team actually realises is a *load* — minutes per team game,
already net of missed games — and a role claim is not one. **The level model is therefore
not changed**, and a test pins it so a future release cannot change it by accident.

The consequence is stated rather than hidden: the shipped allocation still spreads 240
minutes across ~13 players above 10 minutes where the real data shows ~10, and still credits
the best player with roughly 22 minutes where the real distribution says ~30. That is a real
limitation (§7) — it is simply not one this evidence supports fixing by any of the three
alternatives tried.

### 3.2 A fitted compression exponent — the data chose the shipped value

`allocation ∝ baseline^β`, fitted against the observed rotation profile over 90
team-seasons. β = 1.00 (the shipped value) minimised the error at 1.703, and
**leave-one-team-out chose β = 1.00 on all 30 folds**. Nothing to change.

### 3.3 Two measurement constructions that were wrong, and how they were caught

Worth recording, because both produced confident and wrong answers first.

1. **Per-game averages normalised by their own sum.** A player with 5 appearances at 25 mpg
   entered the denominator as a 25-minute rotation player, so the reconstructed rank-1 came
   out at **59.8 mpg** — impossible, which is what exposed it.
2. **Season totals.** `player_season_stats.minutes` is *already* minutes per game (Tyrese
   Maxey 38.0, gp 70), so treating it as a total was wrong in the other direction.

The correct construction is `load = mpg × games / 82`, which sums to 240 by definition. It
was checked before use: real rosters sum to **240.7**, and the served rosters' `Σ(mpg ×
availability)` is **249.0** — the same regime, which is what establishes that
`baseline_minutes` is an mpg and not a load. §2's tables are all on this construction; the
first-pass numbers are discarded, not reconciled.

---

## 4. What changed

| # | Change | Commit |
| --- | --- | --- |
| R5.5-1 | The after-roster is priced against the before-allocation | `bef1d66` |
| R5.5-2 | One-way `fit` scored against a measured replacement | `457f3eb` |
| R5.5-3 | The giveaway property pinned through the service | `9efe8d7` |

### 4.1 The counterfactual (`bef1d66`)

`allocate_rotation(players, anchor=...)`. With an anchor:

- an **incumbent keeps the minutes he already had** — he does not stretch to cover a
  departure;
- an **arrival claims his established role on the anchor's own scale**, recovered from the
  anchor rather than assumed, so an arrival's uncompressed mpg is never compared against
  incumbents' compressed minutes;
- a **departure's minutes go unfilled** and are charged to a replacement player;
- a **surplus is shed proportionally**, the direction §2.2 supports.

This makes the projection **exactly monotone**, and the magnitude is forced too:

```
d_teamTEI(remove j)  =  −(m_j / 240) · ( e_j − REPLACEMENT_TEI )
```

Any other answer means somebody absorbed the minutes. `test_rotation_absorption.py` asserts
the identity, not merely the sign.

### 4.2 Results

| | R5 | R5.5 |
| --- | --- | --- |
| Removals scored as an improvement | 308 (63.2 %) | 117 (24.0 %) |
| …of **above-replacement** players | **191 of 370 (51.6 %)** | **0 (0.0 %)** |
| …rotation players ≥ 15 mpg | **152** | **0** |
| Below-replacement removals that *hurt* | — | **0 of 117** |
| Strip the best player, mean | −5.31 wins | **−7.36** |
| Strip the best three, mean | −12.67 wins | **−16.52** |
| **Memphis, strip the best three** | **−3.73 wins** | **−6.03** |
| **QA-1 probe score** (gate: < 25) | **32.15** | **23.06** |

The QA-1 line is the one that was blocking R6: Memphis scored **above** the 25 threshold
both pre- and post-R5, and now scores **23.06**, with 0 of 30 teams at or above 25.

### 4.3 A deliberate asymmetry, stated plainly

Departures and arrivals have **different thresholds**, and this is the design, not a
leftover:

- **losing** anyone above replacement always hurts — his minutes go to a replacement;
- **gaining** a player for free only helps if he beats the players he displaces — his
  minutes come *out of* the incumbents.

So a free below-average player really does make a good team slightly worse, because he takes
minutes from someone better. Measured on Boston, acquiring each Denver player for nothing:

```
TEI −0.96 → −2.63 wins   −0.46 → −1.86   −0.06 → −1.23
     +0.25 → −0.92        +1.46 → +3.70   +4.58 → +13.20
```

Monotone in the arriving player's own quality, with the break-even at the roster's own
weighted mean. The model does not assume a coach benches a bad acquisition, because nothing
measured here supports that optimisation.

---

## 5. The one-way `fit` baseline (`457f3eb`)

R1 removed a flat 50th-percentile player from `fit_score` — trading everyone away for
nothing scored as if a median NBA rotation player had been acquired in every skill — and
withheld the component. R5 recorded that it would supply a measured baseline and deferred
again, because *"it changes a scored component and no measurement was taken of what it does
to the fit distribution."* Both measurements are here.

**`REPLACEMENT_SKILLS`**, on the same population `REPLACEMENT_TEI` is fitted on (187 players
outside their team's top ten, against 300 inside):

| skill | inside | **outside** | t vs 0.5 |
| --- | --- | --- | --- |
| scoring | 0.632 | **0.391** | **−5.99** |
| creation | 0.568 | **0.420** | **−3.97** |
| shooting_volume | 0.540 | 0.444 | −2.66 |
| turnover_avoidance | 0.520 | 0.446 | −2.46 |
| size | 0.453 | 0.468 | −1.48 |
| shooting_accuracy | 0.552 | 0.482 | −0.93 |
| rim_protection | 0.500 | 0.516 | +0.71 |
| team_defense | 0.505 | 0.522 | +1.01 |
| rebounding | 0.497 | 0.528 | +1.36 |

**The shape is the finding, not the level.** The mean across skills is 0.469 — only 0.031
below the constant R1 removed — but the spread across skills is **0.136**, four times that
gap. What separates a bench player is that he cannot score or create; he rebounds and
protects the rim at a league median rate. A single scalar, at 0.5 or at 0.469, erases exactly
the informative part. Four of the nine are not separated from 0.5 on their own and are used
at their measured values anyway, because 0.5 is not a better-supported alternative for them —
it is a different unmeasured constant. Leave-one-team-out moves no skill mean by more than
**0.0092**.

**The two sides take different baselines**, mirroring §4.3: nothing arriving means a
replacement plays those minutes; nothing departing means they come out of the incumbents, so
the departing package is the roster's own minutes-weighted profile — R5-1b's construction
for `risk`, applied to skills.

Measured on 240 deals of each shape:

| population | n | mean | sd | baseline used |
| --- | --- | --- | --- | --- |
| two-sided (**must not move**) | 240 | 48.83 | 29.67 | `None` ×240 |
| one-way OUT (new) | 240 | **41.01** | 22.59 | `replacement` ×240 |
| one-way IN (new) | 240 | 51.38 | 25.49 | `roster` ×240 |

Giveaways land below neutral **68.3 %** of the time, corr(minutes given away, fit) = −0.112,
and the worst scores are Michael Porter Jr., Jaren Jackson Jr. and Myles Turner — real
rotation players. Both substitutions are disclosed under `baseline_used` / `baseline_note`,
and the component is still withheld when neither side has a measurable player.

**What this score does not say is how much changes.** `fit_score` normalises minutes within
each side, so a package's weight cancels and the component measures the *fit* of the change
rather than its size — an 8-minute arrival scores like a 32-minute one. That is pre-existing
behaviour on two-sided deals, it is why `performance` and not `fit` carries magnitude, and
re-normalising it would be a re-tuning of the composite that no measurement here motivates.

---

## 6. Gates, re-run from scratch

Nothing below is carried forward. Every figure is measured on the post-R5.5 path against the
live ingested database.

### 6.1 R3 calibration — **19 of 19 criteria met**

| Criterion | Gate | Post-R5.5 | At R5 |
| --- | --- | --- | --- |
| Coefficient | — | **14.976967** | 14.976967 |
| Slope significance | t > 5 | **9.802** | 9.802 |
| LOTO out-of-sample RMSE | < 4.5 | **2.944 / 3.773** | same |
| …as a share of predicting zero | < 75 % | **56.6 % / 65.0 %** | same |
| Per-fold slopes vs pooled | ±15 % | **14.716 / 15.276 (±2 %)** | same |
| Served constant matches the fit | ±2 % | **14.977 vs 14.977** | same |
| R² · n | — | **0.6236 · 60** | same |
| Roster-gut (whole roster) | < 25 on all 30 | **max 9.72**, 0 teams ≥ 25 | max 9.72 |
| **QA-1 strip the best three** | < 25 on all 30 | **max 23.06 (MEM)**, 0 ≥ 25 | **32.15 — over** |
| Distinct band widths | > 400 of 512 | **510 of 512** | 510 |
| Band width monotone in minutes | ρ < −0.95 | **−1.0000** | −1.0000 |
| Performance-component sd | > 8 | **18.489** | 14.744 |
| Performance boundary ties | 0 | **0 of 800** | 0 |
| Fit boundary ties | < 3 % | **0 of 800 (0.0 %)** | 2 of 440 |
| Above-replacement giveaway never gains | 0 violations | **0 of 370** | 191 |

Every calibration figure is **bit-identical**, and the reason is structural rather than
lucky: `_team_tei_transitions` builds `d_tei` from `player_season_stats` weighted by season
minutes and **never calls `allocate_rotation`**. R5.5 changed only the counterfactual path,
and the level model — which the served `before` allocation comes from — is untouched.

### 6.2 R5 decision-engine and generator gate

| | R5 | R5.5 |
| --- | --- | --- |
| Both sides above neutral, 241 random trades | 9.5 % | **11.2 %** |
| Exactly one side | 76.8 % | **73.4 %** |
| Two utilities sum to | 99.80 ± 7.32 | **97.74 ± 8.23** |
| Counterparties reached, per focal team | 29/29 | **29/29** |
| Candidates surfaced (BOS/CHA/CLE/MEM/DEN) | — | **8 each** |
| Surfaced deals whose counterparty is below neutral | 38 of 40 *(pre-R5)* | **0 of 15** |

The base rate moving 9.5 → 11.2 % and the sum 99.80 → 97.74 are both consequences of the
fix, and both are correct: an unbalanced trade now leaves replacement minutes on the side
that sends more, so the model says a lopsided deal destroys a little value rather than being
strictly zero-sum. "Both above neutral" remains genuinely restrictive.

Basketball sanity is preserved — BOS still surfaces Ron Harper Jr. ↔ Tyler Kolek and CLE
still surfaces Harden ↔ Şengün, the deals R5 recorded as its post-fix output.

### 6.3 Scenario battery — **16 of 16**

Realistic and adversarial, driven through the real API. Highlights: a star-for-depth deal is
correctly asymmetric (BOS 16.64 / DEN 74.71 with Tatum leaving); a five-for-one is
`verified_illegal`; losing the three biggest roles costs at least 2 wins on **every** team
(worst is Memphis at −4.33); no player is ever allocated above his 36-minute cap, below
zero, or beyond the 240-minute budget; a phantom move is 422 and an unknown player id is 404.

---

## 7. Tests and QA evidence

| Check | Result |
| --- | --- |
| Backend suite | **748 passed**, 1 skipped, 1 xfailed |
| Backend coverage | **88.24 %** (floor 85) |
| ruff / mypy | clean (85 source files) |
| Frontend unit tests | **43 passed** (6 files) |
| eslint / tsc | clean |
| Production build | **12 routes**, succeeds |
| Migrations, clean DB | upgrade → downgrade to base → upgrade, 6 revisions each way; `alembic check` no drift |
| Playwright e2e | **5 passed**, including the full flow |
| Visual QA | **98 screenshots, CLEAN** — no horizontal overflow, no console errors, no empty pages · `docs/qa/r55/` |
| Browser QA | Trade evaluator driven live; `/trades/evaluate` 200, no console errors, incumbents move ≤ 0.1 min |

New test files: `test_rotation_absorption.py` (37 tests), `test_one_way_fit_baseline.py`
(18 tests), plus three service-level giveaway properties in `test_evaluation_sanity.py`.

**Performance**, against R5's recorded budgets — nothing regressed:

| | R5 | R5.5 |
| --- | --- | --- |
| `recency_weighted_features` | 45 ms | **30.3 ms** |
| `evaluate_for_team` | 19 queries (budget < 25) | **5 queries**, 8.0 ms |
| `/trades/generate` ATL / BOS / CLE | 1.03 / 0.77 / 0.76 s | **0.24 / 0.27 / 0.23 s** |
| generate queries (budget < 3000) | 112–392 | **740–753**, 29/29 coverage |

### 7.1 One environment finding, not caused by this release

The dev database `backend/tradelab.db` was **one migration behind** (`d3e5a71b9c02`, missing
`draft_picks.conveyance` from R5's `e5c81f4a7b30`). `generate_candidates` swallows exceptions
from `build_trade_context` with a bare `except Exception: continue`, so the generator
returned **0 candidates on all 30 teams** with no error surfaced — 406 pairs evaluated, 406
silently discarded. This predates R5.5 and was mistaken for a regression by it until the
exception was surfaced deliberately.

`alembic upgrade head` fixed it. The silent `except` is worth narrowing in a later release;
it converts a schema drift into an empty result set that looks like a modelling outcome.

---

## 8. Response-contract changes

Additive only.

| Path | Change |
| --- | --- |
| `RotationResult` | adds `unfilled_minutes` — the minutes charged to a replacement, published rather than inferred |
| `allocate_rotation` | adds an optional `anchor` parameter; without it, behaviour is unchanged |
| `detail.fit` | adds `baseline_used` (`null` \| `"replacement"` \| `"roster"`) and `baseline_note` |
| `components.fit` | now **scores** one-way deals that were previously `null` and listed under `excluded_components` |

No migration. No schema change.

---

## 9. Deviations and limitations

1. **The level model was not changed**, though it is visibly implausible in levels — 13
   players above 10 minutes against a real 10, and the best player at ~22 minutes against a
   real ~30. Three alternatives were measured and all lost, one of them to an equal-minutes
   null. Fixing it needs a *load*-shaped estimand, which means separating a player's role
   from his availability throughout the projection — a larger change than this release, and
   one that would require refitting the R3 coefficient.
2. **A free below-average acquisition makes a good team slightly worse** (§4.3). Correct
   under the measured shed rule, and stated rather than smoothed away.
3. **`fit` measures the fit of a change, not its size** (§5). Pre-existing; re-normalising it
   would be a composite re-tune with no measurement behind it.
4. **The replacement skill profile uses four values not separated from 0.5** individually.
   Used at their measured values because 0.5 is not better supported, and disclosed.
5. **The generator's silent `except Exception: continue`** converts schema drift into an
   empty result set (§7.1). Found here, not fixed here — it is not a projection defect and
   this release is scoped to the projection.
6. **`ROTATION_DEPTH`, `REPLACEMENT_TEI` and the level model still disagree** about how deep
   a rotation is. The counterfactual now honours the first two; the level model does not, per
   deviation 1.

---

## 10. Commits and push status

```
9efe8d7 test(evaluation): pin the giveaway property through the service, not just the allocator
457f3eb feat(fit): score one-way deals against a measured replacement, not a constant
bef1d66 fix(projection): charge a departure's minutes to a replacement, not to the roster
```

All pushed to `origin/feat/rosterlab-autonomous-roadmap`. `main` untouched, no history
rewritten, nothing force-pushed, no `git stash` used.

---

## 11. Where R6 resumes

The R6 boundary is unchanged and **this release stops at it**. Comparable-trade retrieval
was not begun.

What is now true that was not before:

- the projection is **exactly monotone** in replacement level, and the identity is asserted
  rather than spot-checked;
- **QA-1 passes** (23.06 against a 25 line) — the probe R5 recorded as the blocker;
- one-way deals are **scored** against a measured baseline, closing R1's deferral and R5's;
- every R3 calibration figure is **bit-identical**, and the reason is structural.

R6 should still start with comparable-trade retrieval, judged against this projection. The
level-model limitation in deviation 1 is the next projection question, and it is a bigger
one than this release: it changes what `minutes` *means* throughout, and the R3 coefficient
is fitted on the current meaning.
