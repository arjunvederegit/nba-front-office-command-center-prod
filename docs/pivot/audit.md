# A. Repository audit — the R1–R7 product as found

*What existed on `main` at `2aab3e1` before the Pivot restructure. Written so the next
generation knows what it is standing on.*

The audit was performed by eight parallel readers over the whole tree — schema and
migrations, the analytics layer, services and the CBA engine, the API surface, ingestion and
provenance, frontend routes, frontend library and components, and tests/CI — followed by a
synthesis pass. Everything below is cited to a file.

---

## 1. What the product was

A decision-support simulator for NBA roster and trade decisions, shipped as Next.js 16
(App Router, 13 routes) over FastAPI (`/api/v1`, 39 endpoints, 7 routers), on SQLAlchemy 2 +
Alembic against SQLite in development and Postgres in compose.

Its organising value is **data honesty**: a missing input is an explicit unavailable state,
never an estimate, and no verdict is upgraded by a check that could not run. That is not a
slogan — it is enforced by tests that assert the *absence* of numbers, and several releases
were spent removing numbers the product had no right to display.

**Baseline measured before any change was made:**

| Check | Result |
| --- | --- |
| `pytest` | 908 passed, 1 skipped |
| coverage | 88.46 % (floor 85, CI-enforced) |
| `ruff` · `mypy` | clean, 97 source files |
| `eslint` · `tsc` | clean |
| `next build` | 13 routes |
| `vitest` | 82 passed, 9 files |
| `alembic current` | `f2c8b41d6a05` (head) |
| `alembic check` | no drift |

---

## 2. Architecture as found

```
Next.js 16 App Router ── /api/v1 rewrite ──> FastAPI
  app/       13 routes, all but 2 "use client"      api/v1/    7 routers, 39 endpoints
  components/ 11 flat files                         services/  9 modules
  lib/       11 modules                             analytics/ 18 modules
                                                    cba/       engine + 4 rule modules
                                                    ingestion/ 14 idempotent jobs
                                                    integrations/ nba_api, contracts, kaggle
                                                    db/        35 tables, 8 migrations
```

**The layering that was already right**, and which the restructure preserved:

- Every NBA.com call flows through one client
  (`integrations/nba_api/client.py::fetch_dataframe`) carrying rate limiting, retries,
  circuit breaking, schema contracts and caching.
- Analytics are pure given a DataFrame. `analytics/comparables.py` holds the distance and
  knows nothing about the database; `services/comparables.py` owns the join.
- The frontend never decides legality. It renders `POST /trades/validate`; the CBA engine is
  backend-authoritative.
- The dependency graph of `app/analytics` is a clean DAG with one hub and no cycles.

---

## 3. The canonical entity map as found

**35 tables** (36 with `alembic_version`), all with a `String(36)` UUID surrogate primary
key from `uuid_pk()` (`db/models.py:33`).

Provider identifiers are deliberately **not** primary keys: `teams.nba_team_id` and
`players.nba_player_id` are separate unique columns and every domain foreign key points at
the UUID (`db/models.py:1-12`). This is the schema's strongest asset and nothing in the
restructure disturbed it.

| Concept | Table(s) | Notes |
| --- | --- | --- |
| Team | `teams` | 30 rows |
| Player | `players` | 5,121 rows; `full_name` indexed, not unique (38 duplicate lowercase names) |
| Roster | `rosters` | 530 rows, bitemporal (`is_current`, `valid_from/to`) |
| Season | *none* | a `String(10)` label repeated across 12 tables — **no Season entity** |
| Contract | `contracts`, `contract_years` | 0 rows by default; 401/875 in the QA database |
| Trade (user) | `trade_proposals`, `trade_teams`, `trade_assets`, `trade_rule_results`, `trade_evaluations` | |
| Trade (history) | `historical_trades`, `historical_trade_assets` | 565 trades, 2,568 asset legs |
| Draft asset | `draft_picks` | 195 rows, 92 verified |
| Lineup | *none* | no entity at any level — deliberately, see §5 |
| Game | `games`, `player_game_stats` | 1,230 games; `player_game_stats` **0 rows, dead** |
| Statistics | `player_season_stats`, `team_season_stats`, `standings` | 17,022 / 180 / 300 rows |
| Model registry | `model_versions`, `player_impact_estimates`, `player_archetypes`, `team_needs` | |
| Mandate | `scenarios`, `scenario_weights` | **not** a scenario in the R13 sense — see §7 |
| Provenance | `data_sources`, `data_sync_runs`, `data_quality_issues` | |

