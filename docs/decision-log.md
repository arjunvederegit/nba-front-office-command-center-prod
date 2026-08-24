# Decision log (ADRs)

## ADR-1 · Provider adapters instead of direct nba_api calls

**Context:** NBA.com endpoints throttle aggressively, drift schemas, and block
non-browser TLS fingerprints; during this build stats.nba.com hung indefinitely on a
slightly non-standard header set.
**Decision:** every NBA.com call flows through one client
(`integrations/nba_api/client.py`) with rate limiting, retries + jitter, a circuit
breaker, caching, schema validation, and health metrics; domain code sees only
normalized records behind the `NBADataProvider` protocol.
**Alternatives:** direct endpoint calls per feature (rejected: reliability logic
would smear across the codebase); a third-party stats API (rejected: the spec and
the portfolio value both hinge on the canonical free source).
**Consequences:** provider swaps and contract tests are trivial; one extra layer of
indirection.

## ADR-2 · Four-state legality instead of legal/illegal

**Context:** without contract data most salary rules cannot be verified; a binary
answer would either lie or make the product useless.
**Decision:** `verified_legal / verified_illegal / conditionally_valid /
not_evaluated`, derived mechanically from rule results; partial validation can never
produce "legal".
**Consequences:** the default no-provider install shows `conditionally_valid` at
best — visibly honest, and the UI explains exactly which data is missing.

## ADR-3 · Component framework rather than a single model score

**Context:** trades trade off incommensurable objectives; a single score hides the
disagreement between them and can't adapt to strategy.
**Decision:** six 0–100 components with user weights, raw calculations attached,
missing components excluded with weight renormalization.
**Alternatives:** one learned "trade quality" model (rejected: no ground truth for
"good trade", unexplainable, overfit bait).
**Consequences:** more surface area to explain, which is the point.

## ADR-4 · Uncertainty and sensitivity as first-class outputs

**Context:** box-score impact models have real error bars; weight choices are
subjective.
**Decision:** every evaluation ships Monte Carlo win distributions and every
comparison ships Dirichlet rank-stability + tornado analysis.
**Consequences:** ~0.5–1 s extra compute per evaluation; recommendations can be
called robust or fragile with evidence.

## ADR-5 · Constrained candidate generation

**Context:** unconstrained trade search produces absurd deals and combinatorial
explosion.
**Decision:** beam search bounded by package sizes, TEI-gap plausibility filters, an
evaluation budget, and a counterparty utility floor; outputs labeled as model
exploration, never predictions.
**Consequences:** a bounded, explainable idea generator instead of an "AI GM".

## ADR-6 · Deferred CBA rules

**Context:** sign-and-trades, TPEs, cash, BYC, and hard-cap triggers require
transaction-level data no free provider supplies and would multiply rule complexity.
**Decision:** implement the core matching/apron/roster/restriction subset fully and
honestly; document everything else as unsupported (see cba-rule-coverage.md).
**Consequences:** smaller but truthful scope — aligned with the project's
"honest > broad" priority.

## ADR-7 · Provider-backed data over a bundled dataset

**Context:** bundling a CSV would make setup trivial but violate honesty (stale,
unlicensed redistribution, fake "freshness").
**Decision:** runtime ingestion only; the repo ships zero NBA data; test fixtures
are tiny, clearly-marked synthetic records.
**Consequences:** first run requires network + a few minutes of ingestion; every
displayed number is traceable to a retrieval timestamp.

## ADR-8 · SQLite + in-process cache as dev defaults, Postgres + Redis in compose

**Context:** the build machine had no Docker; requiring Postgres/Redis locally
would block the primary "clone and run" path.
**Decision:** `DATABASE_URL` defaults to SQLite and the cache falls back to an
in-process TTL store; docker-compose and production wire Postgres 16 + Redis 7. The
schema avoids Postgres-only types (UUIDs as strings, JSON columns) so Alembic
migrations run on both.
**Consequences:** identical code paths, two deployment textures; single-instance
cache semantics in dev (documented on /data-health via `cache_backend`).

## ADR-9 · APScheduler worker instead of Celery/RQ

