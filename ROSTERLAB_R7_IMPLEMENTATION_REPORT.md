# RosterLab R7 — hardening, correction and close-out

**Branch** `feat/rosterlab-autonomous-roadmap` · **base** `0669f42` (R6) · **last code commit** `9b994d5`
19 commits, the final two being these closing documents

R7 is the last RosterLab release. Its objective was not another analytical system: it was to
finish, correct, simplify, document and comprehensively re-validate what R1–R6 built, so the
whole thing becomes a stable base for the next product generation.

The single most consequential thing it did was **not** the largest item on the plan. Widening
the comparable-trade corpus was the headline task; investigating whether it was safe is what
surfaced a live look-ahead defect, and questioning why a validation threshold moved is what
showed the threshold had never been measuring what it claimed.

---

## 1. The headline results

| | R6 | R7 |
| --- | --- | --- |
| Rankable corpus sides | 337 | **1,151** |
| Rankable completed trades | 154 | **535** |
| Archetype precision@5 | 0.797 | **0.917** (base rate 0.433) |
| Archetype lift over the shuffled null | 0.392 | **0.493** |
| Direction confusion | 0.019 | 0.025 (ceiling 0.05) |
| Best single-dimension null | 0.089 | **0.060** (ceiling 0.75) |
| `comparable-validation` runtime | ~90 s | **68 s at 3.4× the corpus** |
| Trades described by an unplayed season | 57 of 565 | **0** |
| Backend tests | 869 | **908** |
| Frontend tests | 45 | **82** |
| Strict xfails remaining | 1 | **0** |
| Largest frontend module | 2,964 LOC | 2,375 LOC |

Every gated criterion in every battery passes. The R3 calibration is **bit-identical**,
including after a full retrain on the widened database.

---

## 2. Historical corpus: investigated, then implemented

R6 recorded that 407 of 565 trades could not be ranked because `player_season_stats` held
three seasons. The instruction was to investigate rather than assume the remedy. Five
questions had to be answered before writing anything.

### Can the data be acquired through the existing architecture?

Yes, without new integration work. `LeagueDashPlayerStats` (Base, Advanced) and
`PlayerEstimatedMetrics` return 2016-17 onward through the provider already in production,
at 0.4–0.9 s per season. Ten seasons ingest in **23.7 s**.

### Do identifiers resolve?

**11,307 API rows, 0 unresolved.** The `players` table already holds all 5,121 historical
NBA players keyed on the same `nba_player_id` the stats arrive under, because it is
populated from `stats.static.players` rather than from current rosters. There was no
identity problem to solve.

### Does it change any production path?

Measured before anything shipped, on a scratch copy:

- The served window frame is **byte-identical** — 632 rows × 33 columns, same content hash
  — on a season frame that grows from 1,714 rows to 5,483. `recency_weighted_features`
  filters to `HISTORY_SEASONS` before it collapses anything.
- Every R3 calibration figure reproduces to **full float precision**: coefficient
  `14.976967215546017`, SE `1.5279397396294392`, R² `0.6235734193376163`, intercept
  `0.014786514305560218`, both per-fold slopes, both LOTO diagnostics.
- After the release, a **full `make train` on the ten-season database** reproduced every
  figure *and every content hash*. Model versions are content-hashed (R1-9), so this is the
  strongest available statement — the registered artifacts are byte-identical, not merely
  equivalent:

  | model | before | after |
  | --- | --- | --- |
  | `player_impact` | `20260730-0c89cb6a46a8` | `20260825-`**`0c89cb6a46a8`** |
  | `player_archetype` | `20260730-c621d2abcc85` | `20260825-`**`c621d2abcc85`** |
  | `team_projection` | `20260730-131594164c5d` | `20260825-`**`131594164c5d`** |
  | `tei_to_net_rating` | `20260730-7f98efcb3a6e` | `20260825-`**`7f98efcb3a6e`** |

  A fifth, `pick_value_curve`, is newly active — not because R7 changed it, but because the
  RealGM draft-pick snapshot had never been imported into this database, so R5's curve had
  nothing to fit. `make import-draft-picks` reproduces R5's recorded figures exactly: 394
  entries, **92 verified**, 103 unresolved, 0 unmatched team names.

