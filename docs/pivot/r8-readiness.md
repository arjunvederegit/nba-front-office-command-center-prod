# E. R8 readiness — what to build next

*A concrete recommendation, in implementation order. R8 is the **Canonical Basketball Data
Foundation**: the release that makes the intelligence layer's inputs storable, versioned and
honestly labelled.*

R8 should not attempt R9's metrics. Its job is to remove the four things that currently make
R9–R14 impossible or duplicative, in an order where each step is independently shippable.

---

## Recommended sequence

| # | Work | Size | Unblocks | Risk |
| --- | --- | --- | --- | --- |
| **1** | Fix the provenance-labelling defect | S | honesty | low |
| **2** | One evaluation entry point | M | R13, R14, and the two search services | medium |
| **3** | Persist the skill vector | M | R9, R11, R12 | medium |
| **4** | Multi-membership archetypes | S | R10 | low |
| **5** | Provenance + model linkage on derived tables | S | R8's own claim | low |
| **6** | A `Season` entity, or a documented decision not to have one | S | R8, R13 | low |
| **7** | Constraints: CHECKs, enums, FK enforcement in SQLite | M | data integrity | medium |

Items 1–4 are the ones that matter. 5–7 are hygiene that R8 is the natural home for.

---

## 1. Fix the provenance-labelling defect

**This is a correctness bug in the product's core claim, and it should go first because it is
small and because the claim is the product.**

The database is right: synthetic demo rows are stamped `source_provider="demo_seed"`
(`ingestion/demo_seed.py`), every player is named `Demo <ABBR> <NN>`, the seeder refuses to run
against a database holding `nba_api` rows, it is reachable only through a CLI command pointed
at a dedicated SQLite file, and a Playwright guard asserts the roster names.

The **serializers** are wrong. Two API paths hard-code `source_provider` as `nba_api` and the
upstream as `NBA.com` rather than reading the row. So a demo row — correctly labelled in
storage, correctly quarantined from production — is *described to the client as NBA.com data*
once served.

Four guards prevent synthetic data from leaking. None prevents it from being mislabelled.

**Do:**
- Read `source_provider` and `source_retrieved_at` off the row in `api/schemas.py::Provenance`
  and both construction sites (`api/v1/teams.py::_team_out`, and the player serializer).
- Map provider key → human upstream name in one place, and make an unknown provider render as
  the raw key rather than falling back to `NBA.com`.
- Add a test that a `demo_seed` row is never described as NBA.com. This is the assertion the
  suite is missing, and it belongs beside the existing honesty tests.

**Risk:** low. Two serializers, contract tests already exist for the shape.

---

## 2. Give the evaluation composite one entry point

**The single highest-value refactor in the repository.**

Today the sequence

```
build_trade_context  →  TradeLegalityEngine().evaluate  →  per-team evaluate_for_team
```

is copy-pasted in **four API handlers**, and `services/candidates.py` and
`services/acquisition.py` reach into `EvaluationService._roster_cards`, `._team_needs`,
`._performance` and `._fit` — private methods — because no public equivalent exists.

Consequences today: four places to keep in sync, an encapsulation boundary that is already
broken, and `GET /trades/{id}` recomputing everything on every read while the persisted
evaluation stays write-only.

Consequences for the roadmap: `simulate_trade` cannot be a Copilot tool, because a tool must
call one function rather than reproduce an orchestration. R13 has nothing to call either.

**Do:**
- Add `services/evaluation.py::evaluate_trade(db, teams, assets, strategy, weights) -> dict`
  containing the orchestration exactly as the handlers perform it today.
- Convert the four handlers to call it. **Assert identical output** on a fixture set before
  and after — this is a pure extraction and anything that changes is a bug.
- Promote the four private methods the search services use to documented public methods
  (`roster_cards`, `team_needs`, `performance_for`, `fit_for`) and migrate both callers.
- Then register `simulate_trade` in `services/tools.py` and flip it to `available=True`.

**Risk:** medium — it touches the product's most important path. Mitigated by it being a pure
extraction with a before/after equality assertion, and by 986 existing tests.

---

## 3. Persist the skill vector

**The bottleneck under R9, R11 and R12.**

The nine-dimension vector is the most reusable artifact in the product and is not stored
anywhere. It is recomputed over the whole league on the request path and cached in Redis for
six hours under a source-code fingerprint. R9 cannot version, diff or backfill a skill it does
not store, and no query can ask "which players improved at X".

**Proposed schema:**

```sql
CREATE TABLE player_skills (
    id                TEXT PRIMARY KEY,          -- uuid_pk()
    player_id         TEXT NOT NULL REFERENCES players(id),
    season            TEXT NOT NULL,
    skill_key         TEXT NOT NULL,             -- domain.skills.SKILL_KEYS
    percentile        REAL NOT NULL,             -- 0..1
    model_version_id  TEXT NOT NULL REFERENCES model_versions(id),
    schema_fingerprint TEXT NOT NULL,            -- skill_schema_fingerprint()
    computed_at       TIMESTAMP NOT NULL,
    UNIQUE (player_id, season, skill_key, model_version_id)
);
CREATE INDEX ix_player_skills_season_key ON player_skills (season, skill_key);
```

**Design notes that matter:**

- **Long, not wide.** One row per (player, season, skill) rather than nine columns. Adding a
  dimension in R9 is then an insert, not a migration — which is the whole point, since R9's job
  is to add dimensions.
- **A skill Pivot cannot measure has no row.** Not a NULL, not a 0.5. The absence *is* the
  representation, matching `player_skill_vector`'s existing contract.