**Dead or duplicated as found:** `injuries`, `player_game_stats` and `transactions` have zero
code references outside `models.py`; `comparison_sets` is referenced but empty in every
database; `player_team_history` (530 rows) carries the same facts as `rosters`.

---

## 4. The analytical systems

Deterministic and non-ML throughout. Every "model" is fixed documented weights, a rule chain,
or a small OLS fit registered in `model_versions`. scikit-learn is used only for
`mean_absolute_error`; the ridge challenger was retired in R3-1 and nothing in the serving
path can select a learned model.

| System | Where | What it is |
| --- | --- | --- |
| **TEI** | `analytics/impact.py` | transparent weighted z-score index over recency-weighted three-season features |
| **TEI → net rating** | `analytics/projection.py` | fitted change-on-change, coefficient **14.977** (SE 1.528, t 9.80, R² 0.624) over 60 team transitions |
| **Skills** | `analytics/archetypes.py::player_skill_vector` | **9 dimensions**, league percentiles, omitted when unmeasurable — never defaulted |
| **Archetypes** | `analytics/archetypes.py::assign_role` | **14 labels** from a deterministic size-first chain; 1.78 % label churn under a 10 % resample against k-means' 65.7 % |
| **Needs** | `analytics/needs.py` | **11 keys** — 9 percentile rules over team statistics, 2 from roster composition |
| **Fit** | `analytics/fit.py` | `Σ(need_severity × skill_delta) − γ·redundancy`, γ = 0.35 — already **team-conditional** |
| **Composite** | `services/evaluation.py` | 6 components × 7 strategy weight vectors; unavailable components dropped and weights renormalized |
| **Comparables** | `analytics/comparables.py` | 15 features in 6 dimensions over 565 trades / 1,151 sides |
| **Picks** | `analytics/picks.py` | empirical curve; honest that it does not beat a round-only rule (+0.0405, p = 0.22) |

**The key structural finding:** the skill vector — the single most reusable artifact in the
product — was **not persisted anywhere**. It was recomputed on the request path over the
whole league and cached in Redis for six hours under a source-code fingerprint
(`services/evaluation.py::_skills`). There is no skills table.

---

## 5. What the product deliberately refused to ship

These are not gaps. Each was built or measured, failed its own pre-registered check, and was
withdrawn — and each has a test that fails if the claim is quietly reinstated.

1. **Point-of-attack defense as a player skill** (R4-2). The composite scored *worse* than
   the steals proxy it replaced on its own pre-registered class (0.630 vs 0.611), because
   gambling for steals is what a box score records and staying in front of a ball handler is
   not. The team-side need is still measured and shown; no player skill claims to fix it.
2. **Lineup-aware fit** (R6-4). Refused on measurement, not deferred on schedule: the median
   five-man group has 20.2 minutes and an implied ±16 net-rating standard error against a
   ±10 league spread. `make lineup-availability` re-runs it, so the refusal stays falsifiable.
3. **A contract-prediction model.** No historical contract source exists, so there is nothing
   to validate one against.

---

## 6. Where the layering was violated

The audit found domain logic in the presentation layer in five places. Each is a basketball
judgement no backend test could reach.

