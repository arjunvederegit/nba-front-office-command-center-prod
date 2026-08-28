# B. Pivot target architecture

*The layering Pivot is moving toward, what exists of it today, and the seam each future
release plugs into.*

---

## 1. The stack, as layers

```
                                    ┌─────────────────────────────────────────┐
  RAW DATA                          │ integrations/  nba_api · contracts ·    │
  external, provider-shaped         │                kaggle                   │
                                    │ ingestion/     14 idempotent jobs,      │
                                    │                every one inside a       │
                                    │                DataSyncRun              │
                                    └──────────────────┬──────────────────────┘
                                                       │ provenance columns
                                    ┌──────────────────▼──────────────────────┐
  CANONICAL DOMAIN                  │ db/models.py   35 tables, UUID PKs,     │
  what a basketball fact IS         │                provider ids never in FKs│
                                    │ domain/        the VOCABULARY:          │
                                    │   evidence     observed→derived→inferred│
                                    │   skills       9 measured, 13 declared  │
                                    │   archetypes   14 functional labels     │
                                    │   needs        11 keys + what has no fix│
                                    │   roster       RosterState / LeagueState│
                                    │   moves        Move / apply / Scenario  │
                                    │   mandate      TeamMandate + weights    │
                                    └──────────────────┬──────────────────────┘
                                                       │
                                    ┌──────────────────▼──────────────────────┐
  DERIVED FEATURES                  │ analytics/features · impact · archetypes│
  arithmetic over observations      │           needs · age_curve · picks     │
                                    └──────────────────┬──────────────────────┘
                                    ┌──────────────────▼──────────────────────┐
  ANALYTICAL ENGINES                │ analytics/ fit · projection · roster_   │
  basketball inference              │            shape · uncertainty ·        │
                                    │            sensitivity · comparables    │
                                    │ cba/       rules engine, four states    │
                                    └──────────────────┬──────────────────────┘
                                    ┌──────────────────▼──────────────────────┐
  DECISION / SCENARIO               │ services/ evaluation · intelligence ·   │
  compare, simulate, explain        │           candidates · acquisition ·    │
                                    │           comparables · reports         │
                                    │ services/tools.py  the Copilot boundary │
                                    └──────────────────┬──────────────────────┘
                                    ┌──────────────────▼──────────────────────┐
  APPLICATION                       │ api/v1/   8 routers                     │
                                    │ frontend/ 13 routes, App Router         │
                                    └─────────────────────────────────────────┘
```

**The dependency arrow points one way.** `app/domain` imports no pandas, no SQLAlchemy, no
FastAPI, and nothing from `app.analytics`, `app.services`, `app.db` or `app.api`. This is
enforced by an AST test over every module in the package
(`tests/unit/test_domain.py::TestTheDomainImportsNothingAboveIt`), not by convention.

---

## 2. The domain layer

`app/domain` is the vocabulary. **It computes nothing.** No formula, no threshold applied to
data, no percentile. Percentiles, skill vectors, archetype assignment and need severities
stay in `app/analytics`, where the data is. What lives in `domain` is what those things
*mean* — and it is the single source of truth for that meaning.

| Module | Owns | Re-exported by |
| --- | --- | --- |
| `evidence.py` | `Evidence`, `Confidence`, `Measurement` | *(new)* |
| `skills.py` | `SKILL_KEYS`, `DECLARED_DIMENSIONS` | `analytics.archetypes` |
| `archetypes.py` | `ROLE_ID`, `CATALOG`, `ArchetypeMembership` | `analytics.archetypes` |
| `needs.py` | `NEED_TO_SKILL`, `UNADDRESSABLE_NEEDS`, thresholds | `analytics.needs`, `analytics.archetypes` |
| `roster.py` | `RosterSlot`, `RosterState`, `LeagueState` | *(new)* |
| `moves.py` | `Move`, `apply`, `ScenarioStep` | *(new)* |
| `mandate.py` | `Strategy`, `STRATEGY_WEIGHTS`, `TeamMandate` | `services.evaluation` (as `DEFAULT_WEIGHTS`) |

**The constants moved rather than being copied.** Every existing import keeps working, and
each moved value is asserted byte-identical to what shipped. `skill_schema_fingerprint()` is
unchanged at `14a7dac41af3` — it hashes the *contents* of `SKILL_KEYS`, not its address, so
no cached skill vector was orphaned by the move.