- **`schema_fingerprint` is stored**, so a row computed under a different skill contract is
  identifiable rather than silently mixed with current ones.
- **`model_version_id` is required**, which fixes the R8 §5 gap for this table at least.

**Do:** write on `make score` alongside `player_archetypes` and `team_needs`; keep the Redis
cache as the read path initially and switch reads over once the table is populated and a
test asserts the two agree. Do not remove the recomputation path in the same release.

**Risk:** medium. ~5,100 players × 9 skills × N seasons. Mitigated by writing before reading.

---

## 4. Let a player hold more than one archetype

`player_archetypes` has a unique constraint on `(player_id, season)`. Multi-membership is a
schema change, not an addition, and R10 will be blocked on a migration on day one unless R8
does it.

**Migration:**
- drop `uq_player_archetype (player_id, season)`;
- add `UNIQUE (player_id, season, label)`;
- add `weight REAL NOT NULL DEFAULT 1.0` and `is_primary BOOLEAN NOT NULL DEFAULT 1`;
- add `confidence TEXT` (`domain.evidence.Confidence`);
- add `model_version_id` (see §5).

**Backfill is trivial and lossless:** every existing row becomes `weight=1.0, is_primary=1`,
which is exactly what `domain.archetypes.single_membership()` already returns.

**Do not** ship a multi-label engine in R8. The deterministic chain stays the only producer;
the schema simply stops forbidding a second label. `ArchetypeMembership` already carries the
fields, so no application code changes shape.

---

## 5. Provenance and model linkage on derived tables

`ProvenanceMixin` is on 17 of 35 tables and absent from all 18 derived and user-authored
ones — including `player_archetypes` and `player_impact_estimates`, so an archetype row
carries no link to the model version that produced it.

Derived rows do not need the full six-column mixin (there is no upstream `source_record_id`
for a computed value). They need three things: `model_version_id`, `computed_at`, and the
`ingestion_run_id` or data version they were computed against.

Add those to `player_impact_estimates`, `player_archetypes`, `team_needs` and the new
`player_skills`. This is what makes "which model said this?" answerable, which is the
question R9's traceability claim rests on.

---

## 6. Decide about a `Season` entity

`season` is a `String(10)` label repeated across 12 tables with no entity behind it, while
`season_calendar` already holds the first and last regular-season game per season and is
already load-bearing for the comparable corpus.

Two defensible options:

1. **Promote `season_calendar` to the Season entity** and make the 12 `season` columns
   foreign keys to it. Correct, and a wide migration.
2. **Document the string as deliberate** and add a CHECK constraint on the format.

Recommendation: **option 2 for R8**, option 1 only if R13 turns out to need multi-season
scenario state. The string works, the risk of a 12-table migration is real, and the decision
should be driven by a need rather than by tidiness.

---

## 7. Constraints

- **Zero CHECK constraints and zero enums exist.** Every categorical is a bare `String` with
  its legal values in a comment. Add CHECKs for the ones the domain now enumerates:
  `stat_type`, `decision_status`, `resolution_method`, `conveyance`, `strategy`, and the new
  `confidence`.
- **SQLite foreign keys are never enforced.** `PRAGMA foreign_keys` appears nowhere in
  `backend/app`, so every declared FK is documentation-only in dev, e2e and QA — the three
  environments where the tests run. Enable it on connect and expect to find real orphans;
  finding them is the point.
- **`contracts` has no natural key**, so nothing prevents two contract headers for the same
  player from the same source.

---

## Data-quality concerns R8 should carry, not solve

These are acquisitions, not code. Each is unchanged from the R1–R7 handoff and each still
gates something real.

| Wanted | Unlocks | Note |
| --- | --- | --- |
| contract types, signed dates, no-trade clauses | `verified_legal`, salary-matching refutation, second-apron aggregation | a hand-curated CSV is the only known route; 401 imported contracts are NULL on all three fields |
| matchup / tracking data | an honest defensive metric, switchability, POA defense | every in-repo target is circular |
| five-man lineup data with usable samples | lineup-aware fit | measured and refused, not deferred — `make lineup-availability` re-runs it |
| pre-2016 transactions | the last 30 unrankable trades | diminishing returns, worsening era comparability |

---

## What R8 should **not** do

- **Do not add player grades.** R9 owns that, and only after data exists to support them.
- **Do not build a fit model.** R12 owns it, and the gap analysis records what it must survive.
- **Do not rename `tradelab-backend`, `tradelab.db`, the `tradelab:` cache prefix, `TEI`, or
  `ROSTERLAB_OFFLINE`.** Each is load-bearing; the reasons are in [ADR-24](adr.md).
- **Do not remove the Redis skill cache** in the same release that adds the table.
- **Do not touch the four validation batteries' thresholds.** If a threshold moves, it must be
  because a measurement moved it.

---

## Definition of done for R8

1. A `demo_seed` row is never described as NBA.com data, and a test says so.
2. `evaluate_trade` exists, four handlers call it, output is asserted identical, and
   `simulate_trade` is `available=True` in the tool registry.
3. `player_skills` is populated by `make score` and a test asserts it agrees with the
   recomputed vector.
4. `player_archetypes` admits multiple rows per player-season; existing rows backfilled to
   `weight=1.0, is_primary=1`.
5. Derived tables carry `model_version_id`.
6. `alembic upgrade head` then `alembic check` is clean; migrations reverse.
7. The full suite, the four batteries and the R3 bit-identity gate all still pass.