| What | Where | Why it matters |
| --- | --- | --- |
| The **weighted composite score** re-implemented in the browser, and every saved deal re-ranked from it | `app/strategy-lab/page.tsx:93-108` (`decisionScore`) | two implementations of the product's headline number |
| **Competitive-window classification** from hardcoded age thresholds (25.5 / 28.5) | `app/team-outlook/[teamId]/page.tsx` | a basketball claim as a component constant |
| **League percentiles and the sample-qualification rule** computed client-side | `lib/playerStats.ts`, `app/player-explorer/page.tsx` | the population a percentile is taken against decided by the client |
| **Strength / weakness thresholds** (severity 0.35, percentile 65) | `lib/needs.ts` | "is this team bad at this?" answered in the browser |
| **Verdict banding** — the product's headline judgement | `lib/format.ts` | |

Additionally, business logic leaked into API routers in seven places, the largest being the
entire multi-season cap outlook as a 106-line handler that bypasses the payroll service
(`api/v1/teams.py:301-406`), and nearest-TEI player comparables computed inline
(`api/v1/players.py:118-149`).

---

## 7. The `Scenario` name collision

The `scenarios` table does **not** hold scenarios in the sense the Pivot roadmap means. It
holds a team's *decision mandate*: strategy, horizon, risk tolerance, apron willingness,
untouchable players, and the six component weights scoring runs under. It is a settings bag
attached to a team and it never changes as a result of a move.

R13's Scenario is a roster-state trajectory: state → move → state. Two different nouns, one
word — and the collision would have poisoned the scenario layer had it not been named before
anything was built on it. The resolution is in [ADR-22](adr.md).

---

## 8. Contract and honesty coverage

**The four-state standard** — `pass` / `fail` / `warning` / `unavailable`, with
`overall_status` never `verified_legal` while any rule is `unavailable` — is enforced by an
eight-line function, `cba/context.py:370-378`. It is the load-bearing property of the whole
product.

What is unavailable, and why no implementation quality changes it: the Basketball-Reference
snapshot carries no `contract_type`, `signed_date` or `no_trade_clause` — NULL on all 401
imported contracts. Those three fields are why `overall_status` stays
`conditionally_valid`. A hand-curated CSV is the only known route to `verified_legal`.

Consequence worth carrying forward: **salary-matching violations are not refutable**. An
illegal deal fails on roster rules or not at all.

---

## 9. The honesty invariants, and the tests that pin them

These must survive any refactor. Each is named because the test names are the specification.

| Invariant | Pinned by |
| --- | --- |
| `verified_legal` never survives an `unavailable` | `cba/context.py::overall_status` + adversarial battery |
| A player with no impact estimate reports `tei is None`, never 0.0 | `test_unmodeled_players_are_disclosed_not_defaulted` |
| …and no confidence band | `test_unmodeled_players_do_not_get_a_confident_band` |
| An empty trade has no `prob_positive` | `test_no_incoming_players_means_no_availability_number` |
| A skill is omitted, never set to 0.5 | `test_no_silent_defaults.py` (behavioural **and** an AST scan forbidding 0.5 / 0.75 / 12.0 / 0.85 / 1.5 as `.get()` or `or` fallbacks) |
| A verified-illegal trade carries no decision score | `make adversarial-validation`, 11 scenarios |
| The e2e suite runs against the demo database, not a developer's | `guards.spec.ts` — asserts every roster name starts with `Demo ` |
| Model content hashes reproduce after a full retrain | `test_r3_gate_after_r4.py` |
| Query budgets: evaluate ≤ 25, generate < 3,000, directory ≤ 6 | `test_query_budget.py` |

**Zero strict xfails remain** anywhere in the suite.

---

## 10. Technical debt that blocks R8–R14

Ranked by how much it gets in the way. Items marked ✅ were addressed in this restructure;
the rest are carried into [the R8 readiness document](r8-readiness.md).

