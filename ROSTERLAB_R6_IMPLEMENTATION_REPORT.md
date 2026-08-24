# RosterLab R6 — Differentiation

*Branch `feat/rosterlab-autonomous-roadmap`, from the validated R5.5 boundary at `4f3bdf0`
through `623134f`. Nine commits, 54 files, +8,748 / −191.*

---

## 1. What R6 was for, and what it changed

R5.5 left a product that could score a trade you had already built, and could only answer
with its own model output. R6's brief was to make it useful and differentiated as a
decision-intelligence product rather than as a scoring engine.

Four things now exist that did not:

| | Before R6 | After R6 |
| --- | --- | --- |
| **Precedent** | none — no transaction history in the schema | 565 completed trades over ten seasons, retrievable from one team's side, with a per-dimension similarity breakdown |
| **Entry point** | build a trade, then find out if it is good | start from a diagnosed need and get named targets, each already run through the trade evaluator with a balancing package |
| **Roster consequences** | a rotation table of twelve names | minutes by player role before and after, against the league's own distribution, with the roles that got congested or lost |
| **The artifact** | a nine-section report, for saved trades only | a decision memo for any deal — including precedent, draft-capital cost, rotation consequences, and one consolidated section naming everything it could not establish |

Nothing in R3, R4, R5 or R5.5 was reopened. Every R3 calibration figure is bit-identical
(§9).

---

## 2. Comparable historical trade retrieval (R6-1, R6-2)

### 2.1 The dataset, and how it was acquired

`nba_api` publishes no transaction history, and none was present locally: `data/external/`
did not exist, and the Kaggle `nbadb` copy on this machine ends **2023-06-12** — before the
first season this product models.

The source is **Basketball-Reference season transaction pages**,
`/leagues/NBA_<year>_transactions.html`. This is the repository's first fetcher, and it
exists because ten pages is too many to save by hand and they change as a season advances.
It reads its constraints from the source's own published policy rather than assuming them:
`robots.txt` allows `/leagues/` for `User-agent: *` and publishes `Crawl-delay: 3`, so
requests are **3.5 seconds apart**, one per season page, following no links, under a user
agent that names the project. A `provenance.json` sidecar records each page's URL, HTTP
status, byte count, SHA-256 and retrieval timestamp.

Raw pages live in `data/imports/transactions/`, **gitignored in full** and never
redistributed. Only normalized rows enter the database. The commit contains exactly three
data-adjacent files: a hand-written synthetic test fixture, the drop-zone README, and a
`.gitkeep`.

**Verified before use:** provenance (URL + SHA-256 per page), schema (one `<li>` per date,
one `<p>` per transaction, `data-attr-from` / `data-attr-to` carrying three-letter
abbreviations), date coverage (2016-17 … 2025-26), identifiers (Basketball-Reference
player slugs, retained), missingness (5 unreadable asset phrases in 2,364), multi-team
representation ("In a N-team trade, …" with semicolon-separated legs), pick and protection
representation (trailing notes in the source's own words), licensing (raw pages stay
local), and compatibility with RosterLab identities (three franchise aliases, no fuzzy
matching).

### 2.2 What the corpus contains

```
trade paragraphs                565        parsed 565, unparsed 0
multi-team                       69        3 teams x51 · 4 x13 · 5 x3 · 6 x1 · 7 x1
asset legs                    2,568        players 1,500 | picks 859 | cash 209
player legs resolved          1,341        89.4 %; 157 absent, 2 ambiguous
pick conveyance                            580 unconditional | 194 swap | 44 protected | 41 conditional
asset phrases unparsed            5        of 2,364, kept verbatim and filed as warnings
note bindings ambiguous          85        of 859, attached to both picks rather than one
franchise abbreviations           0        unresolved (BRK/CHO/PHO aliased explicitly)
```

The 159 unresolved player legs are almost entirely draft-rights players who never appeared
in an NBA game. `Mike Dunleavy` is the one genuinely ambiguous name, and it is reported as
ambiguous rather than resolved by picking.

### 2.3 Three parsing decisions, each a measured failure first

**A player named inside a pick annotation is not a traded player.** The source writes
"a 2026 2nd round draft pick (Jack Kayil was later selected)". Counting those anchors
inflates the 2025-26 page from 128 real player legs to 184 anchors, and puts a rookie on
the wrong side of a trade that happened before he was drafted. The annotation is captured
as `later_selected` metadata on the pick.

