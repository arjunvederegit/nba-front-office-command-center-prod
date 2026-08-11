# RosterLab R4 — Basketball Methodology

**Branch:** `feat/rosterlab-autonomous-roadmap` · **Base:** `6fd719e` (end of R3)

R4 replaces four proxies that were measurably pointing the wrong way, retires a clustering
step that was unstable rather than merely imprecise, removes three discontinuities that
moved scored components by more than the model's own precision, and — the part worth
reading first — **withdraws one claim the data cannot support** instead of restating it
with different weights.

The R3 conversion coefficient was re-measured on the finished R4 code path, not assumed.

---

## 1. What changed, and what it was measured against

| # | Change | Commit |
| --- | --- | --- |
| R4-1a | Roster fit sums over skills, not over needs | `27729db` |
| R4-1b | `turnover_avoidance` measured, replacing a mapping to assist rate | `77cb7fb` |
| R4-1e | R4's skill inputs plumbed into the served window frame; skills-cache deploy hazard fixed | `ed068f8` |
| R4-1c/1d/2 | Defence and shooting split into four measured skills; weight vectors committed | `20986d7` |
| R4-2 | Point-of-attack claim withdrawn after its pre-registered check failed | `2bda9f8` |
| R4-3 | k-means retired for a deterministic size-first role chain | `4e88bdf` |
| R4-4 | Continuous age curves, self-excluded percentiles, capped rotations | `f495271` |
| R4-2/UI | Weights re-justified by construct; new vocabulary named in the UI | `969d2c2` |
| R4-4 | One definition of rotation depth | *(see log)* |

---

## 2. R4-1a — fit counted some skills twice

`fit_score` summed over **needs**. Several needs legitimately resolve to one skill, so one
skill delta was multiplied by two or three severities and added that many times.

Measured on the 30 seeded teams before the fix:

| Quantity | Measured |
| --- | --- |
| Teams with ≥1 skill claimed by ≥2 active needs | **19 of 30** |
| Mean inflation (Σ severities ÷ largest severity) | **1.625×** |
| Worst | **2.67×** — `playmaking` + `ball_security` + `secondary_creation` → `creation` |
| Skills affected | `creation` 12 teams · `shooting` 9 · `perimeter_defense` 9 |

The sum now runs over skills, with severity the **maximum** over the needs mapping to a
skill — not the sum, which would leave the 0..1 range severity is defined on and silently
restore the double count. The UI still lists a number per need, so the skill's single
contribution is split across its needs in proportion to their severities; the parts sum to
the contribution rather than to a multiple of it.

Landed **before** the proxy fixes deliberately. Fixing the proxies first would have left
`perimeter_defense` double-counted for nine teams, so most of the measurement error would
have survived the data improvement while credit was claimed for removing it.

After R4-1b and R4-1c removed two of the three collisions, the residual team-level effect
of the aggregation fix alone is a mean **1.118×** and a maximum **1.48×** over 30 teams.

---

## 3. R4-1b — ball security pointed at the players who lose the ball

`NEED_TO_SKILL` sent `ball_security` to `creation`, which is `pct(AST_PCT)`. A team with a
turnover problem was told to acquire high-assist ball handlers.

| Measured (player-seasons ≥ 1000 minutes) | Value |
| --- | --- |
| corr(`pct(AST_PCT)`, `pct_inv(TM_TOV_PCT)`) | **−0.255** (−0.142 over all rows) |
| Top 12 by assist rate sitting below median in turnover avoidance | **10 of 12** |
| Their mean turnover avoidance (0.5 = median) | **0.285** |

The mapping did not merely fail to help; it pointed at the worst available answer.

`TM_TOV_PCT` is a genuine player quantity here, not a team one: team-season fixed-effect
share **0.058** over all rows and **0.166** among rotation players, correlation with its
own team's rate **0.110**, year-over-year reliability **0.735**.