**Context:** the job workload is a handful of I/O-bound batch syncs per day; Celery
adds a broker dependency and operational weight far beyond the need, and every job
is already idempotent.
**Decision:** a small APScheduler process (`app/worker.py`) triggers the same
CLI-exposed jobs on configurable intervals.
**Alternatives:** Celery/Dramatiq/RQ (rejected for scope: no fan-out, no queues, no
retry semantics beyond what the client layer already provides).
**Consequences:** one fewer moving part; if the product grew user-triggered async
work, a queue would be reintroduced behind the same job functions.

## ADR-10 · TEI target choice

**Context:** a defensible supervised target must exist in the data. Team wins
contribution can't be attributed per player from box data alone.
**Decision:** predict next-season `0.6·z(PIE) + 0.4·z(NET_RATING)` (minutes-weighted
z within season) — a box-derived impact proxy that exists for every player-season,
validated strictly forward in time; keep the transparent index as fallback and
report both against a persistence baseline.
**Consequences:** honest scope (a proxy, stated as such) with measurable skill: the
index beat persistence 0.645 vs 0.717 MAE on the held-out transition.

**Superseded in part by ADR-15 (R3-1).** The ridge candidate won this player-level
comparison at 0.637 and was served on the strength of it. That was the wrong test: the
product uses TEI at *team* level, where the ridge explained R² = 0.0039 of net rating
against the index's 0.7505. The proxy target remains a defensible way to check the index
forward in time; selecting a model on it was not.

## ADR-11 · Split the two accent colors by job, not by hierarchy

**Context:** the previous dark theme was near-black plus a single orange accent — the
most common look an AI-assisted design lands on, and one that made every element compete
at the same volume.
**Decision:** two accents with disjoint responsibilities. Cyan (`--signal`) is the
system's voice: live state, active navigation, focus rings, primary chart series. Orange
(`--leather`) is the ball: the brand mark and the single primary action on a screen,
nothing else. Team color is a third channel, scoped to team context only.
**Alternatives:** one accent with tints (rejected: no way to distinguish "the system is
telling you something" from "you can act here"); full team-color theming per page
(rejected: destroys cross-page consistency and contrast guarantees).
**Consequences:** orange appears rarely enough that it always means "act", and a page can
be dense without being loud.

## ADR-12 · A condensed display face as a layout tool

**Context:** the spec treats awkward wrapping as release-blocking, and the old header
wrapped onto two lines at 1440px with eight destinations.
**Decision:** Barlow Condensed for titles, module names, team abbreviations and numerals,
paired with Archivo for interface text and IBM Plex Mono for tabular data.
**Consequences:** the condensed face buys roughly 20% horizontal room on every label,
which is what makes four primary destinations plus a More menu, search and status chips
fit one line down to 1024px without shrinking type. It is also the authentic typographic
artifact of the sport (jersey numerals, scoreboards), so the structural fix and the
aesthetic choice are the same decision.

## ADR-13 · Normalize supplied logos rather than styling around them

**Context:** twelve of the thirty supplied logo files ship on an opaque white card and
eighteen are transparent, so a row of crests mixed white boxes with clean marks.
**Decision:** derive a transparent copy at index time by flood-filling near-white **from
the image edges only**, so white inside a mark survives. Derived files are written to a
gitignored `derived/` folder; originals are never modified, and the manifest records
which copy is served.
**Alternatives:** render every logo on a light chip (rejected: 30 bright tiles fight the
dark surface); CSS blend modes (rejected: unreliable across marks with dark elements).
**Consequences:** crests render consistently on dark; the fix lives in the data pipeline
where it belongs rather than in every component that shows a logo.

## ADR-14 · Publish an asset manifest instead of letting images 404

**Context:** roughly 12% of rostered players have no matched photo. The fallback rendered
correctly, but every miss still cost a request and a console error, and the spec requires
no broken requests.
**Decision:** `GET /api/v1/assets/manifest` returns the set of NBA ids and abbreviations
that actually have an indexed image. The client fetches it once per session and only
requests an image it knows exists.
**Consequences:** zero 404s and zero console errors across all seven QA viewports;
unmatched players render their initials immediately rather than after a failed round-trip.

## ADR-15 · Rename routes to the product's own vocabulary

**Context:** navigation labels moved to the module names the product actually uses
(Trade Evaluator, Strategy Lab, Player Explorer, Team Outlook, Salary-Cap Center, Data
Health), leaving URLs like `/trade-machine` and `/data-status` inconsistent with them.
**Decision:** rename the route directories to match, and keep a redirect for every prior
URL — including the ones from the first rename. Next forwards query strings, so shared
Trade Evaluator links (`?state=…`) survive.
**Consequences:** the URL bar and the interface agree; no published link breaks. The
redirect table is the permanent cost, and it is documented in `next.config.ts`.

## ADR-15 · Retire the ridge; the transparent index is the metric (R3-1)

**Context:** the ridge was selected on held-out MAE against a next-season player proxy —
0.637 vs the index's 0.645. That comparison answers "which better predicts a player's own
next-season box profile". The product asks a different question: how does a roster change
move *team* net rating. Measured at that level on 90 team-seasons, the ridge explains
**R² = 0.0039** against the index's **0.7505** (change-on-change over 60 transitions:
0.0030 vs 0.6236). It is additionally a volume metric (corr 0.716 with usage, 0.100 with
net rating) and is not computable per season from stored artifacts, so the R3-2
conversion could only have been fitted on n = 30 of a metric with no signal.