**The sentence/notes boundary is structural, not typographic.** Splitting on a period
followed by two spaces reads 2022-23 onwards and fails on everything before it — 214 asset
phrases with a note glued on, and **every pre-2022 pick classified unconditional** because
its conditions were never seen as notes. The sentence ends at the first period at or after
the final receiving team that is outside a parenthesis **and** outside a name; both shields
are load-bearing, for `Vince Williams Jr.` and for `(Tyrell Terry was later selected)`.

**A qualifier belongs to the pick that follows it.** "conditional 2028 2nd-rd pick is DEN
own" — cutting at the year orphans the qualifier and classifies the pick as the one thing
it is not. Restoring it moved 15 pick legs out of `unconditional`.

### 2.4 The similarity methodology

**The retrieval unit is a side, not a trade.** "Boston traded Marcus Smart for Kristaps
Porziņģis" and "Washington traded Kristaps Porziņģis for Marcus Smart" are one transaction
and two decisions. A three-team trade contributes three sides; a result list returns at
most one side of any transaction, and both remain in the corpus.

Sixteen features in six dimensions; each dimension's distance is the mean over the features
**both sides state**, and the total is the weighted mean over the dimensions that survive:

```
d(a, b) = Σ_g w_g · d_g(a, b) / Σ_g w_g
d_g     = mean over f in g of  |a_f − b_f| / (|a_f − b_f| + scale_f)
```

| dimension | w | features |
| --- | --- | --- |
| `player_value` | 0.30 | value in, value out, best player in, best player out |
| `draft_capital` | 0.25 | net unconditional firsts, net conditional firsts, net seconds, picks in, picks out |
| `structure` | 0.20 | players in, players out, teams involved |
| `age_profile` | 0.10 | minutes-weighted age in, age out |
| `team_context` | 0.10 | win percentage, gap to the other side |
| `timing` | 0.05 | in-season or offseason |

**Nothing is truncated.** `|Δ|/(|Δ|+s)` is bounded, monotone and scale-free — R5-1a's
finding applied again; a hard clip at one scale unit put 41 % of corpus pairs on the
ceiling, and the ordering above the ceiling is what the question is about.

**Counts get a declared unit; continuous quantities get the corpus's interquartile range.**
Estimating the pick scales was tried first and degenerates: 295 of 337 rankable sides
receive no first-round pick, so the IQR is zero, the MAD is zero, and the chain falls
through to the standard deviation — the tail-driven statistic the construction rejects for
exactly those columns.

**Both halves are built by one function.** `services/comparables.py::_side` is the only
place a `TradeSide` is made. A retrieval engine whose query and corpus are constructed
differently measures the construction, not the trades;
`test_query_and_corpus_sides_are_built_by_one_function` asserts that a proposal identical
to a completed trade produces an identical feature vector.

**What the similarity deliberately excludes**, each named in the response:
*salary* (no source here carries a historical contract, so scoring the query's money would
compare a number against nothing), *cash and trade exceptions* (the corpus states both, a
proposal states neither, so the feature could only penalize the 37 % of completed trades
that include one), and *the outcome* — nothing reads what happened next.

### 2.5 Two construction choices the measurements forced

**Draft capital had to become directional.** The first version carried `firsts_in/out`,
`seconds_in/out` and a direction-free `picks_moved`. With 295 of 337 sides at zero firsts,
four of five features were 0-vs-0 on nearly every pair, and agreement on a value nobody has
diluted the one fact that mattered: a query sending a star for three firsts scored 84 %
similar on draft capital against a trade that moved one second. The same direction-free
features made every side resemble its own mirror — 0.714 mean similarity to a reversed copy
against 0.672 between unrelated sides.

**Protections had to become a count, not a share.** After the first fix, attaching a top-4
protection to a query's first-round pick returned the **identical** top five, overlap
1.000. The arithmetic is small enough to state: `conditional_pick_share` was one of five
features in a dimension weighted 0.25, so flipping it 0→1 could move the total distance by
at most 0.25 × (0.667/5) = **0.033**, against a corpus whose pairwise similarity spans p05
0.521 to p95 0.873. A protected first is not the same asset as an unconditional one — R5-2
refuses to price it at all — so `firsts_net` was split into
`firsts_net_unconditional` / `firsts_net_conditional`.

