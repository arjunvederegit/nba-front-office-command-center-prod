# C. Gap analysis — R1–R7 → restructure → R8–R14

*What already exists, what this restructure added, and what each future release must still
build. The purpose is that no future release has to re-derive this.*

```
        R1–R7                      RESTRUCTURE                    R8 ─────────────► R14
   a trade evaluator          a decision-intelligence         the intelligence
   with honest data           architecture around it          that fills it in
```

---

## The one-line summary per release

| | Release | Already exists | Restructure added | Still to build |
| --- | --- | --- | --- | --- |
| **R8** | Canonical data foundation | provenance on 17/35 tables, `DataSyncRun`, UUID PKs with provider ids separated | the domain vocabulary; the layering that gives R8 a target | a `player_skills` table; provenance on derived tables; one evaluation entry point |
| **R9** | Player intelligence | 9 measured skills, deterministic and null-honest | 22 declared dimensions with reasons; `Measurement`; `/intelligence/players/{id}` | data that supports the other 13 |
| **R10** | Archetype engine | 14 functional labels, stable (1.78 % churn) | multi-membership shape with weight + confidence | relax the 1:1 constraint; a multi-label engine |
| **R11** | Roster intelligence | 11 needs; roster shape by role-minutes | `team_profile`, skill coverage, server-side classification | scarcity, complementarity, creation hierarchy |
| **R12** | Team-conditional fit | `fit_score` already conditional, with measured one-way baselines | `Fit(player, team)` addressable; the inversion measured and gated | a fit model that survives a sparse need vector |
| **R13** | Scenario engine | trade evaluation, before/after rotation | `RosterState` / `Move` / `apply` / `ScenarioStep` | an engine that recomputes meaning after a move |
| **R14** | GM Copilot | services that hold the answers | a read-only tool registry, honest about what it lacks | six unbuilt tools, then the model |

---

## R8 — Canonical Basketball Data Foundation

**Exists.** Every provider-derived row carries `source_provider`, `source_record_id`,
`source_retrieved_at`, `valid_from/to`, `ingestion_run_id`. Every ingestion is wrapped in a
`DataSyncRun`, and since R7 that wrapper is where the derived-value cache is invalidated.
Identity resolution is centralized and tiered, and refuses to guess (`ingestion/identity.py`).

**Restructure added.** The domain vocabulary, so R8 has a canonical shape to normalize
*toward* rather than inventing one. `domain.skills`, `domain.archetypes` and `domain.needs`
are now the single definition of each concept, and the analytics modules re-export them.

**Gaps.**

1. **No canonical-data layer exists.** Ingestion writes the exact tables analytics, services
   and the API read. There is no intervening abstraction, so a schema change ripples straight
   through. This is workable and was not urgent; it becomes urgent when a second provider
   supplies the same concept.
2. **Provenance is applied to 17 of 35 tables** and is absent from every derived table —
   including `player_archetypes` and `player_impact_estimates`, so an archetype row carries no
   link to the model version that produced it.
3. **Provenance is uniform as a column but not as a discipline.** `source_provider` defaults
   to `"nba_api"` at the ORM level and several jobs never set it explicitly.
4. **The API hard-codes provenance to NBA.com** regardless of the row's actual
   `source_provider`. This is the one genuine honesty defect the audit found — see
   [the R8 readiness document](r8-readiness.md) §1.
5. **No `Season` entity.** A `String(10)` label is repeated across 12 tables.
6. **Zero CHECK constraints, zero enums, and SQLite FK enforcement never enabled** —
   `PRAGMA foreign_keys` appears nowhere in `backend/app`, so declared foreign keys are
   documentation-only in dev, e2e and QA.

---

## R9 — Player Intelligence Engine

**Exists.** Nine skill dimensions computed from ingested box-score data as league
percentiles, omitted rather than defaulted when unmeasurable — with an AST-level test
forbidding the specific literal-fallback shapes that would reintroduce a silent default.

**Restructure added.** The full 22-dimension vocabulary, with the 13 unmeasurable ones
carrying `available: false` and a specific reason each. `Measurement` carries evidence class,
method, source, confidence and limitations with every value. `GET /intelligence/players/{id}`
returns all 22 — the gap between declared and measured is rendered, not hidden.

**Gaps.** Data, not code. The unavailable dimensions need:

| Needs | Unlocks |
| --- | --- |
| player-tracking data | spacing/gravity, off-ball movement, screen navigation, help defense |
| matchup data | switchability, positional versatility, and an honest point-of-attack metric |
| play-type / shot-location splits | rim pressure, finishing, transition offense |
| a split of existing inputs | offensive rebounding (currently folded into `rebounding`), disruption (folded into `team_defense`) |