**Decision:** retire it. Not demote — nothing in the serving path can select it, there is
no estimator import and no pickle to load. The index's fixed weights are the model, and
they are recorded in `model_versions`. Validation still runs time-aware against a
persistence baseline, because "better than assuming last season repeats" is still worth
checking.

**Consequences:** seven documents and the in-product methodology page carried "held-out
MAE 0.637" as the headline validation number; all now report the index's numbers and
state why the ridge lost. The interval band, which was derived from the retired model's
residual spread, had to be replaced in the same release (R3-4) rather than left pointing
at a model that no longer exists.

## ADR-16 · Fit the index→net-rating conversion; do not assume it (R3-2/R3-3)

**Context:** `team_tei_to_net_rating_delta` returned the difference in minutes-weighted
team TEI unchanged, on the reasoning that "TEI is on a per-100 individual scale". It is
not: the index is a weighted z-score on an arbitrary scale. A ×5 "players on court"
factor was also proposed and is equally unfounded.

**Decision:** fit `Δnet = b · Δ(team TEI)` change-on-change over 60 team transitions —
levels would carry everything the roster does not (coaching, health, schedule), and
differencing removes the team fixed effect. Measured **b = 14.977**, SE 1.528, t = 9.80,
R² 0.624; per-fold slopes 14.716 / 15.276; leave-one-transition-out RMSE 2.944 / 3.773
against 5.201 / 5.805 for predicting zero. Registered as its own `model_versions` row
with the regressor-construction string, because the coefficient is meaningless without it.

Two changes had to ship in the same release or the coefficient would have been silently
wrong:

- **Train/serve scale (C5).** Served rows were z-scored against the recency-weighted
  window's own distribution. Team-level correlation between the two constructions was
  r = 0.387, and the two rescalings that implied disagreed by **2.6×** — proof that no
  transfer factor existed. Serving against the reference season's moments removes the
  mismatch rather than correcting for it; slope is now 1.015 (r = 0.911).
- **Denominator and replacement level (R3-3).** Team impact was divided by the minutes a
  roster happened to fill, so giving players away took the same average over fewer
  minutes. It now divides by the 240 a team must field and charges the shortfall to a
  replacement-level player, derived (**−1.214**, mean TEI outside a team's top 10 by
  minutes) rather than hardcoded at −2.0, which sat at the 14.1st percentile.

**Consequences:** the performance component moved from sd 1.27 to **18.2** across a
150-trade sample, and stripping a roster of its three best players now scores at most
**14.7** across all 30 teams, from 56.4. The clamp binds on 2.7 % of that sample. The
falsification note is recorded with the fit: if TEI were already in additive
net-rating units the coefficient would be ≈5; it is ≈15.

## ADR-17 · One `delta_net`, computed once (R3-5)