Measured after that change, on a one-for-one player trade:

| query change | top-5 overlap with the base query |
| --- | --- |
| +1 unconditional first vs no picks | 0.429 |
| +1 second vs no picks | **0.000** |
| +1 first vs +1 second | 0.250 |
| 1 first: unconditional vs **protected** | **0.667** (was 1.000) |
| 1 first: unconditional vs **swap** | 0.667 |
| 1 first: protected vs swap | 1.000 — deliberate; one class |

---

## 3. Comparable-trade validation

`make comparable-validation` — leave-one-out over all 337 rankable sides, k = 5, statistic
throughout is **top-5 Jaccard overlap**, because that is what a user sees: not the
distance, the list. The command exits non-zero on a stated threshold.

| check | measured | gate | |
| --- | --- | --- | --- |
| **Stability** — ±10 % of each feature's own scale, both directions, n=674 | **0.648** | ≥ 0.60 | ✅ |
| **Scale form** — standard deviation instead of IQR | **0.735** | ≥ 0.50 | ✅ |
| **Scale form** — min-max | 0.471 | reported | null |
| **Distance form** — hard clip instead of saturation | **0.717** | ≥ 0.50 | ✅ |
| **Single-dimension null** — best of six | **0.089** | ≤ 0.75 | ✅ |
| **Archetype recovery** — lift over a shuffled-feature corpus | **0.392** | ≥ 0.10 | ✅ |
| **Direction confusion** — selling retrieved as buying | **0.019** | ≤ 0.05 | ✅ |

**Archetype recovery against two nulls.** Five structural classes (`sold_value_for_firsts`,
`bought_value_with_firsts`, `player_for_player`, `second_round_trade`,
`no_measurable_value`), 246 labelled sides:

| | precision@5 | base rate |
| --- | --- | --- |
| the shipped distance | **0.797** | 0.414 |
| random ranker | 0.397 | 0.414 |
| corpus with feature vectors permuted between sides | 0.405 | 0.414 |

Both nulls land on the base rate, which is what a null must do. **This measures internal
consistency, not external validity** — the classes are built from the same features the
distance reads, and nothing in this repository labels two trades as similar, so external
validity cannot be measured here.

**Leave-one-dimension-out.** Draft capital drives the list hardest (0.313 overlap without
it), then player value (0.343) and structure (0.374); age profile (0.701) and timing
(0.707) barely matter. That is the direct answer to "impact of picks and protections":
picks matter most of anything.

**Sensitivity to weighting, reported honestly.** Uniform weights change 57 % of the list
(0.430 overlap). The weights are chosen by construct, not fitted, because there is no
target to fit them against. What *is* established is that no single dimension reproduces
the ranking (best 0.089) and that the per-dimension decomposition is returned with every
result, so the choice is inspectable rather than hidden.

**Era.** The rankable corpus is entirely inside the 2023 CBA, so an era term in the
distance would be a constant — and scoring a constant is not a measurement. Era is instead
measured across all 1,225 ingested sides, where it is real:

| | 2017 CBA (829 sides) | 2023 CBA (396 sides) |
| --- | --- | --- |
| picks per side | 1.317 | **1.581** |
| share of moved firsts carrying a protection or swap | 0.379 | **0.600** |
| multi-team share | 0.163 | **0.247** |

That is why restricting the ranked corpus to one CBA is a feature rather than only a
limitation: a 2019 comparable is a comparable under different rules.

**Neighbours are not a date lookup.** Same-season share 0.382 against a 0.348 base rate.

**One criterion was replaced, not waived — and not because it failed.** The battery
originally asserted that an asymmetric side must resemble its own mirror **less** than two
unrelated sides resemble each other. It did fail when it was written, at 0.679 against a
0.672 median. It was replaced because it does not test *retrieval*: similarity **levels**
compress into p05 0.521 … p95 0.873, so hundredths of level are not evidence about a list.

The clearest illustration is that the same statistic now sits at **0.676 against a 0.685
median** — it would pass — purely as a side effect of the pick-conveyance split, which was
made for an unrelated reason. A criterion that flips on a change made elsewhere is not
measuring what it claims to.