The structural reasons are pinned by `test_corpus_window_isolation.py` rather than the
numbers: `add_zscores` standardizes within season, `recency_weighted_features` filters
before collapsing, and `_team_tei_transitions` filters after grouping per (team, season).

### Are historical features comparable across eras?

The battery already reports `era_structure`, splitting the corpus at the 2023 CBA. The
2017-CBA era moves picks at a similar rate but conditions them far less often — the share
of moved first-round picks carrying a protection or swap is 0.379 against 0.600 — and is
less multi-team (0.163 against 0.247). That is a real structural difference, and it is
**reported rather than corrected for**: a comparable from 2017 is still a trade that
happened, and the response names the neighbour's season on every card.

### Does it materially improve retrieval?

Yes, and by more than the count suggests. Archetype precision@5 rises 0.797 → **0.917**
against a base rate that also rises (0.414 → 0.433), so the lift rises 0.392 → **0.493**.
Both nulls stay on the base rate. Driving it live, a Jaylen Brown / OG Anunoby swap returns
Nurkić-for-Sexton, Caruso-for-Giddey, Rozier-for-Walker and George-for-Oladipo-and-Sabonis
— four of five from seasons that could not be ranked at all before.

**The widening also corrected sides that were already being ranked.** "No prior NBA season"
is decided against the seasons the database holds, so at three seasons a veteran whose last
season was 2022-23 looked like a player who had never played and was priced at zero.
2023-24 loses 8 such legs; 4 sides move from silently priced to honestly withheld. That
count going *down* is the improvement.

### Verdict

Safe, reproducible, provenance-aware, no new modelling project. **Implemented.**
`CORPUS_SEASONS` is a separate setting from `HISTORY_SEASONS`, and the two are kept apart
by tests rather than by discipline.

---

## 3. The look-ahead defect the investigation found

`feature_season_for` decided a trade's feature season from the calendar **month**. The
month is not enough, and the rule was wrong in three places at once:

| the month rule said | what had actually been played |
| --- | --- |
| 33 trades in November 2020 are 2020-21 | the 2020-21 season began **22 December 2020** |
| 12 trades on 26–28 June 2024 are 2024-25 | Basketball-Reference files draft night under the season about to start |
| 10 trades in early October are that season | first games fall 22–25 October |

**57 of 565 trades (10.1 %) were priced against production that did not exist when they
were made.** The June-2024 group sits inside the three-season window R6 shipped, so this was
**live, not latent**. `is_in_season` — a scored feature in the `timing` dimension — was
wrong on 163 trades for the same reason: no games are played in June or early October.

The two sets are identical: every trade the new rule moves is a trade the old rule described
by an unplayed season, and no others. That is asserted, not assumed.

The fix makes the season boundary **data**. `season_calendar` holds the first and last
regular-season game of each season, from `LeagueGameLog` — the same provider `standings` and
`player_season_stats` come from. Ten rows, no heuristic; the COVID and bubble calendars come
out correctly (2020-12-22, 2020-08-14). With no calendar ingested the month rule still
answers and `coverage.calendar_backed` reports `false`.

---

## 4. A validation criterion that was never measuring what it claimed

Widening the corpus dropped `perturbation_stability` from 0.6479 to 0.5949 against a 0.60
gate. Investigating that condemned the criterion, not the release — two independent reasons.

**It is a statistic about corpus size.** Random subsamples of one corpus:

| n | 200 | 337 | 600 | 1,151 |
| --- | --- | --- | --- | --- |
| perturbation stability | 0.707 | 0.676 | 0.651 | 0.611 |

Subsampling the ten-season corpus back to 337 sides reproduces the three-season number —
**0.651 against 0.648** — so retrieval was unchanged and only the statistic moved.

**Both nulls pass it**, which is disqualifying under the rule R4-2 established:

| ranking | measured |
| --- | --- |
| random-hash null (no information about any trade) | **1.0000** |
| shuffled-feature null | 0.6181 |
| the shipped distance | 0.6110 |

