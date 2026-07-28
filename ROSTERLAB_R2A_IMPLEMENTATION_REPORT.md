# R2a — Performance and instrumentation

**Branch:** `feat/rosterlab-autonomous-roadmap` · **Commits:** `8b0fe82`, `dc645d5`
**Property:** ships alone, requires no contract data.

---

## 1. Performance

Measured on the live database with `contracts` at **0 rows** — the cheapest possible
case, because a missing contract is one query that returns nothing.

| | before | after | budget |
| --- | --- | --- | --- |
| `POST /trades/evaluate` (2-for-2) | **61** queries | **15** | < 25 |
| `POST /trades/generate` (focal BOS) | **21,326** queries / 2.15 s | **46** / 0.36 s | < 3,000 / < 1.2 s |
| `app.cli score` | **crashed** (§3) | 93 queries / 0.07 s | — |

**464× fewer queries** for candidate generation. The plan measured 47,158 queries /
5.17 s with contract data loaded; on the compose Postgres path that is 7–14 s of pure
round-trip latency, which is why the budget is expressed in queries — SQLite hides the
cost that matters.

The 21,326 broke down as:

| queries | statement |
| --- | --- |
| 16,640 | `SELECT … FROM contracts WHERE player_id = ?` |
| 1,169 | `SELECT … FROM league_cap_parameters` (one immutable row) |
| 793 | `SELECT … FROM players WHERE id IN (…)` (one per team per evaluation) |
| 409 | roster-membership validation, re-run per candidate trade |

`app/cba/resolver.py` batches all four behind a cache in `Session.info`. Its lifetime is
exactly the request's session, and it is cleared on `after_flush`, `after_commit` and
`after_rollback`, so a write can never be served a stale read. Nothing is global.
`evaluation.py`'s two function-local imports of a private helper inside the hot path
(~800 executions per generate request) are gone.

**Acceptance: the same 8 candidates**, same packages, same counterparties,
`evaluations_run` still 400. Verified by diffing the generator output against a
`git stash` of the pre-change code on the same database.

`tests/unit/test_query_budget.py` pins the budgets, that the batch cost does not scale
with roster size (1 player and 30 cost the same number of queries), that a commit
invalidates the cache, that batched and per-player lookups agree exactly, and that the
simulation is order-independent.

## 2. Contract coverage instrumentation, and the R2b go/no-go

Run against the Basketball-Reference snapshot already in the repository
(`data/imports/contracts/players.html`, saved 2026-07-28), on a **scratch copy** of the
development database. Nothing was written to the development database.

```
matched                                       886 rows
  exact_name 867 · suffix_insensitive 10 · unaccented 9
unmatched                                     154 rows
ambiguous                                       0 rows
seasons present in snapshot         2026-27 … 2031-32   (cap league year present ✓)
roster players with a 2026-27 salary      392 / 530     (74.0 %)
teams with a computable payroll             0 / 30
```

### This is a measured no-go for R2b

R2b's acceptance criterion is **`teams_with_complete_payroll ≥ 27/30`**. The best
available artifact yields **0/30**.

It is not a matching failure — the join works. 886 records bound, zero ambiguous, and the
snapshot does carry 2026-27, the league year trade legality is evaluated under. The
problem is coverage: 138 rostered players (26 %) have no 2026-27 salary in a
Basketball-Reference snapshot taken in the offseason, overwhelmingly because their deals
expired. `_team_payroll` is all-or-nothing, so one missing player removes an entire team
from the count.

The plan predicted this shape from a sensitivity table (1 % missing → 26/30 teams;
5 % → 10/30; 20 % → 0/30). At 26 % missing the measurement lands where it said it would.
Building R2b on this artifact would ship a release whose gate cannot pass, and whose
headline — "salary matching now works" — would be false for all 30 teams.

**Two honest paths forward, in order of preference:**

1. **R2c first, inverting the plan's order.** R2c replaces the binary payroll gate with a
   disclosed-coverage model — "computed from 16 of 18 contracts; 2 unknown". The plan
   gates R2c on "only after R2b proves the join works", and the join *is* proven: 886
   bound, 0 ambiguous, 74 % roster coverage. With disclosed coverage the same snapshot
   becomes useful for 30 teams instead of 0, and the missing 26 % is stated rather than
   hidden. This is the change that makes partial real data worth having.