By list, the mirror is far: injected into the corpus it is the nearest neighbour for **2 of
141** asymmetric sides, reaches the top five for 11, and sits at **median rank 89 of 338**.
Direction confusion measured on real trades replaces it, at **0.019** — of the neighbours
returned for a side that sold on-court value for firsts, 1.9 % are sides that bought it.
Both figures are still reported.

**Structurally different trades are not considered close.** The confusion matrix over the
five classes is strongly diagonal, and the two opposite classes are near-orthogonal:
`bought_value_with_firsts → sold_value_for_firsts` is **0.000**.

---

## 4. Need-driven acquisition (R6-3)

`GET /teams/{id}/acquisition-targets` runs diagnosis → need → candidates → fit → cost → an
evaluated trade. Every link reuses a validated system; nothing new is fitted.

**Two rules, both printed in the response, deliberately not merged.**

- *Filter*: the player's percentile in the skill that addresses the chosen need must exceed
  the acquiring roster's own level in that skill — its third-best rotation value, the same
  definition `_fit` uses for "already strong here".
- *Rank*: the projected win change from adding him, before anything leaves.

Ranking on `fit` was rejected for a reason `_fit`'s own docstring already records:
`fit_score` normalises minutes within each side, so "acquiring an 8-minute player who
answers a need scores like acquiring a 32-minute one". A blended score was rejected because
the weight between need and impact cannot be fitted — nothing here labels a target as good.
`sort=need` reorders instead.

**Feasibility is what makes it a target list rather than a leaderboard.** Ranking by
projected wins alone gave all 30 teams the same names: **26 distinct players across every
team's top five**. Each candidate is now put through the trade evaluator with a package
that balances its modelled value, and kept only if it clears the conditions
`generate_candidates` already commits to — both sides above 50, neither worse than −2
projected wins, not verified illegal. The constants are *imported* from that module, so the
two features cannot disagree about what a front office would accept.

    distinct players across the league's top fives      26 → 72
    trades actually evaluated across 30 teams        1,243
    rejected: counterparty below neutral               445
              focal below neutral                      389
              verified illegal                         232
              projected win loss                        29
              no balancing package                      23

### Validation across team types

`make acquisition-validation`. Team types are classified from **measured** quantities, never
from a label: win-percentage tertile, the top two players' share of a roster's
above-replacement value, and the skill family of the most severe addressable need.

| check | measured | gate | |
| --- | --- | --- | --- |
| Need filter differentiates (distinct-player ratio, filtered ÷ unfiltered) | **2.77** | ≥ 1.5 | ✅ |
| Same-need teams hear more alike than cross-need teams | **+0.090** | ≥ 0.05 | ✅ |
| ...but not identical (same-need overlap) | **0.113** | ≤ 0.9 | ✅ |
| Every returned target improves its need | **1.000** | = 1.0 | ✅ |
| Shuffled-need null — a team re-run with another team's need | 0.160 | reported | |

Cross-need overlap is 0.023 against same-need 0.113. Re-running a team with another team's
diagnosed need changes **84 %** of its list, so the need is what decides it.

The recommendations follow the basketball:

| weakness | teams | distinct targets | most common |
| --- | --- | --- | --- |
| size / rebounding | 10 | 23 | Bitadze, Holmgren, Reed, Gafford |
| creation | 10 | 32 | Şengün, Avdija, Flagg, Spencer |
| shooting | 8 | 27 | Miller, Sensabaugh, White, Flagg |
| defence | 1 | 3 | Thompson, Jackson, Ware |

| direction | teams | distinct targets |
| --- | --- | --- |
| contender | 9 | 33 |
| middle | 9 | 31 |
| rebuilding | 11 | 34 |

| concentration | teams | distinct targets |
| --- | --- | --- |
| balanced | 11 | 38 |
| middle | 9 | 32 |
| star-heavy | 9 | 32 |

**San Antonio returns unavailable, and that is the R4-2 withdrawal reaching the product.**
Its only measured weakness on the ingested data is point-of-attack defence, which R4-2
withdrew every player-side claim over. The response names the need and quotes the reason
rather than returning an empty list.