The inversion is a named `pct_inv` helper. There was no inversion mechanism in the skill
path to copy — `STAT_RULES`' `lower_is_need` acts team-side and a negative `INDEX_WEIGHTS`
weight acts on a z-score — and a bare `1 - pct(...)` is one careless edit from losing the
sign that is the entire fix. An AST-level test asserts the helper is used and no inline
inversion exists.

Verified in the production window frame, not only in fixtures: **632 of 632** players carry
the skill, **588** distinct values, sd **0.2887**.

---

## 4. R4-2 — the defensive metric, and the criteria that could not judge it

### 4.1 The plan's prescription is contradicted by the data

The plan specified the team-demeaned on-court differential as the **primary** term at
≥ 50 % weight, with event rates minor. Three independent measurements say otherwise.

**Raw `DEF_RATING` is mostly team.** Team-season fixed-effect share of player
`DEF_RATING`: **0.155** over all rows, **0.677** among players with ≥ 1000 minutes,
**0.700** minutes-weighted. The plan's 65.1 % reproduces at the rotation-player subset.

**The differential is the least reliable input available.** Year-over-year correlation,
same player, both seasons ≥ 1000 minutes (n = 391):

| Quantity | r |
| --- | --- |
| `DREB_PCT` | 0.926 |
| `blk_per_min` | 0.907 |
| `pf_per_min` | 0.819 |
| `stl_per_min` | 0.725 |
| raw `DEF_RATING` | 0.432 |
| **team-demeaned differential** | **0.283** |
| …restricted to players who **changed team** | **0.166** |

A trade tool projects a player onto a new roster. A metric that does not survive the move
fails at its only job.

**Beyond its own persistence, the differential adds nothing.** Partial rank correlation
with next-season differential, controlling for this-season differential (n = 391):

| Metric | raw | partial |
| --- | --- | --- |
| lagged differential itself | 0.310 | −0.011 |
| shrunk differential | 0.298 | **−0.056** |
| steals | 0.188 | +0.122 |
| event composite | 0.217 | **+0.133** |

### 4.2 Three of the four acceptance criteria do not test the release

Every criterion was re-run against three published nulls: a **placebo** scoring every
player by his own team's rating (zero player information), a **circular** metric
(−player `DEF_RATING`), and deterministic **noise**.

| Criterion | Gate | Placebo scores | Verdict |
| --- | --- | --- | --- |
| A′ team-aggregate ρ | must beat steals' −0.374 | **−1.000** | **inadmissible** |
| A″ decile gap | ≥ 3.0 | **10.97**, 99 % of it team quality | **inadmissible** |
| change-on-change | — | **R² 0.904** | **inadmissible** |
| A‴ commit order | procedural | cannot be gamed by data | **valid, kept** |

A′ is degenerate by construction for a demeaned quantity: possessions are charged to five
on-court players, so the possession-weighted roster mean of on-court `DEF_RATING` **is** the
team rating, and aggregation destroys 94.7 % of the dispersion (player sd 8.66 → team
aggregate 0.455). Its sign even flips — **+0.342** demeaning against the team stat,
**−0.292** against a leave-self-out teammate mean — for a player-level quantity that is the
same to r = 0.998. That is an artefact, not a skill.

**A criterion a zero-information placebo wins by 2.6× is not an acceptance test.** They are
reported below, never gated.

### 4.3 What shipped, and what it achieves

Every term is z-scored within season, minutes-weighted. The differential is demeaned
against a **leave-self-out teammate mean**, and shrunk on **window** minutes.

```
def_impact = (teammate minutes-weighted mean DEF_RATING excluding self − player DEF_RATING)
             × m / (m + 5300)

team_defense = 0.10·z(def_impact) + 0.36·z(blk_per_min) + 0.27·z(stl_per_min)
             + 0.22·z(DREB_PCT)   − 0.05·z(pf_per_min)
```