### The evidence ladder

```
OBSERVED   a provider reported it. Nobody here computed it.        PTS, MIN, a salary
    ↓
DERIVED    arithmetic over observations, reproducible by formula   a per-100 rate, a percentile
    ↓
INFERRED   a basketball attribute asserted from derived values     "this player protects the rim"
```

The distinction is not decoration. R4-2 withdrew a shipped point-of-attack composite because
it was an *inference* its own pre-registered check refuted, while the *derived* steals rate
underneath it was never in question. Keeping the two apart is what made withdrawing the claim
possible without deleting the data.

`Measurement` is the envelope that carries a value together with its rung, its method, its
source, its limitations — or an explicit absence with a required reason. It is **not** a
replacement for `None`: the existing discipline that a missing input is `None` rather than a
default is unchanged and load-bearing.

### Skills: measured versus declared

`SKILL_KEYS` is the **9 dimensions computed today**. Its contents and order are load-bearing
(cache fingerprint, persisted `role_id`).

`DECLARED_DIMENSIONS` is the **22-entry full vocabulary** — the offensive and defensive
dimensions a GM actually talks about. Thirteen carry `available: false` and the reason they
cannot be measured. This is the honest half of the product's claim: a reader learns that
Pivot cannot see switchability, rather than concluding switchability does not matter.

R9's job is to move dimensions across by finding data that supports them — **not** to invent
grades for them.

### Moves: membership, and nothing else

```
    state_b = apply(state_a, move)      # domain.moves — who is on the roster
    profile_b = team_profile(state_b)   # intelligence layer — what that means
```

`apply` does not reallocate minutes, reassign archetypes, re-derive needs, run a projection
or check legality. Folding any of that in would put a basketball model inside a data
structure and make the transition untestable on its own.

Legality in particular stays where it is: `cba.engine` is the authority, and a move `apply`
accepts may still be `verified_illegal`. Making `apply` refuse illegal moves would turn a
rules question into a data-structure question and lose the distinction between "cannot" and
"did not".

`apply` is pure, so a **branch is a second call on the same input**. `ScenarioStep` carries
the parent pointer a tree needs, and `LeagueState` holds many rosters — so the multi-team
reasoning in §11 of the brief is a traversal later rather than a rewrite.

---

## 3. The intelligence layer

`services/intelligence.py` exposes the three reads the decision workflow starts from. It
computes no new basketball quantity: every number comes from machinery that already shipped
and is already tested.

| Entry point | Endpoint | Built from |
| --- | --- | --- |
| `player_intelligence(player_id)` | `GET /intelligence/players/{id}` | `player_skill_vector`, the archetype chain, `player_impact_estimates` |
| `team_profile(team_id)` | `GET /intelligence/teams/{id}/profile` | roster cards, stored `team_needs`, the rotation skill profile |
| `player_team_fit(player_id, team_id)` | `GET /intelligence/fit` | `EvaluationService._fit` with its measured one-way baselines |
| `vocabulary()` | `GET /intelligence/vocabulary` | `domain.skills`, `domain.archetypes`, `domain.needs` |

Three properties this layer is responsible for that the underlying machinery does not enforce:

1. **Fit is conditional, and the signature makes it so.** There is no `fit(player)`. `team_id`
   is required, and a request without one is a 422 rather than a default. A route shape that
   permitted a universal score would contradict the product's position before any handler ran.
2. **A dimension Pivot cannot see is named, not omitted.** Every declared dimension appears in
   the response; the unmeasurable ones carry `available: false` and the reason.
3. **Strength and weakness are decided once, on the server**, from `domain.needs`, so every
   client is served one answer.

### Where fit is withheld, and why

Fit was measured across all 30 ingested rosters before being exposed. Where the need vector
has signal it discriminates correctly:

| Roster | Needs | n | median | sd | best fits |
| --- | --- | --- | --- | --- | --- |
| DEN | POA defense 1.00, rim protection 0.86 | 127 | 63.9 | 28.9 | Jalen Smith, Moussa Cisse, Charles Bassey |
| SAC | 3P volume 1.00, efficiency 0.93 | 129 | 62.3 | 34.8 | Porziņģis, Jokić, Tatum |
| MEM | defensive rebounding 1.00 | 129 | 49.7 | 33.7 | Jokić, Gafford, Porziņģis |