The random null scores *perfectly*, because a ranking keyed only on a side's identity cannot
move when its features do. A gate a zero-information ranking wins by the maximum possible
margin is not a gate.

**Replaced by the same wobble read as a rank.** The five neighbours the unperturbed query
returned must still average inside the top ten of the perturbed one: measured **4.33**,
median 4.0, p95 7.0, against a threshold of 10. It holds as the corpus grows (4.72 at
n=200 against 5.32 at n=1,151), which is what the level could not do. The old statistic is
still computed and printed with both nulls and the size curve beside it.

**R7 also named a distinction the battery had been eliding.** R4-2's rule was written about
*validity* claims. Applied literally to every check it would delete half of them, because a
ranking that ignores the trades is trivially insensitive to how the scales were estimated.
The battery now separates them: `archetype_recovery` and `direction_confusion` are validity
criteria and the nulls fail both decisively; the form-sensitivity checks are robustness
criteria — necessary, not sufficient, never evidence of validity — and each says so in its
own payload.

---

## 5. UX improvements

Every one below was found by driving the running product, not by reading code.

**Player Explorer — a percentile needs a population that can support it.** Every loaded
player entered the percentile population whatever his sample, so the ends of each shooting
scale were occupied by players who had barely shot:

| players at exactly 0.000 or 1.000 | all | ≥10 att | ≥15 att |
| --- | --- | --- | --- |
| FG% | 4 | 0 | 0 |
| 3P% | **67** | 1 | 0 |
| FT% | 52 | 0 | 0 |

Sixty-seven players at exactly 0 % or 100 % from three is 11.7 % of the league pinning both
ends, and every qualified player was read against them. One rule, one number, measured
rather than chosen: **fifteen of whatever the column divides by** — games for a per-game
stat, attempts for a percentage; 15 is the smallest common threshold at which no rate column
has a player at 0.000 or 1.000. A player below the line is still listed, sortable and
comparable; he is not given a percentile, and the tooltip says which of "no value" and "too
small a sample" it is. A **minimum-games filter** was added (default: all players, up to the
NBA's own 58-game leader rule), and the header's "league percentiles from this same set" was
deleted for being made false by the change.

**Strategy Lab — sixteen identical dropdown options.** Team Outlook generates
"BOS — Contend now" every time the button is pressed, so the starting-weights dropdown
offered rows that read alike and picked differently. R1 added the save *date*, which is right
in direction and insufficient in resolution: sixteen of nineteen scenarios shared one
afternoon. Labels are now built for the whole list at once with detail added only where
entries collide — date, then time, then an ordinal — so uniqueness is a property of the
output. Sixteen scenarios sharing a timestamp produce sixteen distinct labels.

**Precedent — coverage the retrieval actually has.** The panel said "1,151 team-sides of 565
completed trades"; 565 is what was ingested and 535 can be ranked. It names `trades_rankable`
now and states the shortfall. `calendar_backed` reaches the UI, because a fallback nobody can
see is a fallback that ships.

**Data Health — the seventh source.** The page opens with "every screen traces to one of
these sources", and since R6 the Precedent panel had traced to one that was not listed. The
card distinguishes three states, and the middle one is the point: trades **with no season
calendar still rank**, but each falls back to the month rule, so it reports `incomplete`
rather than working.

**Favourite team — one tab told the others nothing.** `storage` fires in the tabs that did
*not* write, so two open tabs disagreed until one was reloaded: a background tab kept showing
the previous team's colours and deep-linking to it. Writing the test found two more defects —
every `localStorage` access now guarded (it throws, not returns null, in Safari private mode,
and an uncaught throw in `getSnapshot` takes the page down), and the parsed value cached
against the raw string so `getSnapshot` returns a stable identity.

**About — a tool suite missing three tools.** It listed five surfaces and omitted comparable
trades, need-driven acquisition and the decision memo; its architecture diagram said 32
tables (35) and omitted two integrations.

**The decision memo claimed the corpus, not the coverage.** The precedent section read
"1,151 rankable sides of 565 completed trades" — the same defect corrected in the UI panel
earlier in R7, missed here, and this is the surface where it matters most: a memo is the
artifact a front office reviews away from the product and cannot interrogate. It now names
535 and states the shortfall with its cause. Found by generating a memo against the running
product, not by reading the code.