**Restrictive salary situation, tested with contracts present.** The dev database has no
contracts, so salary matching is `unavailable` league-wide. Re-run on a scratch copy with
the Basketball-Reference snapshot imported (886 rows, 392/530 rostered players priced), the
battery still passes — differentiation ratio **3.04** — and the recommendations change:
`focal_utility` rejections fall 389 → 334 while `counterparty_utility` rejections rise
445 → 493, because the `contract` component now scores. Salary figures appear per target
(Curry $62.6 M in, requiring ≥ $49.9 M out; Kennard $6.06 M in, requiring ≥ $2.9 M).

**Limited draft capital is *not* a lever in this path, and the report says so rather than
claiming a test.** The acquisition workflow proposes player-for-player packages only, so a
team's pick inventory cannot change its target list. Draft capital is a first-class
dimension in comparable retrieval, where leave-one-out shows it drives the neighbour list
harder than anything else, and it is scored in the evaluator's `assets` component. Making
picks part of a suggested package is named as an R7 item (§13).

---

## 5. Lineup-aware fit: deferred, on measurement (R6-4)

The obvious answer — "the data is missing" — is **not true**. `nba_api`'s
`LeagueDashLineups` is reachable and returns real five-man data. So the samples were
measured instead of assumed. 2024-25, `Totals`, the top 2,000 groups by minutes:

| group size | groups | median minutes | share ≥ 200 min | implied sd of net rating |
| --- | --- | --- | --- | --- |
| 2 | 2,000 | 376.9 | 88.4 % | 3.7 per 100 |
| 3 | 2,000 | 249.4 | 66.6 % | 4.6 per 100 |
| 5 | 2,000 | **20.2** | **1.6 %** | **16.1** per 100 |

(`sd = 100 · 1.05 / √possessions`, possessions = 2.1 × minutes; both constants stated, not
fitted — the conclusion does not turn on their third digit.)

At five-man level the estimate is **noise**: 16 points per 100 against a league team spread
of roughly ±10, and that is the median of the *top* 2,000 groups, not of the population.
Two- and three-man groups are estimable and still do not give a **trade** fit model, for a
reason no sample size fixes: a trade prices combinations that have never played together, so
observed groups can only support a synergy model, and nothing here holds a held-out target
to validate one against. Any target built from on-court net rating is also the circularity
R4-2 already withdrew a claim over.

Two independent confirmations: the local Kaggle `nbadb` play-by-play ends **2023-06-12**,
before the first season this product models; and Basketball-Reference's `robots.txt`
disallows `*/on-off/` and `*/lineups/` outright.

`make lineup-availability` re-runs the whole measurement and stores nothing, so the
deferral is falsifiable rather than permanent.

### What was built instead

**Roster composition** — `detail.roster_shape` on every evaluation: minutes by player role
before and after, from R4-3's deterministic roles and the **same** R5.5 allocation the
projection used, never re-derived. A role is congested when its post-trade minutes exceed
the 90th percentile of that role across the 30 ingested teams, computed from each team's own
allocated rotation; every team contributes a zero for a role it does not hold, so a rare
role's threshold is not high *because* it is rare.

Dallas trading Gafford for Towns: glass-cleaning big **19.2 → 37.6** minutes against a
league median of 12.3 and a 90th percentile of 29.3 — congested — while rim protection falls
**35.0 → 21.2**. The block states in its own text that it is not lineup data and makes no
claim about on-court synergy.

---

## 6. Decision memo / export (R6-5)

`POST /trades/memo` (markdown / HTML / JSON) and `GET /trades/{id}/report`, through one
builder so a saved trade and an unsaved one cannot become two documents that disagree. The
memo existed only for saved trades, which meant the document a front office circulates could
not be produced for a deal someone was still building.

Sections: **Recommendation · 1. What changes on the floor** (projected wins with its
calibration provenance, the Monte-Carlo interval, who arrives and leaves, and the rotation
consequences) **· 2. Does it fit this roster** (needs addressed, what it duplicates, the
one-way baseline where a side is empty) **· 3. What it costs** (payroll, and draft capital
priced and unpriced separately) **· 4. Rules · 5. Precedent · 6. Risks · What is not known ·
Alternatives · Questions this product cannot answer · Assumptions and provenance**.

It is deliberately not a dump: roles are tabulated only when their minutes move by at least
2 of 240; three comparables, not twenty-five; the top three components by distance from
neutral.