2. **A more complete artifact.** A hand-curated CSV through the `file` provider, which
   accepts `nba_player_id` (exact identity), `signed_date`, `no_trade_clause` and
   `contract_type` — the three fields that, per C8, keep `overall_status` pinned at
   `conditionally_valid` no matter how much BBRef data is loaded. Even one or two fully
   curated teams would unlock `verified_legal` for those teams, which BBRef cannot do at
   any coverage level.

Neither is blocked on code. Path 1 is available now; path 2 needs a human artifact.

## 3. Two defects found by doing this

### `make score` was broken on any database that had already been scored

`score_all` deleted a team's `TeamNeed` rows and added the replacements in the same
flush. With `autoflush=False` both landed together, and SQLAlchemy emits a mapper's
INSERTs before its DELETEs, so the second run raised

```
UNIQUE constraint failed: team_needs.team_id, team_needs.season, team_needs.need_key
```

Reproduced against the code at `f16dedc` on the development database, so it is
pre-existing and unrelated to the batching. It only ever worked the first time, which is
why a fresh clone never saw it — and why neither the audit nor the plan caught it. Rows
are now updated in place, new ones inserted, and genuinely-gone ones deleted, so a rule
that stops firing cannot leave a stale row behind claiming otherwise. Both properties are
tested.

### The Monte Carlo depended on player order

It consumed one shared generator in list order, so the same trade produced different
numbers depending on the order players happened to arrive in — which was database order
until `_roster_cards` gained an `ORDER BY` in R1-5. Each player now draws from a stream
seeded on the run seed and their identity. Numbers shift once (≤ 0.15 composite points
across the 8 generated candidates) into an order-independent state, and a parametrized
test shuffles the input two ways to prove it.

## 4. Identity resolution

`app/ingestion/identity.py` replaces `{full_name.lower(): p}` over 5,121 players with
four tiers tried in descending confidence, none of which falls through silently.

| Tier | On the real snapshot |
| --- | --- |
| `nba_player_id` | exact identity; the `file` provider supplies it, BBRef does not |
| exact name | 867 matches |
| unaccented | 9 |
| suffix-insensitive | 10 |

Measured on the live database:

- **38 lowercase names are duplicated.** `Brandon Williams` is both nba_player_id 1585
  (on no roster) and 1630314 (rostered). A currently-rostered player now wins the tie;
  two historical namesakes are reported **ambiguous and not bound**, and recorded to
  `data_quality_issues` at severity `error`. A wrong binding puts one team's salary on
  another team's books, which is worse than a missing one.
- **Unaccenting is a fallback tier, never a blanket normalize.** The database is
  internally inconsistent: `Bogdan Bogdanović` keeps its diacritics, `Alperen Sengun`
  does not. Normalizing everything would break as many matches as it fixes. As a
  fallback it introduces **no new collisions** — 38 duplicate names before, 38 after.

## 5. Deviations from the plan

| # | Deviation | Why |
| --- | --- | --- |
| D1 | The Monte Carlo was made order-independent | Not in R2a's scope, but the batching changed player ordering and would otherwise have moved numbers for an invisible reason. Fixing the fragility is better than documenting it, and it makes "the same 8 candidates" cleanly verifiable. |
| D2 | `score_all`'s re-score crash was fixed here | Found while measuring `score.py`'s N+1. A crash on the second run of a documented command is not something to leave in place for a later release. |
| D3 | Coverage is reported even with no provider configured | The plan says instrument before importing. Reporting only after a provider exists would mean an operator cannot see the gap until they have already committed to filling it. |
| D4 | The R2b go/no-go was measured, not assumed | The plan lists two go/no-go unknowns that "cannot be resolved without the artifact". The artifact is in the repository, so they were resolved — on a scratch database copy. |

## 6. Next eligible release

**Not R2b.** Its gate cannot pass with the artifact available (§2).

**R2c** is now the highest-value next step and is unblocked: the join is proven, and
disclosed coverage turns a 74 %-covered snapshot from useless into useful. After that,
**R3** — impact units and calibration — is the critical path and depends only on R1,
which is complete.