| Criterion | steals proxy | **team_defense** | null floor |
| --- | --- | --- | --- |
| Stability, year-over-year (n = 391) | 0.669 | **0.838** | 0.370 |
| Incremental validity, partial (n = 391) | 0.106 | **0.126** | ~0.090 |
| A″ decile gap (n = 815) *(reported)* | 3.55 | **4.50** | 10.97 |
| …of which team quality rather than player | 1.51 | **0.99** | 10.88 |
| A′ *(reported, inadmissible)* | −0.374 | **−0.499** | −1.000 |

The plan's 0.60-impact blend scores 0.419 on stability — barely above the placebo's 0.370.

**`K = 5300` is documented as arbitrary within a wide band.** Every value from 1,000 to
20,000 gives the same answer to three decimals (composite reliability 0.860 → 0.859). Only
`K = 0` behaves differently. There is nothing there to tune.

### 4.4 The weights are chosen by construct, not by the numbers above

Adversarial verification established that the criteria cannot tell a defensive statistic
from an offensive one. Holding the vector fixed and swapping only the 0.22 term for
`TS_PCT` — true-shooting percentage, no defensive content whatsoever — **beats** `DREB_PCT`
on every non-circular criterion:

| Criterion | `DREB_PCT` | `TS_PCT` |
| --- | --- | --- |
| A′ | −0.499 | −0.542 |
| A″ | 4.50 | 5.23 |
| lagged team fit, ρ | −0.309 | −0.377 |
| …partial t | −1.84 | −2.58 |
| …leave-one-team-out gain | +0.013 | +0.054 |

So the table in 4.3 is evidence the composite is **not worse** than the steals proxy on
what anyone has managed to measure. It is not evidence the weights are right. Every term is
included because it is a defensive act; `TS_PCT` is excluded despite scoring better, which
is what construct validity is for.

### 4.5 The point-of-attack claim is withdrawn

A `point_of_attack_defense` composite was built (0.15 impact, 0.60 steals, −0.25 fouls) and
its weights committed before any named-player check, per A‴. It then **failed** its
pre-registered class check — high-usage, high-assist, sub-6′8″ players with ≥ 1500 window
minutes, n = 20, the exact population the tool used to overrate:

| Metric on the class | mean | above 0.50 |
| --- | --- | --- |
| pre-R4 steals proxy | 0.611 | 70 % |
| **new PoA composite** | **0.630** | **75 %** |

It was **worse than what it replaced**. Dončić moved 0.843 → 0.858.

A‴ says the response to a failed check is not to tune until it passes. The claim was
withdrawn instead: `point_of_attack_defense` is gone from `SKILL_KEYS` and
`NEED_TO_SKILL`, and the tool no longer asserts that acquiring anyone improves on-ball
defence — the audit's headline finding, which a reweighted proxy would have restated in a
new costume. The `poa_defense_score` column was deleted too; a computed-but-unread
defensive score invites wiring it up later without re-running the check that rejected it.

The team-side need is still measured and still shown. `fit_score` reports it under
`needs_without_a_skill`, `_fit` attaches the reason from `UNADDRESSABLE_NEEDS`, and the UI
states that the weakness is measured and why nothing is being claimed about it.

**On-ball defence needs the matchup and tracking data deferred to R6.** No reweighting of
steals, fouls and an on-court differential reconstructs it.

### 4.6 Face validity — reported, never gated

Run after `20986d7` fixed the weights. Top and bottom ten by `team_defense`, ≥ 1500 window
minutes:

- **Top:** Wembanyama, Jonathan Isaac, Matisse Thybulle, Paul Reed, Anthony Davis, Walker
  Kessler, Mitchell Robinson, Goga Bitadze, John Konchar, Chet Holmgren
- **Bottom:** Cam Thomas, Doug McDermott, Jalen Brunson, Nick Smith Jr., Tim Hardaway Jr.,
  Corey Kispert, Anfernee Simons, Keyonte George, Harrison Barnes, Jordan Clarkson