**"What is not known" is the section that makes it a front-office document.** On a live
Dallas-for-New-York deal it collects eight entries — the lineup-fit deferral, a measured
weakness no player skill addresses, unavailable contract data, an unpriceable 2029 first,
five CBA checks that could not reach a verdict, the fields the comparable retrieval does not
score, and two excluded components. Every one of those facts existed before R6; none of them
was ever collected in one place.

`test_no_section_renders_empty` pins the rule that motivated it: an empty section reads as
"nothing to say here", which for a cost section that could not be computed is the opposite
of the truth.

---

## 7. Product surface

- **Precedent tab** in the trade evaluator, mounted only when selected so the 337-side
  search runs on demand. Each comparable shows its per-dimension similarity, because 0.74
  reads as a grade until you can see draft capital agreeing at 100 % and on-court value at
  42 %. "Resemblance is not consequence" is in the panel's own text.
- **Rotation consequences** in the Impact tab, with the lineup-fit deferral stated where the
  reader is looking.
- **"Who fixes this?"** on team outlook: choose a need, get targets, expand one for cost, the
  suggested package, the evaluated verdict for both teams, and a link that opens that exact
  deal in the evaluator.
- **"Open decision memo"** in the evaluator's action rail.

Three defects found by driving it: both sides of one completed trade taking two of five
slots (fixed by returning at most one side per transaction); `"Blocks per game is in the 3th
percentile"` (a missing ordinal in `needs.py`, quoted verbatim by three surfaces); and the
evaluator's share-state encoding being private to its page, so the acquisition panel's deep
link was built to a format that would have opened an empty builder with no error.

---

## 8. Tests and QA evidence

```
backend pytest              869 passed · 1 skipped · 1 xfailed     (was 748)
backend coverage            88.43 %, floor 85                      (was 88.24 %)
frontend vitest              45 passed                             (was 43)
ruff · mypy (96 files) · eslint · tsc          clean
production build            13 routes, TypeScript clean
migrations                  clean DB → head, head → base, base → head, `alembic check` no drift
Playwright                    5 passed
visual QA                    98 screenshots, 7 viewports — no overflow, no console errors, no empty pages
adversarial scenarios      20 / 20
```

121 new backend tests across eight files. The properties that matter most:

- the query side and every corpus side are built by one function;
- an explanation may only name a driver the arithmetic had — `contributions()` is the sum
  that produced the similarity, and the sentences follow it in order;
- the "least alike" line names the least *similar* dimension, not the smallest *term* — a
  contribution is weight × similarity, and ranking on it produced the live sentence "Least
  alike on timing (100 % similar)";
- a player whose evidence is missing withholds a side; a player who had never played
  contributes zero, which is a measurement;
- no memo section renders empty;
- the league role reference does not scale with the number of teams.

**Adversarial and unusual scenarios, all 20 correct:** an empty trade (refused, with the
reason), picks-only, a three-team query, a whole roster moving one way, a far-future
protected pick, a focal team not in `team_ids` (400), `k` out of range (422), a team whose
only need no skill addresses (unavailable, naming the need), an unknown need (400), a bad
sort (400), limits of 0 and 999 (clamped), unknown team and unknown scenario (404), a memo
for an empty trade, a memo for a roster-overflow illegal trade (no score, rules named), and
the JSON and comparables-suppressed memo formats.

**Found while wiring, and fixed:** the test suite was about to make real requests to
Basketball-Reference and NBA.com on every `pytest` run, because
`test_every_documented_command_is_reachable` executes every command in the CLI docstring.
`ROSTERLAB_OFFLINE=1`, which the suite now sets, makes the two fetching commands refuse.
The same test read `exit_info.value.code` on a caught `SystemExit`, which has no `.value`;
it had never fired only because no documented command happened to exit on a machine with
every optional snapshot present.

---

## 9. Upstream gates re-run

**R3 / R5.5, re-measured on the live database after R6 — every figure bit-identical:**