**Context:** the point estimate reallocated all 240 minutes across the whole roster; the
Monte Carlo summed raw minute shares over the traded players only. Two different
quantities printed beside each other as if they were the same one, diverging with trade
size.

**Decision:** the simulation draws over the rotation the allocator produced — same
players, same minutes, same replacement fill, same coefficient. Incumbents appear on both
sides and, keyed on player identity, their draws cancel exactly.

**Consequences:** the simulated **mean** now equals the point estimate to within Monte
Carlo error (the regression test's tolerance is the simulation's own standard error, so
it tightens automatically if the draw count rises). The median sits slightly off it
because the availability beta is skewed, which is a real property of the distribution
rather than a disagreement; `mean` is therefore reported alongside the quantiles.

## ADR-18 · A comparable is a **side**, not a trade (R6-2)

**Context:** "Boston traded Marcus Smart for Kristaps Porziņģis" and "Washington traded
Kristaps Porziņģis for Marcus Smart" are one transaction. A front office asking for
precedent is not asking about the transaction; it is asking what happened to teams that
did what it is about to do.

**Decision:** the retrieval unit is one team's view of one trade. A three-team trade
contributes three of them, direction lives on the asset rather than on the team, and a
result list returns at most one side of any transaction — both remain in the corpus and
both are ranked.

**Consequences:** the corpus is 1,225 sides over 565 trades, 337 of them rankable. The
direction of a deal became a first-class property, which is what made
`direction_confusion` measurable at all: of the neighbours returned for a side that sold
on-court value for first-round picks, **1.0 %** are sides that bought it.

## ADR-19 · Similarity excludes what only one half can state (R6-2)

**Context:** a distance is a claim that two things are alike in the dimensions it reads.
Three dimensions are available on only one side of the comparison: salary (no historical
contracts exist here), cash and trade exceptions (the corpus states both, a *proposed*
trade states neither), and the outcome.

**Decision:** none of the three is scored. Cash and trade exceptions are reported as
attributes of a neighbour; salary and outcome are named in a `not_scored` block with the
reason on each.

**Consequences:** a feature the query can only ever answer "no" to would have penalized
the **37 %** of completed trades whose notes report a trade exception — a systematic bias
that would have looked like a preference for clean two-team deals. And the product never
implies that a comparable predicts anything: "resemblance is not consequence" is in the
panel's own text and in the memo, not in a tooltip.

## ADR-20 · A target list ranks on wins and filters on the need — not one blended score (R6-3)

**Context:** need-driven discovery has to combine "does he fix our problem" with "is he
any good". A single score needs a weight between them, and nothing in this repository
labels a target as good, so the weight could not be fitted.

**Decision:** two rules, both printed in the response. Filter on the need; rank on the
projected win change from adding the player. `sort=need` reorders by need improvement
instead. Ranking on `fit` was rejected because `fit_score` normalises minutes within a
side, so an 8-minute specialist scores like a 32-minute starter.

**Consequences:** ranking by wins alone gave all 30 teams the same names — **26 distinct
players** across every team's top five. Putting each candidate through the trade
evaluator under the candidate generator's own conditions took that to **72**, and made
the acquisition path and the generator agree by construction about what a front office
would accept.

## ADR-21 · Lineup-aware fit is refused on a measurement, not deferred on a schedule (R6-4)

**Context:** R6's third objective was a lineup-aware fit "where the available data
honestly permits it". The obvious answer — "the data is missing" — was not true:
`LeagueDashLineups` is reachable and returns real five-man data.

**Decision:** measure the samples instead of assuming them. At the median five-man group
among the top 2,000 by minutes (20.2 minutes, 2024-25) a net-rating estimate carries a
standard error of about **16 points per 100 possessions**, against a league team spread
of roughly ±10. Two- and three-man groups are estimable and still cannot support a
*trade* fit model, because a trade prices combinations that have never played together
and nothing here holds a held-out target to validate a synergy model against.

**Consequences:** what shipped is roster composition — minutes by role, before and after,
against the league's own distribution — labelled in its own text as not lineup data.
`make lineup-availability` re-runs the measurement, so the refusal is falsifiable rather
than permanent.