| # | Debt | Blocks | Status |
| --- | --- | --- | --- |
| 1 | No skills table — the vector is ephemeral, Redis-only, 6 h TTL | R9, R11, R12 | carried to R8 |
| 2 | `player_archetypes` is 1:1 with a unique constraint on (player, season) | R10 | carried to R8 |
| 3 | No roster-state object; evaluation works on ad-hoc dicts and a private `_rotations` tunnel | R13 | ✅ `domain/roster.py`, `domain/moves.py` |
| 4 | No OBSERVED / DERIVED / INFERRED separation | R9, and §18 of the brief | ✅ `domain/evidence.py` |
| 5 | The evaluate-a-trade composite has no service home — the orchestration is duplicated in four API handlers, and both search services reach into `EvaluationService._roster_cards`, `._team_needs`, `._performance`, `._fit` | R13, R14 | carried to R8 |
| 6 | No `response_model` anywhere; the frontend hand-mirrors 771 lines of types | R14, and every client | partly — new endpoints are validated |
| 7 | Domain logic in the browser (§6 above) | R11, R12 | ✅ needs classification; others carried |
| 8 | The API hard-codes provenance to NBA.com regardless of the row's `source_provider` | honesty | carried to R8 — see below |
| 9 | No App Router `loading` / `error` / `not-found` anywhere | quality | ✅ |
| 10 | Fit is a trade-delta, not a player-team affinity | R12 | ✅ addressable, and gated where it inverts |

### The one genuine honesty defect found

The API serializers hard-code `source_provider` as `nba_api` / `NBA.com` rather than reading
the row. Synthetic demo rows — which are correctly stamped `source_provider="demo_seed"` in
the database and are guarded four separate ways from reaching production — are nonetheless
*described to the client as NBA.com data* when they are served. Four guards prevent the data
from leaking; none prevents it from being mislabelled once it has been legitimately loaded.

This is the only place the audit found where the product says something about provenance that
the database does not support. It is recorded here and carried into R8 rather than fixed
blind, because the fix touches the two serializers and their contract tests.

---

## 11. Naming: what could and could not move

95 occurrences across 40 files. The split is not cosmetic — four of these identifiers are
load-bearing.

**Must not be renamed:**

| Identifier | Where | Why |
| --- | --- | --- |
| `tradelab-backend` | `pyproject.toml:2` | the python distribution name; the import root is the generic `app`, so there is no `import tradelab_backend` anywhere and the rename buys nothing |
| `sqlite:///./tradelab.db` | `config/__init__.py:17` | points at a live 40 MB ingested database on the operator's disk |
| `tradelab:` | `core/cache.py:88-108` | the cache-key prefix; the data-version counter under it has a ten-year TTL |
| `TEI` | throughout | names a DB column, an API field, and every registered `ModelVersion` row. The **expansion** changed to "Pivot Estimated Impact"; the acronym did not |
| `ROSTERLAB_OFFLINE` | `cli.py:102` | the test suite's third-party network interlock |
| `rosterlab.favoriteTeam` | `lib/favoriteTeam.ts:32` | renaming silently discards every user's saved team |
| 13 `ROSTERLAB_*.md` reports | repo root | the provenance record of what was built under what name |

**Renamed:** all rendered UI copy, the wordmark, page titles, the OpenAPI title and root
payload, the decision-memo `<title>`, the outbound User-Agent, the `pyproject` description,
README and docs prose, module docstrings.

**A pre-existing inconsistency, now fixed:** the repository shipped *three* taglines
simultaneously — "Basketball Decision Intelligence" (browser title, wordmark), "NBA Front
Office Simulator" (OpenAPI title, `pyproject` description), and a third in page copy. Pivot
has one, exported once from `components/brand.tsx` and asserted by a test.

Alembic and the model registry are rename-neutral: `alembic.ini` hardcodes no database name,
a recursive grep across `backend/alembic/` returns zero brand hits, and all five
`ModelVersion` names are already neutral (`player_impact`, `player_archetype`,
`team_projection`, `tei_to_net_rating`, `pick_value`).

---

## 12. What was preserved without modification

The restructure deliberately did not touch:

- every formula, coefficient, weight and threshold in `app/analytics`
- the CBA engine and its four-state honesty function
- the comparable-trade retrieval, its side constructor, distance and weights
- the four validation batteries and their thresholds
- all 13 route paths and the 10 legacy redirects
- the "arena at night" visual language — palette, typography, panel treatment, court motifs

The visual and analytical work of R1–R7 is the part of this product that was already right.