| criterion | gate | post-R6 | at R5.5 |
| --- | --- | --- | --- |
| Coefficient | — | **14.976967215546017** | 14.976967 |
| Slope significance | t > 5 | **9.802066683060602** | 9.802 |
| LOTO out-of-sample RMSE | < 4.5 | **2.944 / 3.773** | same |
| …as a share of predicting zero | < 75 % | **56.6 % / 65.0 %** | same |
| Per-fold slopes vs pooled | ±15 % | **14.716 / 15.276** | same |
| Served constant matches the fit | ±2 % | **14.977 vs 14.977** | same |
| R² · n | — | **0.6236 · 60** | same |
| Roster-gut (whole roster) | < 25 on all 30 | **max 9.72**, 0 ≥ 25 | max 9.72 |
| QA-1 strip the best three | < 25 on all 30 | **max 23.06**, 0 ≥ 25 | 23.06 |
| Distinct band widths | > 400 of 512 | **510 of 512** | 510 |
| Band width monotone in minutes | ρ < −0.95 | **−1.0000** | −1.0000 |
| Above-replacement giveaway never gains | 0 violations | **0 of 370** | 0 of 370 |
| Performance boundary ties | 0 | **0 of 370** | 0 |

It holds for a structural reason worth stating: R6 added a *reported* block to the
evaluation response and changed no scored quantity. The `needs.py` ordinal fix touched only
explanation strings — re-running `make score` changed 279 explanations and **zero**
severities, percentiles or impact estimates.

**R5-3 generator gate, re-run:** 29 of 29 counterparties searched, 406 evaluations, 8
candidates, all with both sides above 50 and no package gap beyond 2 projected wins.

---

## 10. Performance

| path | queries | seconds |
| --- | --- | --- |
| `POST /trades/evaluate` (2-for-2, cold cache) | **17** | 0.55 |
| …one team, cold / warm | 8 / **6** | 0.53 / 0.01 |
| `POST /trades/generate` (focal DAL) | 322 | 0.29 |
| `POST /trades/comparables` | **7** | 0.20 |
| `GET /teams/{id}/acquisition-targets` | 70 | 0.55 |
| …`feasible_only=false` | 36 | 0.02 |
| corpus assembly (1,225 sides) | — | 0.24 |
| `make comparable-validation` (full battery) | — | ~35 |
| `make acquisition-validation` (30 teams) | — | ~6 |

**A regression was introduced and removed inside R6.** The league-wide role distribution was
first written as a loop over the thirty teams, which took a cold `/trades/evaluate` from 6
queries to **37** — thirty round trips paid by the first request after every ingestion, which
on the compose Postgres path is where the cost lands. It passed `test_query_budget.py`
unnoticed, because that fixture holds two teams. The batch load fixed it, and the budget file
now asserts the *shape*: the query count must not change when four more teams are added, and
a second service must reuse the cached reference with zero queries.

---

## 11. Commits and push status

```
623134f fix(comparables): a protected first is not the same asset as an unconditional one
ae9e1cb docs: record what R6 measured, and what it refused
e6a0d00 perf(evaluation): load the league's rosters once, not once per team
553d0d0 feat(ui): put precedent, rotation consequences and the memo in front of a user
d83ef29 feat(memo): turn the report into a decision artifact a front office can review
3a7b16e feat(roster-shape): report what a trade does to the rotation, and defer the lineup model
eb5e718 feat(acquisition): start from the need, and end at a trade you can evaluate
9b82540 feat(comparables): retrieve the completed trades a proposal actually resembles
e2a3a03 feat(transactions): ingest ten seasons of completed trades as evidence
```

All pushed to `origin/feat/rosterlab-autonomous-roadmap`. `main` untouched, no history
rewritten, nothing force-pushed, no `git stash` at any point. The working tree is clean and
no raw dataset is staged: the only data-adjacent files in the diff are a hand-written
synthetic test fixture, the drop-zone README and a `.gitkeep`.

---

## 12. Deviations from the plan

1. **The plan assumed a local historical-trade dataset. There was none.** `data/external/`
   did not exist and the Kaggle `nbadb` copy on this machine ends before the modelled window.
   R6 acquired one instead, following the pattern contracts and draft picks already use —
   third-party page in, gitignored, RosterLab-owned parser out — and added the repository's
   first fetcher, constrained by the source's own published policy.

2. **The plan called `TeamPlayerOnOffDetails` "Large" and blocked on `fetch_dataframe`'s
   single-dataset contract.** That contract already takes a `dataset_index`, so the stated
   blocker is outdated; the real one is different and larger. On/off splits derive from
   on-court `DEF_RATING`, which is the circularity R4-2 already withdrew a claim over, and
   five-man lineup data — which *is* reachable — carries a 16-point standard error at the
   median group. The deferral stands on a better reason than the plan gave it.