**Stated because it is not a clean win:** the composite is big-biased — blocks and
defensive rebounding carry 0.58 of the weight — and its `DREB_PCT` term correlates 0.907
with the input of the separate `rebounding` skill, giving a 0.579 overlap between two
skills. Dropping it would cut the overlap to 0.280, but the only evidence that dropping it
costs anything comes from criteria just shown to be undiscriminating, so there is no
measured basis for either choice. It stays, and the overlap is disclosed.

---

## 5. R4-1d — shooting volume and shrunk accuracy

`shooting` was `0.5·pct(fg3a_rate) + 0.5·pct(TS_PCT)`, answering both
"we do not shoot enough threes" and "we do not shoot them well" with one number.

**Volume is attempts per minute, not 3PA/FGA.** Against team 3PA per game — the quantity
the `three_point_volume` need is actually built from — attempts-per-minute tracks at
ρ **+0.845** and 3PA/FGA at **+0.754**, a bootstrap difference of +0.093 [+0.016, +0.178].
3PA/FGA is shot *selection*.

**Accuracy is empirical-Bayes shrunk before it is ranked.** 635 of 1714 player-seasons
(37.0 %) have under 50 attempts and 219 sit at exactly 0.000 or ≥ 1.000. Three independent
estimators agree on the constant: method-of-moments **272.5**, MLE **297.2**, out-of-sample
log-loss optimum **326** → **k = 300 attempts**, league mean **0.3618**, blended 0.7/0.3
with true shooting.

Measured on the 632-player window frame: 610 carry accuracy, the 22 with no attempt record
have it **withheld** rather than handed the prior, and **zero** sit at a degenerate extreme
where the unshrunk window percentage put 33.

---

## 6. R4-1e — every new feature reaches the served frame

`recency_weighted_features` keeps only `MODEL_FEATURES`. On the real database the season
frame carried 49 columns and the window frame 25 — 27 dropped silently, `DEF_RATING`,
`FG3A` and `POSS` among them. A skill on a dropped column resolves for nobody, with no
error and no failing test. That is the C7 trap.

Added: `PF` and `FG3M` (neither was read at all), `pf_per_min`, `fg3a_per_min`, and
`team_id` — which `features.py` never selected, so the module had no team context.

**Two quantities are derived after the collapse**, because shrinking per season and then
averaging is a different operation from shrinking the window:

| Quantity | Correct | Shrink-then-collapse | Effect |
| --- | --- | --- | --- |
| `def_impact` sd | **0.676** | 0.398 (1.70×) | 263 of 632 players move > 5 percentile points |
| `fg3a_window` | recency-weighted **sum** | a mean | a mean is a rate, not evidence |

Both live inside `recency_weighted_features` rather than at either call site, so `train.py`
and the request-path `_skills()` cannot diverge.

**Production frame health**, all nine skills:

| Skill | coverage | distinct | sd |
| --- | --- | --- | --- |
| `shooting_volume` | 632 | 609 | 0.290 |
| `shooting_accuracy` | 632 | 632 | 0.257 |
| `creation` | 632 | 614 | 0.289 |
| `turnover_avoidance` | 632 | 588 | 0.289 |
| `team_defense` | 632 | 632 | 0.289 |
| `rim_protection` | 632 | 616 | 0.289 |
| `rebounding` | 632 | 602 | 0.270 |
| `size` | **583** | 19 | 0.289 |
| `scoring` | 632 | 632 | 0.289 |

632 scored, 0 without a vector, 49 without `size` (no listed height). The gate's
`sd > 0.05` was replaced: a clean percentile over 632 players has sd 0.289 *by
construction*, so 0.05 is more than five times too loose, and both a binary skill (sd 0.31)
and a column that is zero for 90 % of players (sd 0.26) clear it. The bar is now coverage
≥ 0.90, sd ≥ 0.15, maximum tie mass ≤ 0.15 and effective distinct values ≥ 10.

