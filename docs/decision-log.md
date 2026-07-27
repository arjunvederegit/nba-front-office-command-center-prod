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
**Consequences:** honest scope (a proxy, stated as such) with measurable skill:
ridge beat persistence 0.637 vs 0.717 MAE on the held-out transition.

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