**Copy.** "1 saved deals". `count()` puts the noun in agreement at the six call sites that
can render one.

---

## 6. Engineering improvements

**The validation battery did not finish on the widened corpus** — over ten minutes, killed.
A gate nobody can run is not a gate. Three changes, none of which moves a number:

- **A side's feature vector was rebuilt on every distance.** `compare` asks both sides for
  their vector, so one leave-one-out pass rebuilt each corpus side's vector once per query —
  1.3 M dict constructions per pass, against ~25 passes. Memoized in a field excluded from
  equality, hashing and repr.
- **`rank` built the explanation for every candidate and discarded 1,146 of 1,151.** It now
  scores with `distance_between` and builds the decomposition only for the sides returned.
  `math.fsum(...) / n` rather than a running total, because `statistics.fmean` is what the
  full path uses and "the same number" has to mean the same number — asserted over every
  pair in the corpus.
- **Thirteen weighting passes were one pass.** Seven weightings plus six
  leave-one-dimension-out share the per-dimension distances and differ only in how they
  combine them.

Result: **68 s at 3.4× the corpus**, from over ten minutes.

**This nearly shipped a silent regression.** `_clipped_top_keys` measures the distance *form*
by rebinding the module-level `feature_distance`; inlining that arithmetic in the fast path
made the rebinding unreachable, and the check would have compared the shipped ranking against
itself and reported a perfect 1.0 while measuring nothing.
`test_the_distance_form_seam_is_reachable_from_rank` now fails if the seam is cut.

**A search that could not run read as a search that found nothing.** `generate_candidates`
wrapped `build_trade_context` in a bare `except Exception: continue`. At R5.5 the dev
database sat one migration behind, every pair raised, and the generator returned 0 candidates
on all 30 teams with 406 pairs silently discarded — which reads as a modelling outcome and
cost most of a session to identify. Still caught, but counted, typed, sampled and published
as `coverage.construction_errors`. The acquisition path carries the type too.

**`make e2e` was testing the wrong database.** Playwright's `reuseExistingServer` defaulted
to true, so the target seeded a dedicated demo database and then attached to whatever uvicorn
a developer had running — pointed at their ingested data — ran the suite against it, and
wrote fixture trades into it. Reproduced deliberately: 8 fixture trades and 19 near-identical
scenarios had accumulated, and one more run added two. **Every test passed while this
happened**, because the assertions are about product behaviour and the product behaves the
same on either database — silence was the failure mode. Reuse is now opt-in, and
`guards.spec.ts` measures which database is under test rather than trusting a flag.

**Component extraction.** The trade-evaluator page went 2,964 → 2,375 LOC; the seven
evaluation tab panels moved to `components/evaluation-tabs.tsx` (565), `sectionOf` to
`lib/evaluationDetail.ts`, and seven detail interfaces from a page's "local types" heading to
`lib/types.ts` where the contract they describe belongs.

**Dead code.** `lib/teamTheme.ts` deleted — with the favourite-team store moved out, every
remaining export was a re-export, so it was a shim in front of a shim.

**N+1.** `list_season_totals` called `db.get(Player, …)` per row — 573 statements for one
page load, on the surface a user hits first. Batched, with a budget expressed as "constant in
the row count".

**The cache was invalidated on one ingestion path out of eleven.** `bump_data_version` was
called at the end of `sync_all` and nowhere else, so the eight single-job CLI commands, the
CSV, transaction and draft-pick imports, and R7's own `sync-corpus-stats` all wrote rows and
left the previous snapshot's derived values cached under the old namespace.
`EvaluationService._skills()` is keyed on the data version, so a refresh of the modelling
seasons through any of those paths served **stale skill vectors**. Moved into
`ingestion/runs.sync_run`, which every job passes through, so invalidation is a property of
having ingested rather than a line a future job must remember — firing only on success and
only when rows were written.

**Frontend response validation.** The comparables response joined the two contracts
`lib/schemas.ts` guards, because R7 made its coverage block something the panel does
arithmetic on. Two refinements assert R7's own invariant: more rankable trades than ingested
ones is a broken join, not a bigger corpus.