**A live deploy hazard was fixed on the way.** The skills cache key was namespaced only on
the data version, which ingestion bumps and a deploy does not — so a release changing the
skill contract would have served the previous shape for the rest of the six-hour TTL, with
no error, and could not reproduce locally because the in-process fallback dies with the
process while Redis does not. The key now carries a fingerprint of the declared keys, the
vector function and the feature list.

---

## 7. R4-3 — k-means was unstable, not merely imprecise

Measured on the real 632-player frame:

| | k-means | **rule chain** |
| --- | --- | --- |
| Branches ever reached | **5 of 10** | **14 of 14** |
| Largest label share | 30.7 % | **12.18 %** |
| Smallest real label | — | **3.48 %** |
| Rows with a numeric suffix | **217 (34.3 %)** | **0** |
| Herfindahl | 0.238 | **0.0797** |
| Silhouette | 0.154 | n/a — nothing is fitted |
| **Label churn when 10 % of players drop** | **65.7 %** (ARI 0.647) | **1.77 %** (max 3.17 %) |
| Byte-identical across runs | no (distance drifts with BLAS threads) | **yes** — in-process, row-permuted, and a separate process at `OMP_NUM_THREADS=3` |
| Players whose height was fabricated | **49 (7.75 %)** | 0 — labelled `unclassified` |

The churn figure is the decisive one and nothing had measured it. A label that changes two
times in three when the population moves slightly is a property of the run, not of the
player — and it is persisted per player-season and shown on the player page.

*The plan's figures (35.9 % max share, 249 suffixed, Herfindahl 0.261) did not reproduce;
they are 4–5 points pessimistic. The measured values above are used.*

**Size gates first**, deliberately: a creation-first chain was measured to label
Wembanyama a secondary creator. Thresholds are league percentiles recomputed from the
scored frame — scaling league-wide `fg3a_rate` by 1.25 changes zero labels.

Face validity, three highest-minute players per role: lead guard *Brunson, Maxey, Fox* ·
point-of-attack guard *DiVincenzo, Wallace, Dunn* · primary wing creator *DeRozan, Harden,
Gilgeous-Alexander* · 3&D wing *Camara, Caldwell-Pope, Green* · stretch big *Porter Jr.,
Lopez, Reid* · rim-protecting big *Gobert, Claxton, Jackson Jr.* · playmaking big *Durant,
Jokić, Adebayo*. Pure height tiers put Durant and Jaden McDaniels in big roles, which is
the cost of gating on size first and is reported rather than patched.

`player_archetypes.cluster_id` → `role_id` (frozen, append-only, stable across retrains)
and `distances` → `role_inputs`, via migration `d3e5a71b9c02`, verified to apply and
reverse cleanly on a fresh database.

---

## 8. R4-4 — four discontinuities, and one the plan had wrong

| Defect | Before | After |
| --- | --- | --- |
| `age_delta` at the age-30 boundary, 4-year projection | **0.70 TEI** for two days of age (0.59 sd of the TEI distribution) | **< 0.02** |
| `timeline_alignment`, worst one-year swing | **0.35** → 35 points of a 0..100 component | **≤ 0.15** |
| …collapse to exactly 50.0 | 24.9 % (contend) – 39.5 % (rebuild) of realistic pairs | halved |
| `needs._percentile` | every percentile × **29/30**; league leader capped at **96.7** | **100.0** reachable |
| `allocate_rotation` | **39.14** minutes against a 36-minute cap, three players over; **24.0** against a 20-minute cap | cap never exceeded |

Both curves are the **linear interpolant of the previous step curve through its own bucket
midpoints**, so the trapezoid rule keeps them area-preserving: total drift over ages 18–42
is −4.651 against the old −4.660, worst running-cumulative discrepancy 0.126 TEI. Nothing
new is asserted about magnitude; only the steps are gone.