Where no need clears the severity threshold it **inverts**. `fit` is a needs term minus a
redundancy term; with the needs term near zero it becomes a pure redundancy penalty, and a
better player is strong in more skills so is charged for each one the roster already has:

| Roster | Max severity | n | median | share below neutral | worst-ranked |
| --- | --- | --- | --- | --- | --- |
| ATL | 0.172 | 79 | 41.6 | 88.6 % | Donovan Mitchell |

Two of thirty rosters are in that state. They receive an explicit unavailable with the reason,
rather than a number that would rank a star last.

---

## 4. The Copilot boundary

```
USER LANGUAGE → COPILOT → STRUCTURED TOOL CALL → PIVOT ENGINES
                        → RESULT + EVIDENCE → COPILOT EXPLANATION
```

`services/tools.py` is that seam, and there is deliberately no language model in it. A model
that answers "is this a good trade?" from its own weights is a different product from one
that calls `simulate_trade`, receives a composite with its components, exclusions and wins
band, and puts that into a sentence. The first invents; the second explains.

Two properties are asserted by tests:

- **Every tool is read-only.** `ToolSpec` raises on construction if `readonly=False`, so a
  conversation cannot change state a person never confirmed.
- **A tool that does not exist says so**, with the reason — the same discipline
  `domain.skills` applies to unmeasurable dimensions.

| Available today | Declared, not built | Why not |
| --- | --- | --- |
| `get_vocabulary` | `get_roster` | assembled inline in the teams router, not a service |
| `get_player_profile` | `search_players` | filtering is inline; search by archetype or need does not exist |
| `get_team_profile` | `compare_players` | comparison is assembled in the browser |
| `calculate_fit` | `simulate_trade` | the composite has no single entry point — the orchestration is duplicated across four handlers |
| | `simulate_addition` / `simulate_departure` | the transition exists in `domain.moves`; no engine consumes it yet (R13) |
| | `compare_scenarios` | half in the comparisons router, half in the browser |

The unbuilt half is the useful half of this document: it is exactly the R8 work list.

---

## 5. Application layer

**API.** Eight routers under one `/api/v1` prefix. The version lives only in the mount
prefix and routers carry no version, so new resource families are purely additive and cannot
break existing clients — `/intelligence` was added this way, touching no existing contract.

**Frontend.** 13 routes, unchanged. Navigation was regrouped around the decision workflow
(observe → diagnose → test → decide) rather than the module inventory; route *paths* were
deliberately not renamed, because doing so would break the ten legacy redirects, the
fourteen-route visual-QA manifest, the e2e specs and every shared Trade Evaluator link, for
no gain a reader would notice.

The client/server contract remains hand-mirrored in `lib/types.ts`, with runtime `zod`
validation applied narrowly to responses that carry decision numbers. The new intelligence
schemas validate two invariants the type system cannot: that `available` agrees with whether
a value is present, and that a need never appears as both a strength and a weakness.

---

## 6. What each future release plugs into

| Release | Seam that now exists | What it must still build |
| --- | --- | --- |
| **R8** canonical data | `domain/` vocabulary; `ProvenanceMixin`; `DataSyncRun` | a `player_skills` table; provenance on derived tables; the evaluation service entry point |
| **R9** player intelligence | `domain/skills.DECLARED_DIMENSIONS`; `Measurement`; `GET /intelligence/players/{id}` | data that supports the 13 unavailable dimensions |
| **R10** archetypes | `ArchetypeMembership` (weight, primary, confidence); `single_membership` | relax the 1:1 unique constraint; a multi-label engine |
| **R11** roster intelligence | `team_profile`; `skill_coverage`; server-side classification | scarcity, complementarity, creation hierarchy |
| **R12** fit | `player_team_fit`; the conditional signature; the measured gate | a fit model that does not collapse on a sparse need vector |
| **R13** scenario | `RosterState`, `LeagueState`, `Move`, `apply`, `ScenarioStep` | an engine that recomputes profile/projection after a move |
| **R14** copilot | `services/tools.py` registry, read-only, with caveats | the six unbuilt tools, then the model |