**The test environment had no `localStorage`.** This vitest/jsdom build exposes it as a plain
empty object, so anything persisting across a page load silently did nothing under test and
the missing cross-tab listener could not have been caught. `tests/setup.ts` supplies a real
in-memory `Storage`, defined before anything reads the property so Node 25's experimental Web
Storage is never initialised and its warning stops appearing on every worker.

---

## 7. QA-11: the last strict xfail

`EFF` is NBA.com's efficiency composite summed over the season — 60 across 4 games is 15.0
per game — and it sat in `_RATE_FIELDS`, rendered beside FG% and 3P% where every other value
is scale-independent. Per C12 the fix needed a **third field category** rather than a move
into `_TOTAL_FIELDS`: those are parsed with `_required_float`, so a blank `EFF` would have
started rejecting the whole row, dropping a player's entire season over a stat the source
does not guarantee.

**The pin itself was also wrong**, and would have gone on passing for the wrong reason: it
queried `stat_type == "csv_totals"`, which the importer has never written, so it failed at
`assert stat is not None` before reaching a single claim about `EFF`.

Strict xfails remaining: **0 of 23**.

---

## 8. The adversarial battery, committed

R6's report says "adversarial scenarios 20 / 20" — a number in a document that nobody can
re-run. `make adversarial-validation` runs eleven scenarios against the ingested league and
exits non-zero on any failure. Each asserts a **property of the response**, never a value.

| scenario | measured |
| --- | --- |
| empty trade scores exactly neutral | 50.0 both sides (QA-5 shipped 46.36) |
| empty trade states no probability | `prob_positive` null, not 0.0 |
| verified-illegal carries no decision score | 4 refusals, every composite null |
| a refusal names its rule | `ROSTER_SIZE`, "would have 24 players — above the 18-spot ceiling" |
| suppression says it was suppressed | `suppressed_illegal` both sides |
| giving away the best three never reads as a gain | worst **7.8** of 100, 8 teams |
| a roster gutting stays under the QA-1 ceiling | max **7.8** against 25 |
| receiving value never scores below sending it | sent 2.7–15.7, received **81.2–90.1** |
| an unpriced player is disclosed, never defaulted | no case in this database, reported |
| an impossible trade is refused at construction | duplicate and phantom both `InvalidTradeError` |

**Writing it found two ways a check can pass while testing nothing**, both now pinned:
`rules_failed` read a key spelled `rule_code` and collected `[None]` — a non-empty list of
nothing; and the directional scenarios built one-way trades the roster limit refuses, so they
iterated over an empty list.

A third was a faulty assumption about the product rather than the test. `_roster_cards`
orders by `player_id` — deterministic, chosen in R1-5 — not by quality, so slicing it for
"the best three" took three arbitrary players. The first run reported the team **sending**
its two best at 70.9 and the team receiving them at 23.9. That reads as a serious model
inversion and was nothing of the kind.

---

## 9. Final validation

```
backend pytest             908 passed · 1 skipped · 0 xfailed    (was 869 / 1 / 1)
backend coverage           88.46 %, floor 85
frontend vitest             82 passed, 9 files                    (was 45 / 6)
ruff · mypy (97 files) · eslint · tsc                 clean
production build           13 routes, TypeScript clean
migrations                 clean DB → head → base → head; `alembic check` no drift
Playwright                   6 passed (5 + the new database guard)
visual QA                  105 shots, 15 routes, 7 viewports — no overflow,
                           no console errors, no empty pages
adversarial battery         11 / 11
comparable battery          every gated criterion, 68 s
acquisition battery         4 / 4 gated
R3 gate                    bit-identical, including after a full retrain
```

Re-run after `make train` and `make score` on the widened database: every figure above
reproduced.

---

## 10. Plan deviations

1. **The corpus widening was not gated behind the R3 gate as a *sequence*** — it was measured
   against it on a scratch copy *before* the settings change was written, which is stronger
   than the plan's ordering and is why the look-ahead defect surfaced before shipping.