3. **Era is not a scored dimension.** The rankable corpus is entirely inside one CBA, so an
   era term would be a constant. Era is measured across all ten ingested seasons instead,
   where it is real and large.

4. **The comparable corpus was not widened by ingesting more seasons of player stats.**
   Doing so would have extended the rankable pool roughly threefold, and it touches the
   calibrated impact conversion the brief protects. It is named as the R7 starting point with
   the gate that must be re-run.

5. **One validation criterion was replaced rather than waived**, in the R2b / R4-2 pattern,
   with the reason and both numbers recorded (§3).

---

## 13. Unresolved limitations

- **The rankable corpus is 337 sides.** Every ranked comparable is a real trade side from the
  current CBA, and 888 ingested sides are stored, counted and retrievable but not ranked
  because `player_season_stats` holds three seasons.
- **No salary in the similarity.** Not a design choice that could be revisited without new
  data: no source here carries a historical contract.
- **The weights are a construct choice that materially determines the list** — uniform
  weights change 57 % of it. There is no target in this repository to fit them against, and
  the report says so rather than implying they were learned.
- **Archetype recovery measures internal consistency, not external validity.** The classes
  are built from the same features the distance reads.
- **The acquisition path proposes players only**, so a team's draft capital cannot constrain
  it.
- **Salary matching is unavailable league-wide on the shipped data** (0 of 30 teams have every
  rostered player priced), so the permissive band is used and the response says so.
- **The rotation level model remains implausible in absolute minutes** — R5.5 deviation 1,
  untouched, and R6 produced no new evidence about it.
- **QA-11** (`EFF` classification) remains the one strict xfail, still R7.

---

## 14. Recommended R7 starting point

**Widen the comparable corpus, behind a gate, before anything visual.**

The single highest-value change to R6's headline feature is more seasons of
`player_season_stats`. 407 of 565 ingested trades are unrankable purely because their feature
season sits outside 2023-24 … 2025-26; ingesting 2016-17 … 2022-23 would take the rankable
corpus from **337 sides to something on the order of a thousand** — 1,225 sides exist, and
95.7 % of the in-window ones are currently rankable, though older seasons resolve fewer
players so the real figure will be lower — without touching the methodology, which is
already validated and would simply see more data.

It is deliberately not in R6 because it touches a protected foundation. The exact procedure:

1. Sync `LeagueDashPlayerStats` (Base, Advanced) and `PlayerEstimatedMetrics` for 2016-17 …
   2022-23 into a **scratch copy** of the database. Do **not** add them to
   `history_seasons` — the served window must stay 2023-24 … 2025-26.
2. Re-run the R3 gate on that copy (§9's table). `add_zscores` standardizes within season and
   `_team_tei_transitions` filters to `history_season_list`, so every figure *should* be
   bit-identical. If any is not, stop: the window filtering has a leak, and finding it is the
   release.
3. Check `score_all` idempotence and the quality checks on the wider database — more seasons
   means more rows for `validate_data` to reason about.
4. Only then adopt, and re-run both R6 batteries: with a 3× corpus the thresholds should hold
   comfortably, and if archetype precision *falls*, that is evidence the current numbers were
   partly a small-corpus artifact and belongs in the report.

Then the R7 items the plan already names: `EFF` reclassification with a third field category
(C12, the last strict xfail); the minimum-GP filter and percentile-population fix in Player
Explorer; favourite-team persistence with a `storage` listener; component extraction from the
trade-evaluator page, which R6 grew rather than shrank; renaming TradeLab → RosterLab in the
stale docs; and rewriting or deleting `docs/demo-script.md`.

Two smaller R6 follow-ups worth carrying:

- **Let a suggested acquisition package include picks.** It would make draft capital a lever
  in the path where it currently cannot be one, and the pick valuation it needs already exists
  (R5-2) — including its refusals.
- **Narrow the bare `except Exception` in `generate_candidates`** and now also in
  `_evaluate_feasibility`. Both count and report the failure rather than swallowing it, which
  is an improvement on R5.5's finding, but a schema drift still reads as a modelling outcome
  rather than as an error.