**Two of the plan's characterisations were wrong:**

1. The plan feared the age-curve change would invalidate R3's calibration. `age_delta` and
   `project_tei` have **zero production callers** — only `timeline_alignment` is wired in —
   so the curve `docs/methodology.md` documented as product behaviour was dead code.
2. The plan recorded the cap-redistribution loop as **unreachable**. It is not. It fires on
   realistic rosters, and because each pass *ends* on the redistribution with no re-clip,
   whatever it added back could leave a player above his ceiling and stay there. Equal
   baselines hide it entirely, which is why its guarding test passed. Water-filling
   replaces it: terminates in at most one pass per player, cannot exceed a cap, and leaves
   a genuinely infeasible shortfall unallocated so it flows to the replacement-level term.

**C13 confirmed exactly, against the audit's reading.** The collapse to 50.0 reproduces
only under `contend`. The default strategy is `custom`, `custom` resolves to the retool
shape, and the measured score is **20.0**. Bucket widths are 3 and 4 years, never 5.

**One definition of rotation depth.** Three cutoffs existed: `REPLACEMENT_TEI` fitted on
"outside the top 10", `_fit` taking the top **9**, and a **12**-row chart. The chart is a
display choice and is named as one; the other two are the same basketball claim and now
meet at `ROTATION_DEPTH = 10` — chosen because that is where `REPLACEMENT_TEI` is already
calibrated.

---

## 9. R3 recalibration — re-measured, not assumed

R4 changed the skill and feature path, so the coefficient could not be presumed to
survive. `make train` was re-run on the post-R4 code path against the ingested history:

| Diagnostic | Recorded at R3 | **Re-measured after R4** |
| --- | --- | --- |
| Coefficient | 14.977 | **14.976967** |
| Slope SE | 1.528 | **1.5279** |
| Slope t | 9.80 | **9.802** |
| R² | 0.6236 | **0.6236** |
| n | 60 | **60** |
| Per-fold slopes | 14.716 / 15.276 | **14.716 / 15.276** |
| LOTO OOS RMSE | 2.944 / 3.773 | **2.944 / 3.773** |
| …share of predicting zero | 56.6 % / 65.0 % | **56.6 % / 65.0 %** |

**It is preserved because the new measurement independently supports it, not because it
passed before.** The reason it holds is structural: R4 added columns to `MODEL_FEATURES`
and derived new post-collapse quantities, but touched neither `INDEX_WEIGHTS` nor
`Z_SOURCE_COLS`, so the regressor is the same construction.

That was a decision, and it was measured rather than assumed. Feeding the new defensive
term into TEI was tested and **rejected**:

| TEI variant | team-level R² | change-on-change R² |
| --- | --- | --- |
| **current weights** | **0.7505** | 0.6236 |
| replace the event trio with `def_impact` | 0.5655 | 0.4838 |
| events + `def_impact` at 0.10 | 0.7263 | 0.6297 |
| events + `def_impact` at 0.20 | 0.6753 | 0.5906 |

The demeaned differential degrades TEI on the level fit R3 validated — the same conclusion
the skill-side A′ measurement reached, from an independent direction.

**A gap in the R3 gate was closed.** Its central assertion —
`test_the_served_coefficient_matches_the_registered_fit` — **skips** when the database has
no registered fit, which is every CI run, so the most important check in the gate never
executed. `test_r3_gate_after_r4.py` adds 15 tests that do not skip: structural proof that
no R4 column entered the calibrated path, and machinery tests that the calibration reaches
the R3 thresholds on realistic signal and **fails** them on noise.

---

## 10. Frontend surfaces

Nothing in the stack was type-protected for skill keys, need keys or role labels:
`npx tsc --noEmit` exits 0 today and would have exited 0 after any rename.