2. **A validation criterion was withdrawn rather than met.** The plan did not anticipate
   `perturbation_stability` failing; the honest response was neither to lower the threshold
   nor to declare a regression, but to measure whether the criterion tests the release. It
   does not. This follows the precedent of the R2b, R4-2 and R6-mirror reassessments exactly.

3. **The acquisition package still proposes players only.** The state file listed "let a
   suggested acquisition package include picks" as R7 item 2. It is a feature addition to a
   validated production path, and R7's stated objective is to finish and harden rather than to
   add. Deferred with the reason, not silently dropped — see §11.

4. **The TradeLab → RosterLab rename is deliberately incomplete** in two places, both stated
   in code: the `TEI` acronym (it names a column, an API field and every registered model
   version) and persistent infrastructure identifiers (SQLite filename, compose credentials,
   cache-key prefix, distribution name — renaming them orphans every existing local database
   and volume).

5. **`docs/demo-script.md` was rewritten, not deleted.** The plan offered either. It was
   rewritten because every surface it should describe now exists.

---

## 11. Remaining limitations

**Data.**

- **No contract provider is configured by default**, so salary matching, apron limits and
  payroll remain `unavailable` product-wide. This is unchanged since R2b and unchangeable
  from `nba_api`: the BBRef snapshot carries no `contract_type`, `signed_date` or
  `no_trade_clause`, and those three are why `overall_status` stays `conditionally_valid`. A
  hand-curated CSV is still the only route to `verified_legal`.
- **30 of 565 ingested trades still cannot be ranked** — feature season before 2016-17, or a
  player with no production in any season held. Widening further has diminishing returns:
  the pre-2016 pages are not fetched, and era comparability degrades.
- **Draft-pick ownership is 92 verified of 394 parsed.** Swaps, protections and conditional
  picks are recorded with their source sentence and never priced.

**Modelling.**

- **No defensive metric here is validated.** Every available target derives from on-court
  `DEF_RATING`, so every test is circular to some degree; on the one non-circular question
  every candidate's confidence interval crosses zero. Unchanged from R4-2.
- **Lineup-aware fit remains refused on measurement**, not deferred on a schedule. Re-run
  `make lineup-availability` before reopening it.
- **The rotation allocator's level model is still implausible in levels** — ~13 players above
  10 minutes against a real ~10, best player ~22 minutes against a real ~30. R5.5 measured
  three alternatives out of sample and every one lost. The fix needs a load-shaped estimand,
  which means separating role from availability throughout the projection, and the R3
  coefficient is fitted on the current meaning of `minutes`.
- **The pick curve does not beat a round-only rule** (+0.0405, p = 0.22). What is established
  is the gradient inside the first round (0.3277, p = 0.0023).

**Product.**

- **The acquisition package proposes players only.** Draft capital cannot constrain the
  acquisition path, although the valuation it would need already exists (R5-2) including its
  refusals. This is the cleanest single piece of deferred work in the repository.
- **The trade-evaluator page is still 2,375 lines.** The tab panels came out cleanly; the
  team-workspace and board region (~900 lines) is coupled to the builder's drag state and was
  not worth the regression risk in a close-out release.
- **`era_structure` is reported, never gated.** The 2017 and 2023 CBA eras differ measurably
  in how picks are conditioned, and neighbours from either may be returned. The season is
  named on every card; nothing weights against era distance.

**Process.**

- `test_the_served_coefficient_matches_the_registered_fit` still skips when no fit is
  registered, which is every CI run. `test_r3_gate_after_r4.py` covers the same ground without
  skipping, and this release verified the served constant against the registered one manually.

---

## 12. Commits and push status

```
9b994d5 fix(e2e): explain the refusal, so the fix is not undone by the next person to hit it
98f7d34 docs: bring the closing documents to the final commit
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
```

All pushed to `origin/feat/rosterlab-autonomous-roadmap`. `main` untouched; no history
rewritten; nothing force-pushed; no `git stash` at any point.

**No raw dataset is committed.** The R7 diff adds one migration, one ingestion job, one
validation module, one component module, three small lib modules, tests, and documentation.
Transaction snapshots, contract snapshots and QA screenshots remain gitignored.