The last row is the only one R9 can do without an acquisition, and it is a modelling change
rather than a data one.

**Persistence is the bottleneck.** `player_skill_vector` is a single-row pure function — a
clean seam — but the vector is recomputed over the whole league on the request path and
cached only in Redis for six hours. R9 cannot version, diff or backfill a skill it does not
store.

---

## R10 — Archetype Engine

**Exists.** Fourteen functional archetypes from a deterministic size-first rule chain. These
are already archetypes in Pivot's sense, not positions — `3&D wing`, `movement shooter`,
`stretch big`, `playmaking big`, `connector wing`. The chain is stable (1.78 % label churn
under a 10 % resample, against k-means' 65.7 %) and byte-identical across process
invocations and BLAS thread counts.

**Restructure added.** `ArchetypeMembership` carries `weight`, `primary`, `evidence` and
`confidence`; `single_membership()` wraps the one label the shipped chain returns, faithfully
— it returns a one-element list because the engine produces one label, not because a
multi-label engine exists. Callers written against it are already written for the plural form.

**Gaps.**

1. `player_archetypes` has a unique constraint on (player, season). Multi-membership is a
   **schema change, not an addition**.
2. No engine produces a second label or a confidence today.
3. Membership is `Evidence.INFERRED` at `Confidence.MEASURED` and can never be `VALIDATED` —
   no ground-truth archetype set exists to validate labels against. R10 should not invent one.

---

## R11 — Roster Intelligence / Needs Engine

**Exists.** Eleven need keys on a shared 0..1 severity scale, each with a percentile and a
plain-English explanation. `roster_shape` reports how the 240 minutes distribute across roles
before and after a trade, with a congestion threshold measured as the 90th percentile of the
same role across the 30 ingested teams.

**Restructure added.** `team_profile` — roster size, skill coverage across the rotation,
archetype distribution, needs, and strengths/weaknesses **classified on the server**. The
classification thresholds moved out of the browser, where they were a basketball judgement no
backend test could reach, into `domain.needs` — and a zod refinement now asserts the two lists
stay disjoint, the defect QA-9 originally found.

Skill coverage is reported as the **third-best rotation value**, which is the same statistic
`_fit` uses to decide a roster is already strong somewhere — so the profile a user reads and
the redundancy the evaluator charges are one number, not two thresholds that can disagree.

**Gaps.** The brief's roster vocabulary is only partly covered:

| Concept | Status |
| --- | --- |
| skill coverage, depth, positional size, roster balance, strengths, deficiencies, needs | ✅ available |
| role hierarchy, lineup dependency | partial — role-minutes exist, no hierarchy |
| **skill scarcity** (league-relative), **complementarity**, **creation hierarchy** | ✗ not built |
| **redundancy** | exists only inside `fit_score`, not as a roster property |
| **defensive versatility** | ✗ blocked on matchup data (same as R9 switchability) |

The brief's example — *"switchability is limited because only one rotation player meets the
threshold for guarding three or more archetypes"* — is **not buildable today** and the
restructure did not fake it. Switchability is a declared-unavailable dimension.

---

## R12 — Team-Conditional Fit

**Exists.** `fit_score` was already conditional and already correct in shape:

```
F = Σ_k ( n_k · Δs_k )  −  γ · Σ_k max(0, r_k)        γ = 0.35
```

with severity taken as the **maximum** over the needs mapping to a skill rather than the sum
(R4-1a: summing double-counted one skill delta up to 2.67×), and with measured one-way
baselines for each direction (R5.5).

**Restructure added.** Fit is addressable as `Fit(player, team)` with `team_id` **required** —
there is no team-free entry point, and a request without a team is a 422. The score was then
measured across all 30 rosters before being exposed, which is how the failure mode below was
found rather than shipped.

**The gap R12 must close.** Fit is a needs term minus a redundancy term. When the need vector
is sparse the needs term vanishes and fit becomes a pure redundancy penalty that **ranks
better players lower** — a better player is strong in more skills and is charged for each one
the roster already has. On ATL (max severity 0.172) 88.6 % of candidates score below neutral
and the worst-ranked player is Donovan Mitchell. Two of thirty rosters are in that state, and
they now get an explicit unavailable rather than a number.

A fit model that survives this needs at least one of:

- a **league-relative scarcity term**, so a skill can be valuable without a measured deficit;
- **magnitude**, which fit deliberately excludes today — `fit_score` normalizes minutes within
  each side, so a package's weight cancels and an 8-minute player who answers a need scores
  like a 32-minute one. This is why `performance`, not `fit`, carries magnitude in the
  composite, and re-normalizing it would be a re-tuning of the composite that no measurement
  motivates;
- a **prior** over needs, so a roster with no measured deficit is not treated as having no
  preferences.

The brief's decomposition — `need fulfilment + scheme fit + role fit + complementarity −
redundancy − risk` — currently has **need fulfilment** and **redundancy** only. Scheme fit and
role fit have no input: nothing in the repository measures a scheme.

---

## R13 — Scenario Engine

**Exists.** A trade produces one evaluation **per team**, with components, exclusions, a wins
band from 2,000 draws, and rotation consequences by role. The before/after rotation pair is
real — it was simply smuggled through the response under a private `_rotations` key and popped
by the caller.

**Restructure added.** The nouns. `RosterState` (membership snapshot), `LeagueState` (several
rosters — so multi-team is expressible without a rewrite), `Move` (seven kinds: trade,
signing, waiver, draft, departure, injury, rotation), `apply` (pure, membership only), and
`ScenarioStep` with a parent pointer so a scenario is a tree rather than a list.

**Gaps.**

1. **Nothing consumes `domain.moves` yet.** `apply` changes membership; no engine recomputes
   profile, projection, rotation or legality from the result. That composition is R13's work.
2. The evaluation pipeline is still trade-shaped end to end, and its composite has no service
   entry point (see R14 below) — which is what a scenario engine would need to call.
3. `scenarios` has no parent, no branching and no owner; it is a flat settings bag.
4. Constraints R13 must respect, all measured and all easy to break:
   - a departure's minutes go **unfilled at replacement level**, never to the next man up
     (the signal share of served TEI outside a team's top ten is 0.000);
   - shedding is proportional, and gaining and shedding are genuinely asymmetric;
   - `roster_shape` reads the allocation the projection produced, never re-derives it.

---

## R14 — GM Copilot

**Exists.** Services that hold real answers, and `reports.py` — a pure function over
already-computed dicts, the cleanest seam in the layer.

**Restructure added.** `services/tools.py`: a read-only registry of ten named tools with JSON
Schema parameters, four implemented and six declared-with-reasons, plus `result_caveats` that
travel with each result. The caveats are the part that matters — `calculate_fit` carries
"fit measures the direction of a change, not its size", which is precisely the misreading a
fluent model would otherwise produce.

**Gaps — and this is the concrete R8 work list.** Six tools cannot be exposed because the
functions they would call do not exist as functions:

| Tool | Blocked by |
| --- | --- |
| `simulate_trade` | the composite has **no single entry point**: `build_trade_context → TradeLegalityEngine().evaluate → per-team evaluate_for_team` is duplicated across four API handlers |
| `get_roster` | assembled inline in `api/v1/teams.py` |
| `search_players` | filtering inline in `api/v1/players.py`; search by archetype or need does not exist at all |
| `compare_players` | assembled in the browser from several endpoints |
| `compare_scenarios` | half in the comparisons router, half in the browser |
| `simulate_addition` / `simulate_departure` | R13 |

A related symptom of the same problem: `services/candidates.py` and `services/acquisition.py`
reach into `EvaluationService._roster_cards`, `._team_needs`, `._performance` and `._fit` —
private methods — because no public equivalent exists. The encapsulation boundary is already
broken; R8 should give it a public shape rather than continue around it.

---

## What the restructure deliberately did **not** do

Each of these was considered and declined, with the reason:

| Not done | Why |
| --- | --- |
| Persist skills; relax the archetype constraint | Schema changes with no consumer yet. Recommended concretely in R8 rather than executed speculatively. |
| Rename route paths to the brief's IA | Would break 10 legacy redirects, a 14-route QA manifest, e2e specs and every shared link, for no gain a user sees. Navigation grouping and labels changed instead. |
| Add a GM Lab / Strategy / Pivot AI index page | The brief forbids empty pages, and a page promising a module Pivot has not built is the presentation-layer version of a fabricated number. GM Lab is a nav group over three real modules. |
| Retrofit `response_model` across all 39 endpoints | Large, risky, and orthogonal. New endpoints carry validated contracts; the rest is an R8 item. |
| Move the Strategy Lab composite to the server | A real violation, but the page is 1,805 lines and entangled with slider state. Named in R8 with the specific lines. |
| Build any part of R9–R14's intelligence | The brief's instruction, and the right call: establish the interface now, implement the sophisticated intelligence later. |