- `SKILL_LABEL` replaces key-munging. `turnover_avoidance` reads "Ball security", not
  "Turnover Avoidance".
- `needs_not_addressable` renders, so a withheld need appears with its reason rather than
  vanishing.
- `ArchetypeAssignment.cluster_id` → `role_id`, matching the API. `tsc` would have passed
  while the field read `undefined` at runtime.
- The role Badge was `whitespace-nowrap` in a `max-w-sm` drawer; role labels reach 31
  characters where k-means labels topped out at 18. It wraps.
- The player page said "Archetype … assigned by clustering". Nothing clusters; it is a
  "Role", assigned by a rule chain.

**Threshold re-check** (the R4 gate's requirement), measured on the re-scored 30-team frame:

| | before | after |
| --- | --- | --- |
| Rows at `NEED_SEVERITY_THRESHOLD` 0.35 | 98 | **99** |
| Rows at `STRENGTH_PERCENTILE_THRESHOLD` 65 | 69 | **75** |
| Teams truncated by `MAX_ROWS = 4` | 8 | **8** |
| Rows in the [0.35, 0.40) band | **0** | **8** |
| Maximum reachable percentile | 96.7 | **100.0** |

Both thresholds stand. Worth recording: 0.35 was previously *indistinguishable* from 0.40,
because the 30-team grid quantised severity to multiples of 1/15 and no row ever fell in
that band. Excluding a team from its own peer group breaks the grid, so the threshold does
something for the first time.

---

## 11. QA evidence, and one gap stated plainly

| Check | Result |
| --- | --- |
| Backend suite, CI-equivalent with the coverage floor | **484 passed / 1 skipped / 1 xfailed**, coverage **78.15 %** (floor 68) |
| `ruff` + `mypy` over `app` and `tests` | clean, 82 source files |
| Frontend unit tests | **43 passed** (6 files) |
| `npx tsc --noEmit` · `eslint` | clean |
| Migrations from a clean database | `alembic upgrade head` through `d3e5a71b9c02`, and `downgrade -1` + re-upgrade, both clean |
| Full pipeline on a copy of the real database | `migrate` → `train` → `score` clean; 632 players labelled, 279 need rows |
| R3 release gate on the post-R4 database | **all 10 criteria met** |
| Playwright e2e | **5/5 passed** mid-session (after R4-1a/1b) — **not re-run after R4-1c onward** |
| Visual QA | **not run** |

**The browser gap is real and is not being glossed.** Partway through the session the
sandbox stopped allowing Node to bind a port: `next dev` and `next build` both start, sit
at 0 % CPU and never listen, so `make e2e` times out waiting for `config.webServer`. It is
the same restriction that makes `preview_start` fail with "Operation not permitted", and
nothing in this release caused it — e2e passed 5/5 including the full decision flow earlier
in the same session, on a demo database rebuilt through migrate + train + score.

So the skill split, the role labels, the wrapped Badge and the `needs_not_addressable` copy
are backed by unit tests, types and lint, but **no rendered page**. `make e2e` and
`make visual-qa` are the first two commands for the next session, and
`ROSTERLAB_AUTONOMOUS_STATE.md` says so at the top.

## 12. Deferred, with the reason

| Deferred | Why |
| --- | --- |
| Point-of-attack defence as a scored skill | Needs on-ball matchup data. No box-score composite passes its class check; measured, not assumed. |
| Validating any defensive metric | Every target in this repository derives from on-court `DEF_RATING`, so every available test is circular to some degree. Needs tracking data (R6). |
| Kaggle `nbadb` work | `data/external/` is still absent. Blocks lineup-aware fit only. |

## 13. Datasets used

Only what was already present: `player_season_stats` and `team_season_stats` for
2023-24 · 2024-25 · 2025-26 (1,714 player-seasons, 90 team-seasons), `players`, `rosters`,
`standings`. No new dataset was added and none was fabricated.
