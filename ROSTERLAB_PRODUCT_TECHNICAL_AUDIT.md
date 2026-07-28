# RosterLab — Product & Technical Audit

**Audit date:** 2026-07-27 · **Commit audited:** `f16dedc` (main, clean tree)
**Method:** full source read (backend 9,322 LOC Python / frontend 12,169 LOC TS), live SQLite inspection (`backend/tradelab.db`, 17 MB), live API exercise against `localhost:8000`, live UI walkthrough of every route at `localhost:3000`, `pytest` run (114 passed) with coverage.
**Reviewer stance:** senior product engineer / sports-analytics lead / ML engineer / front-office strategist. Deliberately critical.

---

## 1. Executive Summary

RosterLab is the most *honest* NBA trade tool I have audited and one of the least *decision-useful*. Those two facts have the same root cause, and fixing the second without destroying the first is the entire job ahead.

The engineering is real. `backend/app/integrations/nba_api/client.py` is a properly hardened provider client — rate limiting, bounded retries, circuit breaking, schema contracts, provenance on every row. `backend/app/cba/` is a clean, individually-unit-tested rules registry with a genuinely rigorous four-state honesty standard (`context.py:overall_status`). `docs/limitations.md` is more candid than most published sports-analytics work. 114 backend tests pass in 2.7s. CI runs ruff + mypy + pytest + eslint + tsc + a Docker build.

But the product that sits on top of that engineering produces numbers a basketball operations person would reject inside sixty seconds. Verified live during this audit:

- **Chicago trades Josh Giddey for Stephen Curry** → verdict "High-risk upside", decision score **46/100** (below neutral), **"Median −0.0 wins · 49% chance it helps"**, "Modeled net-rating change **+0.00** per 100 possessions."
- **Boston trades Jayson Tatum for Luka Dončić** → **+0.43 wins**, and the model's single largest cited benefit is that Boston's **point-of-attack defense improves** (`fit.needs_addressed.point_of_attack_defense = +0.3279`).
- **Boston trades all 16 rostered players for nothing** → composite utility **72.85**, **+0.83 wins**, the *highest score of any trade I constructed*.
- The saved executive memo for "give away Jayson Tatum, receive nothing" reads: **"−0.2 wins … P(positive) = 42%"** and **"Historical availability of incoming players: 85%"** — when there are no incoming players.
- The **Data Health page — the honesty centerpiece — reports "Current NBA data ✓ fresh, updated Jul 27, 2026, 1:45 AM"** while the underlying API reports `stale: true` for all seven NBA.com tables and every roster page correctly reads "updated Jul 21, 2026, 1:53 AM." The Jul 27 timestamp is a local *image-file indexing* job.

The failure is not sloppiness. It is a single unvalidated unit conversion (`projection.py:92–95`) sitting under a very well-built pipeline, plus a defensive-value proxy (`archetypes.py:141`, steals-per-minute) that is basketball-wrong, plus a set of magic scaling constants that saturate or flatten every component score. The honest disclosures exist — but they live in `docs/limitations.md`, and the UI asserts the opposite of them on screen.

**The single most important structural fact:** the flagship differentiator — the CBA rules engine — **cannot run.** `contracts` = 0 rows, `contract_years` = 0 rows, `draft_picks` = 0 rows, `injuries` = 0 rows, `transactions` = 0 rows. Every trade evaluated in this audit returned `conditionally_valid` with `SALARY_DATA_AVAILABLE: unavailable` and `SALARY_MATCHING: unavailable`. In its shipped state, the "CBA-aware rules engine" is a roster-headcount checker with `confidence: medium`. One 20-minute data import (`data/imports/contracts/players.html` + `CONTRACT_DATA_PROVIDER=bbref_snapshot`) turns four dead modules on. Nothing else in this report has a comparable value-to-effort ratio.

**Verdict:** RosterLab is roughly 70% of a credible front-office platform. The missing 30% is not more features — it is calibrating one number, replacing one defensive proxy, loading one dataset, and deleting four components that currently manufacture false precision.

---

## 2. Current Product Positioning

### What it actually solves today

Two-team (and three-team) hypothetical roster construction against live NBA.com rosters, with an explicit, inspectable statement of what the system does *not* know. The unique asset is the **honesty layer**, not the analytics.

### Who it is currently built for

The UI copy targets a fan ("fan verdict", "High-risk upside", broadcast-style team banners) while the substrate targets an analyst (provenance columns, model cards, Dirichlet rank stability, tornado sensitivity). Neither audience is fully served: the fan gets a decision score whose components they can't interpret; the analyst gets a headline win delta they can't reproduce.

### One platform or several tools?

**Several loosely-linked tools.** Concrete evidence of disconnection:

| Symptom | Evidence |
| --- | --- |
| Two parallel stat pipelines that never meet | Player Explorer renders `stat_type='totals'` from `user_import_csv` (573 rows). Every model reads `stat_type IN ('base','advanced','estimated')` from `nba_api` (5,142 rows). `features.py:77–87` never touches the CSV. |
| The platform's own headline metric is absent from its research page | Player Explorer has no TEI/Impact column at all. Team Outlook and Trade Evaluator show *only* TEI and no box score. |
| Team context does not persist across modules | Trade Evaluator opened on CHI; navigating to `/salary-cap-center` reset to ATL, contradicting the homepage promise "RosterLab defaults to it everywhere." |
| Strategy Lab ships development artifacts as its sample content | The saved-deal picker lists **"E2E RosterLab deal"**, **"Smoke test deal"**, **"Alt deal"**; the scenario dropdown shows `BOS — Contend now` three times and `E2E scenario` twice. |

### Differentiation vs. the field

| Competitor class | RosterLab today | Honest assessment |
| --- | --- | --- |
| ESPN / Fanspo trade machines | Cannot do salary matching at all (no contracts) | **Strictly worse.** The one thing trade machines do, RosterLab currently cannot. |
| Basketball-Reference / Cleaning the Glass | No tracking, no on/off, no lineups, no play types, no shot location | **Strictly worse** as a stats reference. |
| Spotrac / RealGM cap tools | No payroll, no cap holds, no exceptions, no picks | **Strictly worse.** |
| Generic prediction dashboards | Uncertainty bands, unavailability states, provenance, sensitivity analysis | **Genuinely better** — this is the only defensible moat today. |

### Proposed positioning statement

> **RosterLab is a decision-support workspace for NBA roster construction that scores every trade against a team's stated strategic objective under real CBA constraints — and refuses to answer where the data cannot support an answer.**

The clause after the em-dash is already true and already differentiating. The clause before it is currently aspirational: the CBA constraints don't run and the strategic objective barely moves the answer (see §6, `_timeline` returned exactly 50.0 on both sides of a Tatum↔Dončić swap).

---

## 3. What RosterLab Already Does Well

These are real and should be protected through any refactor.

1. **The four-state legality standard is correct and rare.** `cba/context.py:overall_status` will never emit `verified_legal` when any rule returned `unavailable`. The UI honors it: *"RosterLab never reports a deal as legal while a required check is missing."* Most public tools would have shown a green check.
2. **The provider client is production-grade.** `nba_api/client.py` funnels every call through one path: cache → rate limiter (`rate_limiter.py`, min-interval + bounded semaphore) → bounded retries (`retry.py`) → schema validation (`schemas.py`) → classified exceptions (`exceptions.py`) → health metrics (`health.py`). `data_sync_runs` shows this working: 6 `ProviderThrottledError`/`ProviderTimeoutError` failures on 2026-07-20 were classified and recorded, then succeeded on retry the next day.
3. **Provenance is structural, not decorative.** `ProvenanceMixin` (`db/models.py:52`) puts `source_provider`, `source_record_id`, `source_retrieved_at`, `valid_from/valid_to`, `ingestion_run_id` on every provider table. Every UI panel renders a SOURCE line. 842 data-quality issues are recorded and surfaced rather than swallowed.
4. **Identity resolution refuses to guess.** CSV rows match strictly on official `PLAYER_ID` (573/582; 9 unmatched recorded as `csv_unmatched_player`). Kaggle enrichment fills only NULL fields, preserving 273 conflicts as `kaggle_source_conflict`. 280 unmatched image folders kept for review rather than fuzzy-matched.
5. **Scale discipline in the CSV importer.** `stats_csv.py` stores totals at the JSON top level, per-game under `stats["per_game"]`, and — critically — writes `stat_type='totals'`, which `features.py` never reads. The totals/per-game contamination hazard the README claims to have solved *is actually solved* in the modeling path.
6. **Component exclusion with weight renormalization.** `sensitivity.py:composite_utility` drops `None` components and renormalizes. The UI states it: *"Not scored because the data is missing: Contract value — the remaining weights were rescaled."*
7. **Empty states are designed, not accidental.** `/salary-cap-center` is a well-built three-step import guide rather than a broken dashboard. Missing player photos degrade to initials monograms (`LO`, `YK`, `NW`).
8. **Accessibility is real.** Every drag handle has a keyboard-reachable button with a descriptive `aria-label` (`"Send Josh Giddey to GSW"`). Every chart has a text alternative. Zero console errors observed across all routes.
9. **Testing and CI infrastructure exist and pass.** 114 backend tests in 2.7s, no network. CI: ruff, mypy, pytest+coverage, alembic upgrade, eslint, tsc, vitest, next build, Docker build. A scripted visual-QA harness (`scripts/visual_qa.mjs`) screenshots every route at 7 widths and fails on horizontal overflow.
10. **`docs/limitations.md` is exemplary.** It correctly states that TEI is box-score-only, that defense is structurally under-measured, that the wins conversion is cross-sectional, that clustering is descriptive (silhouette 0.156), and that backend coverage is 65% (measured: 64%). This document is more rigorous than the product it describes.

---

## 4. Critical Weaknesses

Ranked by damage to credibility.

### W1 — TEI is asserted to be in net-rating units. It is not. (P0)

`projection.py:92–95`:

```python
def team_tei_to_net_rating_delta(before, after) -> float:
    """TEI is on a per-100 individual scale; five players share the floor, so a team's
    net-rating shift is approximately the change in minutes-weighted average TEI."""
    return after.team_tei_per_minute - before.team_tei_per_minute
```

TEI is `ridge.predict(X) * 2.5` where the ridge target is `0.6·z(PIE) + 0.4·z(NET_RATING)` (`impact.py:107–111, 209–213`). `TEI_SCALE = 2.5` is annotated *"index points per z-unit; elite seasons land around +5"* — an arbitrary display scale. **Nothing anywhere in the codebase fits TEI to points per 100 possessions.** The docstring is the entire justification.

Two compounding errors:

1. **Units.** An uncalibrated z-index is multiplied by `slope = 2.235` wins/net-rating-point and printed as *"Modeled net-rating change +0.00 per 100 possessions"* and *"+X wins"*. Both numbers are dimensionally meaningless.
2. **A missing factor of 5.** `allocate_rotation` computes `weighted += m / total * effective_tei` with `total = 240` (`projection.py:70, 79`). Since five players are always on the floor, `Σ minutes = 240 = 5 × 48`, so `weighted` is the *average TEI per on-court slot* — one fifth of the five-man unit's summed impact. Even granting the per-100 premise, team net rating would be `5 × weighted`, not `1 × weighted`.

**Observed consequence:** Tatum (TEI 2.03) → Dončić (TEI 3.49) at the top of Boston's rotation = **+0.43 wins**. Giddey → Curry = **+0.00 net rating**. Every headline number in the product is deflated by roughly an order of magnitude.

### W2 — "Defense" is steals per minute. (P0)

`archetypes.py:139–145`:

```python
"shooting": pct("fg3a_rate") * 0.5 + pct("TS_PCT") * 0.5,
"perimeter_defense": pct("stl_per_min"),
"rim_protection": pct("blk_per_min"),
```

`perimeter_defense` — used for both `defense_overall` and `point_of_attack_defense` in `needs.py:159–161` — is *only* steals per minute. Live consequence: **Boston acquiring Luka Dončić is scored as a +0.378 percentile improvement in perimeter defense, and that is the single largest positive contribution to the fit score.** Atlanta is simultaneously listed as **83rd percentile in "Point-of-attack defense"** (a Strength) and **27th percentile in "Overall defense"** (a Need) — both derived from the same shallow proxies pointing in opposite directions.

`shooting` is also wrong: it is 50% three-point *attempt rate* (volume) and 50% true shooting. `FG3_PCT` is ingested in the raw payload but is not a model feature. A high-volume, low-accuracy shooter scores as a good shooter.

### W3 — `NEED_TO_SKILL` maps turnovers to assists. (P0)

`needs.py:165`: `"ball_security": "creation"`, where `creation = pct("AST_PCT")`.

A team with a turnover problem is therefore told to acquire **high-usage, high-assist ball-handlers** — the population most likely to turn the ball over. Live confirmation from `/trades/generate` for Boston (`target_needs: [playmaking, point_of_attack_defense, ball_security]`): the engine recommended **Jordan Poole**.

### W4 — Every player has an identical, enormous uncertainty band. (P0)

`impact.py:219–224`:

```python
residual_std = 0.6
if ...: residual_std = float(result.validation["ridge_residual_std"])   # 0.9848
band = 1.2816 * residual_std * TEI_SCALE                                # = 3.156
weighted["tei_low"]  = weighted["tei"] - band
weighted["tei_high"] = weighted["tei"] + band
```

Measured across all 512 active estimates: `COUNT(DISTINCT ROUND(tei_high - tei_low, 4)) = 1`, width **6.311** for every player. Observed TEI: mean −0.293, **SD 1.182**, range −3.29 to +4.26. So the advertised 10th–90th interval is **±2.67 cross-sectional SD** — it spans essentially the entire league for every single player, from Victor Wembanyama to a two-way rookie. It carries zero player-specific information and no dependence on minutes played, sample size, or age.

Worse, `db/models.py:375–376` documents these columns as `# bootstrap 10th percentile` / `# bootstrap 90th percentile`. **No bootstrap is performed anywhere in the codebase.**

### W5 — Trading your entire roster for nothing scores 72.85/100. (P0)

Reproduced live. Boston sends all 16 players to LAL, receives nothing:

```
composite_utility: 72.85   confidence: medium
components: {performance: 54.13, fit: 54.37, contract: null,
             timeline: null, assets: 82.0, risk: 79.39}
delta_wins: +0.83        rotation_after: []        roster_after: 0
```

Three independent bugs stack:
- `allocate_rotation([])` returns `team_tei_per_minute = 0.0` via the `total = sum(...) or 1.0` guard (`projection.py:70`). **Vacated minutes are valued at 0.0 = league average**, not at replacement level. Emptying a below-average roster therefore *improves* it.
- `_assets` (`evaluation.py:339`): `50.0 + 8.0*(picks_in - picks_out) - 2.0*roster_spots_delta` → `50 − 2×(−16) = 82`. **Losing 16 roster spots is scored as accumulating assets.**
- The composite **ignores legality entirely.** The rules engine correctly returned `verified_illegal` (roster of 0 < the 12-man minimum); the decision score never consults it.

### W6 — The provenance page misreports provenance. (P0)

`data_health.py:79` takes `last_success = MAX(finished_at) WHERE status='succeeded'` across **all** jobs, then `:129` sets `nba_fresh` from it. The most recent successful run is `index_assets` (2026-07-27 01:45) — a job that indexes local JPEG files. The last actual NBA.com sync was 2026-07-21 01:53.

Result, verified in both API and UI:

| Surface | Says |
| --- | --- |
| `/api/v1/data-health` → `tables.*.stale` | `true` for all 7 NBA.com tables |
| `/data-health` source card | **"Current NBA data ✓ fresh · NBA.com via nba_api 1.11.4 · updated Jul 27, 2026, 1:45 AM"** |
| Global nav pill (`shell.tsx:55–60`, `< 48h → "Live data"`) | 🟢 **"Live data"** |
| Homepage (`app/page.tsx:190`) | **"DATA SYNCED Jul 27, 2026, 1:45 AM"** |
| Every roster panel | "updated Jul 21, 2026, 1:53 AM" *(correct)* |

The one page whose entire purpose is to be trustworthy about data currency is the page that misstates it.

### W7 — Archetype labels are visibly degenerate. (P1)

`silhouette = 0.156` (no meaningful cluster structure). k=8 clusters collapse to **five** distinct concepts; three labels are pure disambiguation suffixes from `archetypes.py:113–117`:

| Label | Players |
| --- | --- |
| bench scorer | 131 |
| **bench scorer (2)** | 96 |
| **primary creator (3)** | 92 |
| two-way wing | 86 |
| rim-running center | 81 |
| **primary creator (2)** | 61 |
| secondary creator | 47 |
| primary creator | 38 |

Rendered to users verbatim: **Stephen Curry "primary creator (2)"**, **Draymond Green "primary creator (3)"**, **CJ McCollum "primary creator (2)"**, **Nikola Vučević "primary creator"**, **Lachlan Olbrich (C) "two-way wing"**, **Onyeka Okongwu (C) "bench scorer (2)"**. `docs/limitations.md` disclaims this; the UI does not.

### W8 — The candidate generator produces fantasy trades and silently truncates its search. (P1)

Live `/trades/generate` for Boston returned, among the top five:

```
CLE  in: [Donovan Mitchell]                out: [Jordan Walsh]   focal 69.16  counterparty 49.33
CLE  in: [Donovan Mitchell, James Harden]  out: [Jordan Walsh]   focal 68.34  counterparty 52.00
```

Boston acquires Mitchell **and** Harden for a 22-year-old end-of-bench wing, and Cleveland's utility (52.0) clears `COUNTERPARTY_MIN_UTILITY = 42.0`, so it is surfaced as mutually acceptable. Additionally `evaluations_run: 400` = exactly `EVALUATION_BUDGET` (`candidates.py:22`), meaning the loop over `db.scalars(select(Team)...)` — which has **no ORDER BY** — exhausted its budget after roughly six of 29 counterparties, in nondeterministic insertion order, **with no disclosure to the user**.

### W9 — Component scores saturate, flatline, or double-count. (P1)

| Component | Scaling | Observed |
| --- | --- | --- |
| `fit` | `50 + score*120` (`evaluation.py:277`) | **100.0 (clipped)** on a routine star-for-star swap. Ceiling reached at `score = 0.417`. |
| `timeline` | `50 + (align_in − align_out)*100` | **exactly 50.0** for Tatum(28)↔Dončić(27) — the age buckets in `age_curve.timeline_alignment` are 4–5 years wide. |
| `assets` | `50 + 8*(picks_in − picks_out) − 2*Δspots` | **All picks are worth exactly 8 points.** A 2027 unprotected first = a 2033 second. Year, protections, and origin team are ignored. |
| `risk` | `60*prob_positive + 40*avail_in` | `prob_positive` comes from a Monte Carlo whose only real inputs are TEI and minutes → **`risk` is largely a restatement of `performance`.** With weights `contend = {performance 0.32, risk 0.20}`, on-court impact is effectively weighted ~0.52. |

### W10 — Documentation is more rigorous than the product. (P1)

`docs/limitations.md` correctly warns that defense is under-measured, that clustering is descriptive, that the wins conversion assumes context stability. The UI presents "Point-of-attack defense — 83rd" as a **Strength** with no caveat, prints "primary creator (3)" as a role, and states "**+0.00 per 100 possessions**" as a measurement. A reviewer who reads the docs will trust the project; a reviewer who only uses the product will not — and the product is what gets demoed.

---

## 5. Data Audit

### 5.1 Live inventory (`backend/tradelab.db`, 17,059,840 bytes)

| Table | Rows | Live/Cached/Manual/Empty | Refresh | Seasons | Used by |
| --- | --- | --- | --- | --- | --- |
| `teams` | 30 | nba_api, cached (**stale**) | manual `make sync-data` | n/a | everywhere |
| `players` | 5,121 | nba_api + Kaggle bio enrichment | manual | all-time | Explorer, rosters |
| `rosters` | 530 | nba_api `CommonTeamRoster`, cached (**stale**) | manual | 2025-26 | Trade Evaluator, Team Outlook |
| `player_season_stats` | 5,715 | nba_api (5,142) + CSV (573) | manual | 2023-24 → 2025-26 | features, Explorer |
| `team_season_stats` | 180 | nba_api | manual | 3 seasons × base/adv | needs, wins calibration |
| `standings` | 90 | nba_api | manual | 3 seasons | team banners, calibration |
| `games` | 1,230 | nba_api | manual | 2025-26 | **nothing** |
| `player_game_stats` | **0** | — | — | — | — |
| `contracts` / `contract_years` | **0 / 0** | not configured | — | — | **blocks 4 modules** |
| `draft_picks` | **0** | not configured | — | — | blocks Stepien, pick valuation |
| `injuries` | **0** | not configured | — | — | blocks availability quality |
| `transactions` | **0** | not configured | — | — | blocks market comps |
| `media_assets` | 2,519 | local files, derived | `make index-assets` | n/a | photos/logos |
| `player_impact_estimates` | 1,536 (512 active) | model output | `make train` | 2025-26 | TEI everywhere |
| `player_archetypes` | 632 | model output | `make train` | 2025-26 | role labels |
| `team_needs` | 279 | model output | `make score` | 2025-26 | Team Outlook, fit |
| `model_versions` | 9 (3 active) | model registry | `make train` | — | Data Health |
| `data_quality_issues` | 842 open | derived | each sync | — | Data Health |
| `scenarios` / `comparison_sets` | 5 / 50 | user + **test fixtures** | user | — | Strategy Lab |
| `trade_proposals` | 3 | **all test artifacts** | user | — | Strategy Lab |

### 5.2 Provenance & reproducibility per key metric

| Metric | Source | Ingestion | Reproducible? | Risk |
| --- | --- | --- | --- | --- |
| Roster / record / net rating | NBA.com `CommonTeamRoster`, `LeagueDashTeamStats`, `LeagueStandings` | `nba_api` → `ingestion/jobs.py` | ✅ deterministic | 6 days stale; no scheduler |
| Per-game box score | NBA.com `LeagueDashPlayerStats` (PerGame) | `nba_api` | ✅ | mode not asserted in schema contract |
| Season totals (Explorer) | user CSV `nba_player_stats_2026.csv` | `stats_csv.py`, `PLAYER_ID` join | ✅ (file is gitignored) | **manually placed; no refresh path** |
| Bio / draft | Kaggle `wyattowalsh/basketball` v238 | `kagglehub` → NULL-fill only | ✅ (sha256 recorded) | ~700 MB; snapshot frozen |
| Photos / logos | local dirs | `assets/indexer.py`, name→ID | ✅ | 84% roster coverage; 280 unmatched |
| **TEI** | derived | `analytics/train.py` | ⚠️ seeded but **units undefined** | W1, W4 |
| **Team needs** | derived | `analytics/score.py` | ✅ transparent percentiles | W2, W3; 135/279 rows have severity 0 |
| **Payroll / apron / salary matching** | — | — | ❌ **no data** | blocks the flagship feature |

### 5.3 Data-quality findings

- **842 open issues:** 280 `asset_unmatched_player_dir`, 273 `kaggle_source_conflict`, 9 `csv_unmatched_player`. All warnings, all surfaced. Healthy behavior.
- **`games` (1,230 rows) is ingested and never used.** No consumer anywhere in `app/`. Dead ingestion cost.
- **43 rostered players have no TEI**, and `evaluation.py:179` silently substitutes `tei = 0.0` — which is **above** the league mean of −0.293. Combined with `availability = 0.75` and `minutes = 12.0` defaults (`:191–192`), an unmodeled two-way rookie is scored as an average NBA rotation player. The roster API honestly returns `null`; the evaluator quietly overwrites it. **This is the sharpest single violation of the stated honesty standard.**
- **`EFF` is misclassified as a rate.** `stats_csv.py:90` puts `EFF` in `_RATE_FIELDS`. It is a season counting total (Dončić: 2146.0). The Player Explorer renders `2146.0` in the **"Per game"** view under the caption *"Shooting rates and EFF are scale-independent"* — which is false, and is exactly the totals/per-game confusion the README claims to have eliminated.
- **Season/league-year skew:** `current_season = 2025-26` but `cap_league_year = 2026-27`. Documented in `config/__init__.py`, but it means 2025-26 performance is evaluated against 2026-27 cap rules with 2025-26 rosters — three different temporal frames in one verdict.
- **Availability systematically over-states injury-prone players.** `availability.py` divides by `Σ(decay^i) × 82` computed **only over seasons for which the player has a stats row**. A player who missed an entire season has no row, so that season silently disappears from the denominator.
- **No `.env` file exists.** All settings run on `config/__init__.py` defaults. Every "configure a provider" instruction in the UI requires a file the repo never creates on `make setup` unless the template copy succeeds.

### 5.4 Datasets that would materially improve the platform

Ordered by value per unit of effort.

| # | Dataset | Enables | Why it matters | Obtainable? | Source | Concerns |
| --- | --- | --- | --- | --- | --- | --- |
| **1** | **Player contracts & cap holds** | Salary matching, apron/tax status, payroll, contract-value component, surplus value | **Unblocks 4 dead modules and the entire differentiator.** Without it RosterLab is worse than a free trade machine. | ✅ Already built: `bbref_provider.py` parses a locally-saved HTML snapshot | Basketball-Reference snapshot (implemented); Spotrac for options/guarantees | Manual snapshot = staleness. Add a `source_date` freshness badge. Do not scrape live. |
| **2** | **Draft-pick ownership + protections** | Real pick valuation, Stepien certification, rebuild-path modeling | `_assets` currently prices every pick at 8 points. Picks are the primary currency of NBA trades. | ⚠️ Semi. No clean API. | RealGM / Spotrac pick tables, manually curated into `draft_picks` (table already exists, `is_verified` flag already exists) | ~450 rows, hand-maintained. High maintenance, very high payoff. |
| **3** | **On/off and lineup data** | Replace steals-as-defense; real lineup interaction; diminishing returns | Directly fixes W2, the most basketball-embarrassing defect. | ✅ `nba_api`: `LeagueDashPtDefend`, `LeagueDashLineups`, `TeamPlayerOnOffDetails` | Already inside the hardened client. Small-sample noise on lineups → require possession minimums. |
| **4** | **Play-type + tracking (Synergy via nba_api)** | Archetypes with basketball meaning; role fit; spacing | Replaces a silhouette-0.156 k-means with interpretable role vectors. | ✅ `SynergyPlayTypes`, `LeagueDashPtStats` | Endpoint stability varies; rate-limit budget. |
| **5** | **Shot-location / shot-zone** | Spacing model, gravity, shot-profile fit | "Shooting = 3PA rate" is currently indefensible. | ✅ `ShotChartDetail`, `LeagueDashPlayerShotLocations` | Large payloads; cache aggressively. |
| **6** | **Injury / availability history** | Real risk modeling, survival analysis | `INJURY_DATA_PROVIDER` hook already exists and is unset. | ⚠️ No free authoritative feed | Pro Sports Transactions (scrape-terms risk), or manual | Label carefully as historical, never predictive. |
| **7** | **Transaction history** | Comparable-trade retrieval — *"the five most similar completed deals"* | Turns model output into evidence. Uniquely credible. | ✅ Kaggle DB already downloaded may contain it; NBA.com `Transactions` | Parsing/normalization effort. |
| **8** | **Multi-season historical salaries** | The actual Contract Predictor on the roadmap | Enables cap-% log-salary regression instead of the hardcoded `market_share` curve. | ⚠️ Manual multi-year BBRef snapshots | Roadmap-correct to defer. |
| **9** | **Playoff-split stats** | Regular-season vs playoff performance | A contender's evaluation should not use regular-season rates. | ✅ `nba_api` `SeasonType='Playoffs'` | Small samples; needs shrinkage. |
| **10** | **Estimated future cap projections** | Multi-year cap sheet, extension planning | Needed for any timeline analysis. | ✅ NBA Communications announcements | Already the pattern used for `league_cap_parameters`. Extend the YAML. |

Explicitly **unavailable / do not pursue**: Second Spectrum tracking, proprietary RAPTOR/EPM/LEBRON, internal team medicals, agent-side contract intel, private draft boards. None should be implied anywhere in the UI.

---

## 6. Feature-by-Feature Audit

### 6.1 Trade Evaluator — `frontend/app/trade-evaluator/page.tsx` (2,679 LOC)

**Works end-to-end:** yes. Drag-and-drop plus accessible send buttons, live rules check, evaluate, save, share link.

**Decision support or demo?** *Half.* The rules-check panel is real decision support. The evaluation panel is a demonstration.

| Check | Finding |
| --- | --- |
| Output understandable? | ✅ Excellent plain-language layering. |
| Methodology defensible? | ❌ W1, W2, W9. |
| Actionable? | ❌ Giddey→Curry = "−0.0 wins, 49% chance it helps." |
| Can the user see *why*? | ⚠️ Components/drivers/tornado shown, but the driver is a saturated `fit` score built on a broken defensive proxy. |
| Beats a public trade machine? | ❌ Not today — it cannot check salary matching. |

**Additional defects found:**

- **The rotation-minutes chart omits the player being acquired.** `evaluation.py:242–243` returns `before.detail[:12]` / `after.detail[:12]` — sliced **before sorting**, in roster order, with incoming players appended last. Observed for CHI acquiring Curry: *"Josh Giddey: 20.4 → 0.0 (−20.4); **Jalen Smith: 0.0 → 12.4 (+12.4)**"* — Jalen Smith was not in the trade, and **Stephen Curry does not appear in the chart at all.** The frontend join (`page.tsx:2210–2222`) is correct; the backend truncation is the bug.
- **`fanVerdict` labels are semantically inverted** (`lib/format.ts:58–65`): `≥58 strong` → `≥48 mixed` → `≥40 upside` → `<40 poor`. A **worse** score (46) reads as *"High-risk upside"* while a **better** score (52) reads as *"Mixed outcome."*
- **Rule-count copy is wrong:** *"4 checks could not run: SALARY_DATA_AVAILABLE, SALARY_MATCHING"* — says four, names two.
- **`-0.0` renders literally** for negative-zero impacts (Draymond Green).
- **Salary and years columns are `—` on all 18 rows of all 30 teams** — dead visual weight on the densest surface in the app.

**Highest-impact single fix:** calibrate TEI→net-rating (W1). Every number on this page inherits it.

### 6.2 CBA Rules Engine — `backend/app/cba/`

**The best-engineered and most-crippled component in the repo.**

| Rule | Status today | Note |
| --- | --- | --- |
| `SALARY_DATA_AVAILABLE` | always `unavailable` | no contracts |
| `SALARY_MATCHING` | always `unavailable` | the expanded-TPE band math in `salary.py:22–33` is internally consistent (band edges meet exactly at $8.846M / $35.384M for the 2025-26 cap) and cannot run |
| `SECOND_APRON_AGGREGATION` | `pass` trivially | needs payroll |
| `MINIMUM_TEAM_SALARY` | skipped (`continue`) | needs payroll |
| `ROSTER_SIZE` | **the only rule that ever runs**, `confidence: medium` | `types_known` requires `contract_provider_configured` → permanently false |
| `RECENTLY_SIGNED` | skipped | needs `signed_date` |
| `NO_TRADE_CLAUSE` | never fires | needs contracts |
| `TWO_WAY_EXCLUSION` | never fires | needs contract types |
| `STEPIEN_FUTURE_FIRSTS` | only ever emits `unavailable` | placeholder |

So: **1 of 9 rules executes, at medium confidence.** Every trade in this audit returned `conditionally_valid`.

Genuine coverage gaps to document even after contracts load (`docs/cba-rule-coverage.md` already lists most): sign-and-trades, existing traded-player exceptions, base-year compensation, poison-pill, cash considerations and the annual cash limit, hard-cap triggers, aggregation timing windows, and the 1-for-1 apron exception. One point to verify against source: `max_incoming_at_or_above_first_apron` adds `params.allowance` ($250K) above the first apron; the 2023 CBA restriction is commonly cited as a flat 100% of outgoing salary with no allowance.

Also: a trade carrying only a `NO_TRADE_CLAUSE` warning still resolves to `verified_legal` (`context.py:overall_status` only inspects `fail` and `unavailable`). A deal requiring player consent should not be "verified legal."

### 6.3 Player Impact (TEI) — `backend/app/analytics/impact.py`

Covered in §4 (W1, W4) and §7.

Face-validity check on the live model: the **top 15 are basketball-sane** (Wembanyama 4.26, Giannis 3.90, Jokić 3.68, Dončić 3.49, Embiid 3.35, Davis 3.02, SGA 2.81). The **middle and bottom are not**:

| Player | TEI | Problem |
| --- | --- | --- |
| Charles Bassey | **+1.30** | Fringe backup center out-rates Jimmy Butler; per-minute rate stats reward low-minute bigs |
| Nikola Vučević | **+1.15** | 57% of Tatum's value |
| Jimmy Butler III | **+0.60** | |
| Derrick White | **+0.32** | Elite two-way guard ≈ league average |
| Dyson Daniels | **+0.10** | Premier point-of-attack defender, invisible to the model |
| Draymond Green | **−0.00** | Defensive anchor scored at exactly zero |
| Payton Pritchard | **−0.24** | |
| Sam Hauser | **−1.54** | Elite shooter penalized by `z_fg3a_rate` coefficient of **−0.0596** |

The pattern is unambiguous: **TEI measures box-score volume and rebounding, and is blind to defense and spacing.** `tei_offense`/`tei_defense` are computed by a *different* formula (`component_index`, the weighted-index path) than `tei` (the ridge path), so they do not decompose it — Wembanyama shows `tei 4.26 / off 2.43 / def 6.84`. Displaying them adjacently implies an additive decomposition that does not exist.

### 6.4 Team Outlook — `frontend/app/team-outlook/[teamId]/page.tsx`

Best-looking page in the product. Two concrete defects:

- **The same metric appears under both Strengths and Needs.** `page.tsx:435`: `{(weaknesses.length ? weaknesses : sortedNeeds.slice(0, 4)).map(...)}`. When a team has no need above `severity ≥ 0.35`, the UI falls back to the **first four rows regardless of severity** — including severity-0 rows, which also qualify as Strengths (`severity === 0 && percentile ≥ 65`). Observed on ATL: **"Defensive rebounding 67th" listed simultaneously as a Strength and as a Need**, with a zero-length bar under a caption reading *"Longer bar under Needs = larger shortfall."* Two of 30 teams currently hit this path.
- **"Competitive window: Open now"** is derived from **average rotation age alone** (`windowLabel(avgRotationAge)`, `page.tsx:163`). No record, payroll, contract horizon, or asset base enters a claim presented as a strategic conclusion.

### 6.5 Strategy Lab — `frontend/app/strategy-lab/page.tsx` (1,743 LOC)

Conceptually the strongest idea in the product: re-weight *stored* component scores without re-running the model, so numbers cannot drift. Dirichlet rank stability and tornado sensitivity are legitimately sophisticated.

Blocked by three things: (1) it inherits every component defect from §6.1; (2) `rank_stability` requires ≥2 alternatives to mean anything; (3) **its shipped sample content is test data** — "E2E RosterLab deal", "Smoke test deal", "Alt deal", with `BOS — Contend now` appearing three times in the scenario picker.

### 6.6 Player Explorer — `frontend/app/player-explorer/page.tsx`

Clean, fast, honest ("LEAGUE PERCENTILES FROM THIS SAME SET"). Three problems: the `EFF` totals-in-per-game-view bug (§5.3); **no TEI column** (the platform's own metric is absent from its research surface); and **no minimum-games filter or small-sample flag** — Jayson Tatum ranks 27th in PTS/g on a **16-game** sample with no visual warning.

### 6.7 Salary-Cap Center — `frontend/app/salary-cap-center/page.tsx` (741 LOC)

Currently a 741-line import wizard. Genuinely well-crafted as an empty state. Zero function until contracts load.

### 6.8 Candidate Generator ("Suggest deals") — `backend/app/services/candidates.py`

Covered in W8. Coverage: **19%**. Recommends two All-Stars for a bench wing, targets turnovers by acquiring high-assist guards, cannot check salary legality, and silently searches ~20% of the league. **This is the feature most likely to end a front-office demo badly.**

### 6.9 Executive Report — `backend/app/services/reports.py`

Structure is exactly right for the audience (recommendation → rationale → basketball → financial → risks → assumptions → alternatives → open questions → freshness). Two content defects:

- Live output for "Boston sends Jayson Tatum, receives nothing": *"Projected regular-season impact: **−0.2 wins**"*, *"P(positive) = 42%"*.
- *"Historical availability of **incoming** players: 85% of team games"* — printed when `incoming` is **empty**; 0.85 is the hardcoded fallback in `_risk` (`evaluation.py:355`). A defaulted constant presented as a measurement, inside the document meant to be handed to a decision-maker.

### 6.10 Data Health — `backend/app/services/data_health.py` + `frontend/app/data-health/page.tsx`

Excellent design (six plain-language source cards, coverage, exact next step, technical drawer). Undermined entirely by W6.

---

## 7. Machine Learning Audit

### 7.1 `player_impact` — ridge regression

| Dimension | Finding |
| --- | --- |
| **Target** | `0.6·z(PIE) + 0.4·z(NET_RATING)` next season, minutes-weighted within season (`impact.py:107–111`) |
| **Training data** | 447 player-season transitions (`2023-24 → 2024-25`) |
| **Validation** | 464 transitions (`2024-25 → 2025-26`) |
| **Test set** | ❌ **none** |
| **Features** | 15 (14 z-scored + raw `AGE`) |
| **Split** | Time-aware forward-only ✅ — genuinely correct and better than most portfolio work |
| **Time leakage** | ✅ none |
| **Selection leakage** | ❌ **model selection happens on the validation set** (`impact.py:181`). The reported "held-out MAE 0.637" is a *selection* score, not a held-out score. The README states it as held-out. |
| **Missing values** | `.fillna(0.0)` on z-scores — imputes to the league mean, silently |
| **Model class** | `Ridge(alpha=10)`, α never tuned |
| **Baselines** | ✅ Two, both good: persistence (0.717) and a transparent index (0.645) |
| **Result** | ridge 0.637 vs index **0.645** — a **1.2% improvement over a fixed weighted z-score index**. This does not justify the ML. |
| **Calibration** | ❌ none |
| **Uncertainty** | ❌ constant ±3.156 for all 512 players (W4) |
| **Explainability** | ❌ coefficients are uninterpretable (below) |
| **Versioning** | ✅ `model_versions` with features, target, metrics, `code_commit` — genuinely good; but 9 rows contain **duplicate version strings** (`v202607210204` appears both active and inactive) |
| **Retraining** | manual `make train` only |
| **Overstates certainty?** | ❌ Yes — see §7.5 |

**Three specific defects:**

1. **`AGE` is unstandardized inside an L2-penalized model.** Fourteen features are z-scores (SD ≈ 1); `AGE` has SD ≈ 4.3 and mean ≈ 26. Ridge penalizes coefficients on the raw scale, so `AGE` is shrunk incomparably. Its coefficient is −0.0051 — effectively excluded by an artifact of scaling, not by evidence. Wrap in a `Pipeline([StandardScaler(), Ridge()])`.
2. **The target's own components carry negative coefficients:** `z_PIE = −0.086`, `z_NET_RATING = −0.030`. Classic multicollinearity suppression. If the methodology page surfaces these, it tells a basketball audience that *higher PIE predicts lower impact.* Indefensible in front of the target user.
3. **Survivorship bias.** `_make_transitions` uses `how="inner"` (`impact.py:130`), so only players who appear in **both** seasons train the model. Players who fell out of the league — the exact population an aging/decline model must learn from — are structurally excluded.

**Recommendation: retire the ridge model.** It beats the transparent index by 1.2%, is not interpretable, and its coefficients actively mislead. Ship the **weighted z-score index as the production model** (it is already written, already documented, already an existing baseline) and spend the saved complexity budget on the things that actually matter: on/off data, a real defensive input, and a genuine TEI→net-rating calibration.

### 7.2 `player_archetype` — k-means (k=8)

Silhouette **0.156**. Labels degenerate (W7). Coverage 28%. `_label_from_center` is an ordered `if` chain where "primary creator" (high USG + high AST) fires first and swallows three clusters. `N_CLUSTERS = 8` is hardcoded with no k-selection procedure.

**Recommendation: replace with rule-based role assignment on interpretable thresholds** (usage, assist rate, 3PA rate, rim rate, height, minutes) — or, better, cluster over Synergy play-type distributions where clusters have basketball meaning. Do not ship "primary creator (3)" to any user.

### 7.3 `team_projection` — wins ~ net rating

`slope = 2.235`, `intercept = 40.93`, `R² = 0.953`, n = 90. The relationship is real and the slope is plausible (literature ≈ 2.7). **But the R² is in-sample** (`np.polyfit` then residuals on the same data, `projection.py:105–117`), reported to users as a validation metric. Trivially fixable with k-fold.

The real problem is not this model — it is that its input (`delta_net`) is not a net rating (W1).

### 7.4 Monte Carlo — `analytics/uncertainty.py`

2,000 draws over TEI (normal), availability (beta, κ=40), and slope (normal, σ = 15% of slope — a hardcoded constant rather than the fitted `residual_std = 2.894` that is sitting right there in `model_versions`).

The structure is sound, but it is **theater**: every player's `tei_sigma` derives from the same constant band (W4), draws are independent (no correlation between teammates or between availability and impact), and the seed is fixed. The output is therefore a deterministic, near-analytic function of minutes shares. It looks like uncertainty quantification and conveys almost no information. It also inherits W1 wholesale, which is why a Tatum↔Dončić swap produced an 80% interval of **[−0.40, +1.66] wins**.

### 7.5 Does the interface overstate certainty?

**Yes, in five specific ways:**

1. `"Modeled net-rating change +0.00 per 100 possessions"` — a unit the model has never been calibrated to.
2. `"median −0.0 wins · 49% chance it helps"` — one-decimal wins and a whole-percent probability from an uncalibrated chain.
3. `"IMPACT +1.4"` per player, with the ±3.16 band nowhere near it.
4. `"Point-of-attack defense — 83rd"` presented as a measured strength when it is a steals percentile.
5. `"Historical availability of incoming players: 85%"` when the value is a hardcoded default and there are no incoming players.

### 7.6 Where ML is and isn't justified

| Task | Current | Recommended |
| --- | --- | --- |
| Player impact | Ridge (beats index by 1.2%) | **Transparent weighted index** + explicit defensive input. Revisit ML only when on/off data exists. |
| Archetypes | k-means, silhouette 0.156 | **Rules over interpretable thresholds**, or clustering over play-type vectors |
| Wins mapping | Linear, in-sample R² | Keep; add k-fold + report out-of-sample RMSE |
| Trade legality | Rules engine | **Correct as-is** — never model this |
| Pick valuation | `8.0 × count` | **Empirical curve** fit on historical pick→career-value (surplus by slot); a lookup table, not a model |
| Contract value | Hardcoded `market_share` curve | **Log-cap-% regression** once multi-year salary history exists (roadmap is right) |
| Team needs | Percentile rules | **Correct approach**; fix the proxies, not the method |
| Comparable trades | — | **Similarity retrieval over `transactions`** — the highest-credibility unbuilt feature |

**Do not add** deep learning, embeddings, causal inference, or ensembles. Nothing here is bottlenecked on model capacity; everything is bottlenecked on measurement and calibration.

---

## 8. Basketball Methodology Audit

| Concept | Handled? | Evidence |
| --- | --- | --- |
| Player role | ⚠️ degenerate | k-means, silhouette 0.156 |
| Usage | ✅ | `USG_PCT` is a feature |
| Efficiency | ✅ | `TS_PCT` is a feature |
| **Spacing** | ❌ | `fg3a_rate` (volume) is used; `FG3_PCT` is not a feature. Sam Hauser: **−1.54**. |
| Shot profile | ❌ | No shot-location data |
| **Defensive versatility** | ❌ | `perimeter_defense = steals/min`. Dyson Daniels **+0.10**, Draymond Green **−0.00** |
| Positional flexibility | ❌ | Position used only for UI grouping; no positional constraint in `allocate_rotation` |
| Playmaking | ⚠️ | `AST_PCT` only; no potential assists, no gravity |
| Rebounding | ✅ | `OREB_PCT`/`DREB_PCT` |
| Turnovers | ⚠️ | `TM_TOV_PCT` is a feature, but `NEED_TO_SKILL` maps ball security **to assist rate** (W3) |
| **Lineup interactions** | ❌ | None |
| **Diminishing returns** | ⚠️ crude | Only `fit.py:GAMMA = 0.35` above the 70th percentile |
| Team context | ⚠️ | Team needs yes; but `NET_RATING` in the *target* means TEI partly rewards **playing on a good team** |
| Pace | ⚠️ | `pts_per75` normalizes; `PACE` ingested, unused |
| Coaching / scheme | ❌ | None |
| Age | ⚠️ | Hardcoded piecewise curve, 4–5 year buckets |
| Development trajectory | ❌ | `age_delta` is a constant per bucket; no player-specific trajectory |
| Contract value | ❌ | No data; heuristic anchored outside its own support (below) |
| Team timeline | ⚠️ | "Competitive window" = average roster age only |
| Opportunity cost | ❌ | No consideration of what else the assets could buy |
| **Reg. season vs playoffs** | ❌ | Regular-season rates only, even under `strategy = "contend"` |
| Uncertainty / small samples | ❌ | Constant band; Tatum's 16-game season is unflagged in the Explorer |

### Where value is treated as additive but must not be

1. **`team_tei_per_minute` is a pure minutes-weighted average** (`projection.py:70–79`). No lineup interaction, no positional balance, no floor-spacing constraint. Trading all three centers redistributes their minutes to guards with zero penalty.
2. **Rotation allocation spreads 240 minutes across the *entire* 16–18-man roster**, proportional to baseline minutes. Observed: Tatum's 35.6 mpg baseline became **25.4 allocated minutes**; Curry, acquired by Chicago, received minutes but never surfaced. Stars are systematically diluted and deep-bench players systematically inflated, which flattens every performance delta.
3. **`_assets` treats picks as interchangeable units** at 8 points each.
4. **`_risk` is not orthogonal to `performance`** — both are driven by the same TEI draws, so on-court impact is double-weighted in the composite.

### Constants that are not grounded in the data they operate on

| Constant | Location | Problem |
| --- | --- | --- |
| `REPLACEMENT_TEI = -2.0` | `projection.py:73` | −1.45 SD; only ~25 of 512 rostered players are below it. This is a **7th-percentile NBA rotation player**, not replacement level. |
| `market_share`: *"star (TEI +5) ≈ 25% of cap"* | `evaluation.py:295–298`, `docs/model-card-market-value.md` | **Zero players reach TEI +5.** Max is 4.26; only 8/512 exceed +2.5. The valuation curve is anchored outside the support of its own input. |
| `age_delta = −1.0/yr` at 36+ | `age_curve.py:47` | **0.85 SD per season** given TEI SD = 1.182 |
| `GAMMA = 0.35`, `×120` (fit), `×5` (perf), `×250` (contract), `8.0` (picks) | `fit.py:12`, `evaluation.py:277/238/308/339` | Six independent, undocumented, unvalidated scale factors determining every score |

### Proposed rigorous frameworks

| Quantity | Replace with |
| --- | --- |
| **Player value** | Box-score prior **shrunk toward** an on/off signal (empirical-Bayes by minutes played), reported in points per 100 possessions **calibrated against team net rating**, with per-player intervals that widen with fewer minutes. |
| **Team fit** | Marginal-value-over-current-rotation: value of the incoming player *given* the top-8 already on the roster, using lineup-level data — not a percentile delta against a static skill vector. |
| **Trade value** | Surplus value = (projected multi-year production, age-adjusted) − (contracted cost), in cap %, with pick surplus from an empirical slot→career-value curve. |
| **Contract value** | Log(cap %) regression on impact, age, minutes, role, availability, contract year — once multi-year salary data exists. |
| **Roster balance** | Positional minute coverage + a spacing constraint (≥3 credible shooters on the floor) + creation load, checked against the allocated rotation. |
| **Strategic alignment** | Explicit multi-year objective (win-now W, 3-year W, asset base, cap flexibility) with the user setting the trade-off — not a hardcoded 6-vector. |
| **Expected transaction impact** | Distribution over 3 seasons, not a point estimate for one, with correlated draws and an explicit replacement-level floor. |

---

## 9. UI/UX Audit

Reviewed at 1440×900 and 710×1562. Design quality is genuinely high: coherent dark analytical language, per-team color theming, disciplined typography, real empty states, monogram photo fallbacks, keyboard-accessible drag alternatives, no console errors on any route.

### Visual and content defects found

| # | Location | Defect | Severity |
| --- | --- | --- | --- |
| 1 | Global nav / homepage / Data Health | "Live data" 🟢, "DATA SYNCED Jul 27" on 6-day-old NBA data (W6) | **Critical** |
| 2 | Team Outlook | Same metric under **Strengths and Needs simultaneously**; zero-length bars under "Longer bar = larger shortfall" | **High** |
| 3 | Trade Evaluator | Rotation chart omits the acquired player, invents a +12.4-min gain for an untraded one | **High** |
| 4 | Everywhere | `primary creator (2)` / `(3)`, `bench scorer (2)` as player role labels | **High** |
| 5 | Trade Evaluator | Verdict scale inverted — 46 = "High-risk upside", 52 = "Mixed outcome" | **High** |
| 6 | Player Explorer | `EFF 2146.0` in the "Per game" view, captioned "EFF is scale-independent" | **High** |
| 7 | Strategy Lab | "Smoke test deal" / "E2E RosterLab deal" as shipped sample content; duplicate scenarios in picker | **High** (demo-killing) |
| 8 | Trade Evaluator | *"4 checks could not run"* then names 2 | Medium |
| 9 | Trade Evaluator | `IMPACT -0.0` rendered for Draymond Green | Low |
| 10 | Trade Evaluator | `salary — · years —` on 18 rows × 30 teams | Medium |
| 11 | Trade Evaluator | "STRENGTHS GAINED: … Downside risk" — gaining risk reads as bad, means the opposite | Medium |
| 12 | Cross-module | Team selection does not persist (CHI → ATL) despite the homepage promise | Medium |
| 13 | Player Explorer | No TEI column; no minimum-GP flag (Tatum ranked on 16 games) | Medium |
| 14 | Routes | `/players/zzz`, `/team-outlook/not-a-team`, `/trades/nonexistent-id` all return **HTTP 200** | Low |
| 15 | Salary-Cap Center | Screenshot capture timed out once at 1440×900 — worth a render-perf check | Low |

### Where the UI presents false precision

- Wins to one decimal and probabilities to the percent, from an uncalibrated unit chain.
- Per-player `IMPACT` to one decimal with no visible interval.
- Percentile "Strengths" built on steals and 3PA volume.
- A "competitive window" verdict from one number (average age).
- A defaulted 0.85 availability printed as a measured rate in the executive memo.

### Where users lack guidance

- No explanation of what a TEI unit *is*. The tooltip says "estimated impact"; there is no scale anchor.
- No "what would change this verdict?" path — the tornado shows weight sensitivity but not *data* sensitivity.
- No comparable-trade evidence anywhere.

### Workflow friction

Building a two-team, four-player deal takes ~8 interactions before any output. There is no "load a recent real trade" starting point and no team-need-driven entry (*"Boston needs X — show me who provides it"*), which is how the target user actually thinks.

### Components that should be standardized

`ui.tsx` (578) + `charts.tsx` (479) + `media.tsx` + `court.tsx` + `brand.tsx` are a reasonable system, but `trade-evaluator/page.tsx` (2,679 LOC) and `strategy-lab/page.tsx` (1,743 LOC) contain large amounts of locally-defined presentational logic (`ImpactTab`, `FitTab`, `ComponentBars`, `BeforeAfterBars`) that belongs in the shared layer.

---

## 10. Engineering Audit

### Strengths

- **Layering is clean:** `api/v1` → `services` → `analytics`/`cba` → `db`. No business logic in routers.
- **Provider isolation is exemplary:** every NBA.com call goes through one function.
- **Typed throughout:** SQLAlchemy 2.0 `Mapped[]`, Pydantic settings, mypy in CI, `tsc --noEmit` in CI.
- **Error contract is deterministic:** `{"error": {code, message, request_id}}` everywhere, with `x-request-id` echoed.
- **Security headers set:** `nosniff`, `DENY`, `no-referrer`. In-process per-IP rate limiter with an asset-path exemption.
- **Migrations real:** Alembic with 2 revisions; CI runs `upgrade head`.
- **Docker Compose:** Postgres 16 + Redis 7 + API + worker + frontend.
- **Repo hygiene:** no data, images, or secrets committed; `.gitignore` is thorough; clean linear history; conventional commit messages.

### Technical debt and fragile paths

| # | Issue | Location | Impact |
| --- | --- | --- | --- |
| 1 | **N+1 query storms.** `_team_payroll` issues 2 queries per rostered player; `build_trade_context` calls it per team; `/trades/generate` runs ~400 evaluations × 2 teams → **~27,000 queries per request** (currently cheap only because `contracts` is empty). | `cba/builder.py:39–72`, `services/candidates.py` | Will degrade badly the moment contracts load |
| 2 | `_roster_profile` runs one `PlayerSeasonStats` query **per player per team** | `analytics/score.py:47–60` | ~530 extra queries per `make score` |
| 3 | **Cold-cache `_skills()` rebuilds the whole feature frame inside the request path** — measured **1.16s** (1,714 rows → pandas → 632 skill vectors, `player_skill_vector` is O(n²) over the league frame) | `services/evaluation.py:146–161` | First request after any data-version bump stalls |
| 4 | **Oversized components:** `trade-evaluator/page.tsx` 2,679 LOC, `strategy-lab/page.tsx` 1,743 LOC | frontend | 4,422 of 12,169 frontend LOC in two files |
| 5 | **`recharts` (~500 KB) is imported by `charts.tsx` alongside hand-rolled SVG charts** | `components/charts.tsx:25` | Verify which chart types actually need it |
| 6 | **`zod` and `react-hook-form`/`@hookform/resolvers` are dependencies with zero imports** in `app/`, `components/`, or `lib/` | `package.json` | Dead dependencies |
| 7 | **Duplicate model versions:** `v202607210204` exists as both active and inactive rows; version string is a minute-resolution timestamp so two trainings in one minute collide | `analytics/train.py:89` | Registry ambiguity |
| 8 | Rate-limiter `_request_log` is an unbounded `defaultdict` keyed by client IP with no eviction of empty deques | `main.py:47` | Slow memory growth |
| 9 | `API` constant is referenced inside the middleware closure but defined **below** it | `main.py:64, 88` | Works by module-global timing; fragile |
| 10 | `RateLimiter.__enter__` holds `self._lock` across `time.sleep()` | `nba_api/rate_limiter.py:22–29` | Serializes starts regardless of `max_concurrency` |
| 11 | `Ridge(random_state=...)` has no effect for the default solver | `analytics/impact.py:161` | Cosmetic; implies reproducibility control that isn't there |
| 12 | Validation errors leak raw Pydantic internals (`{'type':…, 'loc':…, 'ctx':…}`) into the API response | `core/errors.py:validation_error_handler` | Poor client contract |
| 13 | Unknown query params are silently ignored; **`strategy: "win_now_lol"` is accepted (HTTP 200)** and silently falls back to `custom` weights | `api/v1/trades.py`, `evaluation.py:376` | Silent wrong answers |
| 14 | Invalid dynamic routes return **HTTP 200** | Next.js app router | SEO/monitoring noise |
| 15 | `games` (1,230 rows) ingested, never read | `ingestion/jobs.py` | Wasted sync budget |
| 16 | No scheduler. `worker.py` exists but every refresh is a manual `make` target | | Data goes stale silently — and W6 hides that it has |
| 17 | `ADMIN_TOKEN` defaults to empty; `POST /api/v1/admin/sync` is in the OpenAPI surface | `config`, `main.py` | Verify it is hard-disabled when unset |

### Test coverage — inverted relative to risk

Overall 64%. Broken out:

| Module | Coverage | Comment |
| --- | --- | --- |
| `analytics/train.py` | **0%** | The entire training pipeline |
| `analytics/score.py` | **0%** | Team-needs generation |
| `services/candidates.py` | **19%** | The trade recommender |
| `analytics/archetypes.py` | **28%** | Clustering + labeling |
| `analytics/impact.py` | **31%** | TEI training + scoring |
| `analytics/needs.py` | **35%** | `compute_team_needs` body |
| `analytics/uncertainty.py` | 100% | |
| `analytics/projection.py` | 97% | |
| `services/evaluation.py` | 94% | |
| `cba/*` | high | |

**The code that produces the numbers users see is the least tested. The code that is well tested cannot run for lack of data.** No test asserts that TEI has sensible basketball properties; no test asserts that an empty trade scores 50; no test asserts that gutting a roster scores badly.

---

## 11. QA Findings

All reproduced live against `localhost:8000` / `localhost:3000` on 2026-07-27.

---

**QA-1 — Trading an entire roster for nothing scores 72.85/100**
*Component:* `POST /api/v1/trades/evaluate` → `services/evaluation.py`
*Steps:* `team_ids=[BOS, LAL]`, one `player_move` per BOS roster player (16), all `BOS → LAL`, no incoming.
*Expected:* Score near 0; legality `verified_illegal` should gate the recommendation.
*Actual:* `composite_utility: 72.85`, `delta_wins: +0.83`, `assets: 82.0`, `confidence: medium`, `rotation_after: []`, `roster_after: 0`. Report verdict: "Proceed with further diligence."
*Severity:* **Critical**
*Cause:* Three: `allocate_rotation([])` → 0.0 = league average for vacated minutes (`projection.py:70`); `_assets` rewards `roster_spots_delta = −16` (`evaluation.py:339`); composite never consults legality.
*Fix:* Fill vacated minutes at `REPLACEMENT_TEI`; cap `_assets` roster-spot credit at ±2; hard-gate the composite on `verified_illegal`.

---

**QA-2 — A team can "acquire" a player it already rosters**
*Component:* `POST /api/v1/trades/evaluate` → `cba/builder.py:build_trade_context`
*Steps:* `{player_id: <Dončić>, from_team_id: BOS, to_team_id: LAL}` — Dončić is on LAL.
*Expected:* 422 — the player is not on `from_team`.
*Actual:* HTTP 200. BOS unchanged (46.36); **LAL scores 61.67 with +0.45 wins** for acquiring a player already on its roster, who is now double-counted in `after_cards`.
*Severity:* **Critical**
*Cause:* No validation that `player_id ∈ roster(from_team_id)`.
*Fix:* Validate roster membership in the Pydantic request model.

---

**QA-3 — Duplicate player moves are not deduplicated**
*Component:* `POST /api/v1/trades/evaluate`
*Steps:* Include the identical `{Tatum, BOS→LAL}` move twice.
*Expected:* 422.
*Actual:* HTTP 200. Tatum counted twice: BOS `aggregates_salaries` flips true, `roster_after` shifts by 2, BOS `fit` collapses to 9.2.
*Severity:* **High**
*Fix:* Reject duplicate `(player_id)` entries in `player_moves`.

---

**QA-4 — Data Health reports 6-day-old NBA data as "fresh"**
*Component:* `services/data_health.py:79,129`; `components/shell.tsx:55–60`; `app/page.tsx:190`
*Steps:* Load `/data-health`.
*Expected:* "stale" — the API itself reports `stale: true` for all 7 NBA.com tables.
*Actual:* **"Current NBA data ✓ fresh · updated Jul 27, 2026, 1:45 AM."** Nav shows 🟢 "Live data". The Jul 27 timestamp is the `index_assets` local-file job; the real sync was Jul 21 01:53.
*Severity:* **Critical** (destroys the product's core claim)
*Fix:* Derive `last_success` per source from `MAX(source_retrieved_at)` on the relevant tables, not from `MAX(finished_at)` across all jobs.

---

**QA-5 — A trade in which nothing happens scores 46.36 with `prob_positive = 0.0`**
*Component:* `analytics/uncertainty.py:simulate_delta_wins`
*Steps:* `player_moves: []`, `pick_moves: []`.
*Expected:* 50.0 neutral; `prob_positive` 0.5 or `null`.
*Actual:* `composite 46.36`, `risk 34.0`, `median = p10 = p90 = 0.0`, **`prob_positive: 0.0`**.
*Severity:* **High**
*Cause:* `(delta_wins > 0).mean()` on an all-zeros array is 0.0, feeding `risk = 60·0 + 40·0.85 = 34`.
*Fix:* Return `None` when both sides are empty; use `>= 0` or a tie-splitting convention.

---

**QA-6 — Rotation chart omits the acquired player and fabricates a change for an untraded one**
*Component:* `services/evaluation.py:242–243` → `app/trade-evaluator/page.tsx:2210`
*Steps:* CHI ↔ GSW, Giddey for Curry, Evaluate, Impact tab.
*Expected:* Curry appears with post-trade minutes.
*Actual:* *"Josh Giddey 20.4 → 0.0 (−20.4); **Jalen Smith 0.0 → 12.4 (+12.4)**"*. **Curry absent.** Jalen Smith was not in the trade.
*Severity:* **High**
*Cause:* `before.detail[:12]` / `after.detail[:12]` slice in roster order **before sorting**; incoming players are appended last and fall outside the window; removing one player shifts the index alignment.
*Fix:* Sort by minutes descending before slicing, and always include every player involved in the trade.

---

**QA-7 — An invalid strategy is silently accepted**
*Component:* `POST /api/v1/trades/evaluate`
*Steps:* `strategy: "win_now_lol"`.
*Expected:* 422.
*Actual:* HTTP 200; `DEFAULT_WEIGHTS.get(strategy, DEFAULT_WEIGHTS["custom"])` silently substitutes different weights and returns different numbers.
*Severity:* **Medium**
*Fix:* Make `strategy` a Pydantic `Literal`/enum.

---

**QA-8 — Executive report prints a defaulted availability as a measurement**
*Component:* `services/reports.py` §5 + `evaluation.py:355`
*Steps:* `GET /api/v1/trades/{id}/report` for the "E2E RosterLab deal" (BOS sends Tatum, receives nothing).
*Expected:* "no incoming players" or omission.
*Actual:* *"Historical availability of incoming players: **85%** of team games."* 0.85 is the `avail_in` fallback for an empty list.
*Severity:* **High** (contradicts the honesty standard in the highest-stakes artifact)
*Fix:* Suppress the line when `incoming` is empty.

---

**QA-9 — Same metric shown as both a Strength and a Need**
*Component:* `app/team-outlook/[teamId]/page.tsx:435`
*Steps:* Open Team Outlook for Atlanta.
*Expected:* Needs list only actual shortfalls.
*Actual:* **"Defensive rebounding 67th"** appears under **Strengths** and under **Needs**, with a zero-length bar beneath *"Longer bar under Needs = larger shortfall."* "Ball security 23rd" and "Overall defense 27th" are also listed as Needs despite `severity = 0`.
*Severity:* **High**
*Cause:* `(weaknesses.length ? weaknesses : sortedNeeds.slice(0, 4))` — a fallback that shows the first four rows regardless of severity. 2 of 30 teams currently hit this path; 135 of 279 `team_needs` rows have `severity = 0`.
*Fix:* Render an explicit "No pressing needs" state instead of the fallback.

---

**QA-10 — Candidate generator proposes two All-Stars for a bench player**
*Component:* `POST /api/v1/trades/generate`
*Steps:* `focal_team_id = BOS`, `strategy = contend`.
*Expected:* Roughly balanced, legality-checked candidates.
*Actual:* `CLE in: [Donovan Mitchell, James Harden] out: [Jordan Walsh]`, counterparty utility **52.0** (above the 42.0 acceptance floor). Also `evaluations_run: 400` = the full budget, so ~6 of 29 counterparties were searched, in unordered insertion order, silently.
*Severity:* **High**
*Fix:* Require salary-matched packages (needs contracts), tighten `tei_gap`, order counterparties deterministically, and disclose truncation.

---

**QA-11 — `EFF` season total displayed in the "Per game" view**
*Component:* `ingestion/stats_csv.py:90` → Player Explorer
*Steps:* Player Explorer, Scale = "Per game".
*Expected:* ~33.5 for Dončić, or the column hidden.
*Actual:* **2146.0**, under the caption *"Shooting rates and EFF are scale-independent."*
*Severity:* **Medium**
*Cause:* `EFF` is in `_RATE_FIELDS` alongside `FG_PCT`/`FG3_PCT`/`FT_PCT`.
*Fix:* Move `EFF` to `_TOTAL_FIELDS`, derive `EFF/g`, correct the caption.

---

**QA-12 — Verdict labels are inverted**
*Component:* `lib/format.ts:58–65`
*Actual:* score 46 → **"High-risk upside"**; score 52 → "Mixed outcome". The worse score gets the more optimistic label.
*Severity:* **Medium**
*Fix:* Monotone labels: "Clear win" / "Modest gain" / "Roughly neutral" / "Net negative" / "Clear loss".

---

**QA-13 — Validation error bodies leak Pydantic internals**
*Component:* `core/errors.py`
*Steps:* `pick_moves[].draft_year = 2034`.
*Actual:* `"[{'type': 'less_than_equal', 'loc': ('body','pick_moves',4,'draft_year'), 'ctx': {'le': 2033}}]"` inside `message`.
*Severity:* **Low**
*Fix:* Map to `{field, message}` pairs.

---

**Handled correctly (regression-protect these):** single-team trade → 422 · self-trade → 422 · unknown player id → 404 · team not in `team_ids` → 422 · `limit > 200` → 422 · `pick draft_year > 2033` → 422 · unknown season → clean `available: false` payload · missing player image → clean 404 JSON with a monogram fallback in the UI · bad team abbreviation → 404 · long/diacritic names (Dončić, Porziņģis, Antetokounmpo, Alexander-Walker) render without overflow at 1440 and 710 px · zero console errors on every route.

---

## 12. Recommended New Features

Depth over quantity. Four, in dependency order.

### N1 — Contract & Cap Engine (activation, not construction)

- **User problem:** "Is this deal legal, and what does it do to my books?" — currently unanswerable.
- **Target user:** Cap analyst, GM, basketball ops analyst.
- **Data:** BBRef contracts snapshot → `contracts` / `contract_years`. **The parser already exists** (`integrations/contracts/bbref_provider.py`, unit-tested in `test_bbref_provider.py`).
- **Calculation:** Already written — `cba/rules/salary.py`, `roster.py`, `restrictions.py`, `services/payroll.py`.
- **Output:** `verified_legal` / `verified_illegal` verdicts; payroll, tax, apron; the contract-value component enters the composite.
- **Complexity: Small** (data + config + freshness surfacing).
- **Product value: Highest in the report.** **Portfolio value: Highest** — it flips the demo from "cannot verify" to "verified illegal: incoming $48.2M exceeds the $31.4M maximum."
- **Dependencies:** none. **Risks:** snapshot staleness → show `source_date` prominently and warn past 14 days.

### N2 — Calibrated Impact & Wins Translation

- **User problem:** "What is a TEI point worth?" Nobody can answer it today, including the code.
- **Target user:** Everyone; every downstream number depends on it.
- **Data:** Already ingested — `team_season_stats.NET_RATING` (180 rows), `standings` (90), `rosters`, `player_impact_estimates`.
- **Calculation:** Regress **observed team net rating** on **minutes-weighted roster TEI** across the 90 ingested team-seasons. That fitted slope + intercept *is* the TEI→net-rating conversion (and it will surface the missing ~5× factor empirically rather than by assertion). Report out-of-sample RMSE. Persist as a `model_versions` row so it is inspectable like every other model.
- **Output:** Win deltas in defensible units; per-player intervals that widen with fewer minutes.
- **Complexity: Medium.** **Value: Critical** — without it every headline number is meaningless.
- **Risk:** the fit may reveal TEI explains less team net rating than hoped. **That is the point** — publish the R² and let the honesty layer do its job.

### N3 — Comparable Trade Retrieval

- **User problem:** "Has anything like this actually happened, and how did it work out?"
- **Target user:** GM, strategy exec — this is how front offices genuinely argue.
- **Data:** `transactions` (table exists, empty) from the already-downloaded Kaggle DB and/or NBA.com.
- **Calculation:** Similarity retrieval over (impact differential, age differential, salary differential, pick count, team records) → nearest historical deals → outcome the following two seasons.
- **Output:** *"Five most similar completed trades since 2015; the acquiring team improved by a median of +3.1 wins."*
- **Complexity: Medium.** **Product value: High. Portfolio value: Very high** — no public trade machine does this, and it is grounded in fact rather than model output.
- **Risk:** similarity metric selection; small n for exotic structures. Show the comps themselves, always.

### N4 — Real Pick Valuation

- **User problem:** every pick is currently worth 8 points.
- **Data:** `draft_picks` (exists, empty) + historical draft-slot → career-value curve.
- **Calculation:** Slot → expected surplus value curve; protections modeled as a probability distribution over landing slots given the origin team's projected record.
- **Output:** Picks priced in the same surplus-value currency as players.
- **Complexity: Medium** (curve) + **Large** (maintaining ownership data). **Value: High.**

### Deliberately **not** recommended now

Multi-team beyond 3 (already supported to 3; deeper adds combinatorics without insight) · Monte Carlo full-season simulation (garbage-in until N2) · lineup optimization (needs lineup data) · draft-prospect fit (no prospect data) · injury-risk modeling (no injury data; ethically fraught) · LLM narrative generation (`ANTHROPIC_API_KEY` hook already exists — prose polish, not decision support).

---

## 13. Features to Remove or Consolidate

| Action | Target | Reason |
| --- | --- | --- |
| **Remove** | `POST /api/v1/trades/generate` + "Suggest deals" (`services/candidates.py`, 19% covered) | Recommends two All-Stars for a bench player, targets turnovers by acquiring high-assist guards, cannot check legality, silently searches ~20% of the league. **Highest ratio of demo risk to user value in the product.** Rebuild after N1 + N2 as a constrained, salary-matched, deterministic search. |
| **Remove** | `player_archetype` k-means (silhouette 0.156) | Ships "primary creator (3)" to users. Replace with rule-based roles. |
| **Remove** | The ridge model; promote `baseline_index` to production | 1.2% better than the transparent index, uninterpretable, negative coefficients on the target's own components. |
| **Remove** | Constant `tei_low`/`tei_high` bands and the `# bootstrap` comments | Identical ±3.156 for all 512 players conveys nothing and the code comment is false. Reinstate with real per-player intervals from N2. |
| **Remove** | The three test trade proposals, 5 scenarios, and 50 comparison sets in the shipped DB | "Smoke test deal" is the first thing a visitor sees in Strategy Lab. |
| **Consolidate** | `risk` into `performance` | `risk = 60·prob_positive + 40·avail_in`, and `prob_positive` is a restatement of the performance simulation. Six components → **four**: On-court impact (with interval), Roster fit, Contract & flexibility, Timeline. |
| **Consolidate** | Player Explorer ↔ player detail ↔ roster cards into one player surface | Three views of a player with disjoint metrics; the Explorer lacks TEI, the roster cards lack the box score. |
| **Consolidate** | Salary-Cap Center into Team Outlook | 741 LOC of import wizard for one team's payroll. It is a tab on Team Outlook, not a module. |
| **Rename** | "Decision score" → **"Strategic alignment score"** | It measures alignment with the chosen strategy, not deal quality. |
| **Delete** | `zod`, `react-hook-form`, `@hookform/resolvers`; audit `recharts` | Zero imports found in `app/`, `components/`, `lib/`. |
| **Delete or use** | `games` ingestion (1,230 rows, no consumer) | Either drive schedule strength / rest from it or stop syncing it. |

---

## 14. Prioritized Roadmap

### P0 — Credibility and Correctness

*Every item here must ship before any new feature.*

---

**P0-1 · Fix the data-freshness attribution**
- **Recommendation:** Compute freshness per source from `MAX(source_retrieved_at)` on the tables each card describes, not from `MAX(DataSyncRun.finished_at)` across all jobs. Apply to the source card, the nav pill, and the homepage stat.
- **Reason:** The provenance page currently calls 6-day-old NBA data "fresh" because a local image-indexing job ran.
- **User impact:** Restores the single claim the product is built on.
- **Files:** `backend/app/services/data_health.py:79,129` · `frontend/components/shell.tsx:55–60` · `frontend/app/page.tsx:190,432`
- **Data deps:** none · **Approach:** per-source `last_retrieved` already computed in the `tables` loop — reuse it.
- **Complexity: Small · Risk: Low**
- **Accept:** With the current DB, `/data-health` shows "Current NBA data — **stale**", the nav pill shows "Data aging", and the homepage shows Jul 21. A regression test asserts an `index_assets` run does not change NBA freshness.
- **Before next feature: YES**

---

**P0-2 · Import contracts and turn the CBA engine on**
- **Recommendation:** Save the BBRef contracts snapshot to `data/imports/contracts/players.html`, create `.env` with `CONTRACT_DATA_PROVIDER=bbref_snapshot`, run `make sync-data`. Surface `source_date` on every cap surface with a >14-day staleness warning.
- **Reason:** 8 of 9 CBA rules, payroll, apron status, and the contract component are dead. This is the differentiator.
- **User impact:** Trades move from "Incomplete check" to real verdicts; four modules activate.
- **Files:** `data/imports/contracts/` · `.env` · `backend/app/integrations/contracts/bbref_provider.py` (exists) · `frontend/app/salary-cap-center/page.tsx`
- **Data deps:** the snapshot · **Approach:** parser and rules already written and tested.
- **Complexity: Small · Risk: Low** (staleness, mitigated by the badge)
- **Accept:** `contracts > 0`; a knowingly-illegal deal returns `verified_illegal` with the exact dollar figures; Salary-Cap Center renders a payroll.
- **Before next feature: YES** — this is the highest-value action available.

---

**P0-3 · Calibrate TEI → net rating (and fix the missing ×5)**
- **Recommendation:** Fit `team_net_rating ~ a + b·(minutes-weighted roster TEI)` on the 90 ingested team-seasons. Persist as a `model_versions` row with out-of-sample RMSE. Replace the asserted identity in `team_tei_to_net_rating_delta`. If the fit is weak, **publish the R²** and widen intervals accordingly.
- **Reason:** Every headline number — win deltas, net-rating deltas, the performance component, the Monte Carlo, the report — is currently produced by an unvalidated unit assertion plus a factor-of-5 error.
- **User impact:** "+3.4 wins" becomes a defensible sentence.
- **Files:** `backend/app/analytics/projection.py:92–95,70–79` · `backend/app/analytics/train.py:210–234` · `backend/app/services/evaluation.py:238`
- **Data deps:** `team_season_stats`, `standings`, `rosters`, `player_impact_estimates` — all present.
- **Complexity: Medium · Risk: Medium** (may reveal weak explanatory power — publish it)
- **Accept:** A star-for-star upgrade produces a magnitude a basketball person recognizes; the conversion appears in `model_versions` with a holdout metric; `docs/methodology.md` shows the fit.
- **Before next feature: YES**

---

**P0-4 · Gate the composite on legality and floor vacated minutes at replacement level**
- **Recommendation:** (a) When `overall_status == "verified_illegal"`, suppress the decision score entirely and show the failing rule. (b) In `allocate_rotation`, fill unallocated minutes at `REPLACEMENT_TEI`, derived empirically rather than hardcoded to −2.0. (c) Cap `_assets` roster-spot credit at ±2 points.
- **Reason:** QA-1 — trading a whole roster away scores 72.85/100.
- **Files:** `backend/app/analytics/projection.py:70–89` · `backend/app/services/evaluation.py:339,449`
- **Complexity: Small · Risk: Low**
- **Accept:** Gutting a roster scores < 20 and shows no "Proceed" verdict. Regression test added.
- **Before next feature: YES**

---

**P0-5 · Validate trade construction**
- **Recommendation:** Reject (i) players not on `from_team_id`'s current roster, (ii) duplicate `player_id` entries, (iii) unknown `strategy` values (Pydantic `Literal`).
- **Reason:** QA-2, QA-3, QA-7 — all currently return HTTP 200 with wrong answers.
- **Files:** `backend/app/api/schemas.py` · `backend/app/api/v1/trades.py`
- **Complexity: Small · Risk: Low**
- **Accept:** Each of the three cases returns 422 with a clear message; three regression tests.
- **Before next feature: YES**

---

**P0-6 · Stop silently defaulting unknown players to league average**
- **Recommendation:** In `_card`, keep `tei` as `None` when there is no estimate. Propagate `has_unmodeled_players` into the evaluation response; render "N players not modeled — impact excluded" and downgrade confidence.
- **Reason:** 43 rostered players get `tei = 0.0` (above the −0.293 mean), `availability = 0.75`, `minutes = 12.0`. The roster API honestly says `null`; the evaluator silently overwrites it. This is the sharpest violation of the stated four-state standard.
- **Files:** `backend/app/services/evaluation.py:177–195` · `frontend/app/trade-evaluator/page.tsx`
- **Complexity: Small · Risk: Low**
- **Accept:** A trade involving an unmodeled player shows an explicit unavailable state, never a neutral score.
- **Before next feature: YES**

---

**P0-7 · Replace the defensive proxy and fix `NEED_TO_SKILL`**
- **Recommendation:** Ingest `LeagueDashPtDefend` and `TeamPlayerOnOffDetails`; build `perimeter_defense` from opponent FG% at the rim/perimeter plus defensive on/off, with steals as at most a minor term. Remap `ball_security → turnover_avoidance` (a new skill from `TM_TOV_PCT`), not `creation`. Split `shooting` into `shooting_volume` (3PA rate) and `shooting_accuracy` (`FG3_PCT`, currently ingested but unused).
- **Reason:** Acquiring Luka Dončić is scored as a point-of-attack defense upgrade; teams with turnover problems are told to acquire high-assist guards; high-volume poor shooters score as good shooters.
- **Files:** `backend/app/analytics/archetypes.py:139–145` · `backend/app/analytics/needs.py:159–170` · `backend/app/integrations/nba_api/endpoints/__init__.py`
- **Data deps:** two `nba_api` endpoints already reachable through the hardened client.
- **Complexity: Medium · Risk: Medium** (on/off is noisy — shrink toward the box-score prior)
- **Accept:** Dyson Daniels and Draymond Green rank in the top defensive quartile; a Dončić acquisition does not improve POA defense; a turnover need never recommends a high-turnover creator.
- **Before next feature: YES**

---

**P0-8 · Retire the ridge model and the k-means archetypes**
- **Recommendation:** Promote `baseline_index` to production (it is already implemented, documented, and within 1.2% of the ridge on the validation transition). Replace k-means with rule-based role assignment on interpretable thresholds. Remove the constant `tei_low`/`tei_high` bands and the false `# bootstrap` comments until P0-3 supplies real intervals.
- **Reason:** Negative coefficients on the target's own components; degenerate labels shipped to users; a uniform ±2.67 SD "interval" for every player.
- **Files:** `backend/app/analytics/impact.py:181–193,219–224` · `backend/app/analytics/archetypes.py:26–65` · `backend/app/db/models.py:375–376`
- **Complexity: Medium · Risk: Low** (strictly reduces complexity)
- **Accept:** No user-facing label contains a numeric suffix; the methodology page shows interpretable, signed weights; no two players share an identical interval width.
- **Before next feature: YES**

---

**P0-9 · Fix the rotation chart truncation**
- **Recommendation:** Sort `RotationResult.detail` by minutes descending before slicing, and always include every player involved in the trade regardless of rank.
- **Reason:** QA-6 — the chart omits the acquired player and fabricates a +12.4-minute change for one who was not traded.
- **Files:** `backend/app/services/evaluation.py:242–243` · `backend/app/analytics/projection.py:80–89`
- **Complexity: Small · Risk: Low**
- **Accept:** Every incoming and outgoing player appears in the before/after chart with correct values.
- **Before next feature: YES**

---

**P0-10 · Purge test data and fix the Strengths/Needs fallback**
- **Recommendation:** Remove the 3 test trade proposals, 5 scenarios, and 50 comparison sets from the shipped DB; add a seed command that creates realistic named examples. Replace `(weaknesses.length ? weaknesses : sortedNeeds.slice(0, 4))` with an explicit "No pressing needs" state.
- **Reason:** "Smoke test deal" is the first content in Strategy Lab; ATL shows "Defensive rebounding" as both a Strength and a Need.
- **Files:** `frontend/app/team-outlook/[teamId]/page.tsx:435` · `backend/app/cli.py`
- **Complexity: Small · Risk: Low**
- **Accept:** No entity name contains "test", "smoke", or "E2E"; no metric appears in both columns.
- **Before next feature: YES**

---

### P1 — Core Product Value

**P1-1 · Collapse six components to four; remove the double-count**
Fold `risk` into `performance` (as the interval on the win delta) and `assets` into `contract` (as flexibility). Replace saturating linear scalings (`×120`, `×5`, `×250`, `×8`) with percentile ranks against a distribution of plausible trades, so no component clips at 100.
*Files:* `services/evaluation.py:237–361`, `analytics/sensitivity.py` · **Medium / Medium** · *Accept:* no component clips on a routine star-for-star swap; components are demonstrably not collinear.

**P1-2 · Empirical pick valuation**
Slot → expected-surplus curve; protections as a distribution over landing slots. Replaces `8.0 × count`.
*Files:* `services/evaluation.py:332–350`, new `analytics/picks.py`, `draft_picks` · **Medium / Medium** · *Accept:* an unprotected top-5 first is worth ≥10× a late second.

**P1-3 · Player-specific uncertainty**
Intervals that widen with fewer minutes, fewer seasons, and greater age. Empirical-Bayes shrinkage toward positional means.
*Files:* `analytics/impact.py:196–225` · **Medium / Low** · *Accept:* a 5-mpg rookie's interval is ≥2× a 36-mpg star's.

**P1-4 · Unify the player surface**
One canonical player view: box score + TEI + archetype + contract + availability + percentiles. Wire Team Outlook, Trade Evaluator, and Explorer to it.
*Files:* `app/players/[playerId]/page.tsx`, `app/player-explorer/page.tsx`, `components/ui.tsx` · **Medium / Low**

**P1-5 · N+1 and cold-cache elimination**
Batch-load salaries and roster stats; precompute the skills frame in `make score` and store it, rather than rebuilding 1,714 rows of pandas inside a request.
*Files:* `cba/builder.py:39–72`, `analytics/score.py:47–60`, `services/evaluation.py:146–161` · **Medium / Low** · *Accept:* `/trades/generate` issues <500 queries; cold-cache evaluate <200 ms.

**P1-6 · Test the modeling path**
Bring `train.py`, `score.py`, `impact.py`, `needs.py`, `candidates.py` from 0–35% to >70%, with *property* tests: TEI monotone in scoring efficiency at fixed volume; empty trade = 50; roster-gut < 20; unmodeled player never scores neutral.
*Files:* `backend/tests/unit/` · **Medium / Low**

**P1-7 · Automated ingestion**
Wire `worker.py` to a scheduler (APScheduler locally, cron in compose) for daily NBA.com sync + weekly retrain, with failures surfaced on Data Health.
*Files:* `app/worker.py`, `docker-compose.yml` · **Medium / Medium**

---

### P2 — Differentiation

**P2-1 · Comparable trade retrieval** (N3) — populate `transactions`, similarity index, outcome lookback. *Large / Medium.* **The strongest differentiator available.**

**P2-2 · Lineup-aware fit** — `LeagueDashLineups` + on/off; replace static skill-vector deltas with marginal value given the existing top-8. *Large / Medium.*

**P2-3 · Multi-year surplus value** — 3-season projections with age curves and contract cost in cap %, once contracts and history exist. *Large / Medium.*

**P2-4 · Need-driven entry point** — *"Boston needs perimeter defense — here are the 20 available players who provide it, ranked by surplus value and salary-matchability."* This is how the target user actually thinks, and it is a small step from the existing needs + skills machinery. *Medium / Low.*

**P2-5 · Decision memo export** — PDF/shareable version of the existing Markdown report, with comps and the sensitivity chart. `reports.py` is already 94% covered. *Small / Low.*

---

### P3 — Polish and Expansion

**P3-1** Verdict-label rewrite (monotone) — `lib/format.ts:58–65` — *Small.*
**P3-2** `EFF` scale fix + caption correction — `stats_csv.py:90` — *Small.*
**P3-3** Kill `-0.0`; hide the dead salary column until contracts load; fix the "4 checks / 2 named" copy — *Small.*
**P3-4** Persist team selection across modules — *Small.*
**P3-5** Extract `ImpactTab`/`FitTab`/`ComponentBars`/`BeforeAfterBars` from the 2,679-LOC page into `components/` — *Medium.*
**P3-6** Drop `zod` / `react-hook-form` / `@hookform/resolvers`; audit `recharts` — *Small.*
**P3-7** Structured validation errors; `notFound()` on invalid dynamic routes — *Small.*
**P3-8** Playoff-split stats for `contend` strategies — *Medium.*
**P3-9** Minimum-GP flag in Player Explorer (Tatum at 16 GP) — *Small.*
**P3-10** Fix duplicate `model_versions` rows; use a content hash, not a minute-resolution timestamp — *Small.*

---

## 15. Proposed Future-State Architecture

Keep the layering. The changes are in the modeling substrate and the scheduling layer.

```
┌──────────────────────── INGESTION (scheduled, not manual) ────────────────────┐
│  nba_api client (unchanged — this is the strongest code in the repo)          │
│    daily : teams · players · rosters · standings · team/player season stats   │
│    weekly: on/off · lineups · play types · shot locations · defensive tracking│
│  contracts   : BBRef snapshot parser  (built; needs the file + a freshness UI)│
│  picks       : curated draft_picks with protections (manual, is_verified)     │
│  transactions: historical deals for comparable retrieval                      │
│  quality     : per-source freshness → data_health (per-table, never per-job)  │
└───────────────────────────────────────────────────────────────────────────────┘
                                     ↓
┌──────────────────────── FEATURE STORE (materialized, not per-request) ────────┐
│  player_season_features · player_skill_vectors · team_context                 │
│  built by `make score`, cached with a data-version key, never in a request    │
└───────────────────────────────────────────────────────────────────────────────┘
                                     ↓
┌──────────────────────── MODELING (fewer models, calibrated) ──────────────────┐
│  Impact      : transparent weighted index + on/off shrinkage                  │
│                → CALIBRATED to net rating on 90 team-seasons (P0-3)           │
│                → per-player intervals from minutes/sample size                │
│  Roles       : rule-based thresholds (k-means retired)                        │
│  Wins        : net rating → wins, k-fold validated                            │
│  Pick value  : empirical slot → surplus curve                                 │
│  Contract    : log(cap %) regression, once multi-year salary history exists   │
│  Comparables : similarity retrieval over transactions                         │
└───────────────────────────────────────────────────────────────────────────────┘
                                     ↓
┌──────────────────────── DECISION ENGINE ──────────────────────────────────────┐
│  CBA rules engine (unchanged design — finally with data)                      │
│    └── HARD GATE: verified_illegal ⇒ no score is produced                     │
│  Four components (was six):                                                   │
│    On-court impact (with interval)  ·  Roster fit (lineup-aware)              │
│    Contract & flexibility           ·  Timeline                               │
│  Sensitivity: Dirichlet rank stability + tornado (keep — already good)        │
│  Evidence:    comparable historical trades attached to every verdict          │
└───────────────────────────────────────────────────────────────────────────────┘
                                     ↓
┌──────────────────────── PRODUCT SURFACES (consolidated) ──────────────────────┐
│  Trade Evaluator  (flagship, unchanged shape)                                 │
│  Team Workspace   (Team Outlook + Salary-Cap Center + needs-driven targets)   │
│  Player Surface   (Explorer + detail + roster card — one canonical view)      │
│  Strategy Lab     (real saved scenarios; test fixtures purged)                │
│  Data Health      (per-source freshness, correctly attributed)                │
└───────────────────────────────────────────────────────────────────────────────┘
```

**Key architectural changes:** (1) scheduled ingestion replaces manual `make` targets; (2) a materialized feature store replaces per-request pandas; (3) fewer models, all calibrated, all with real intervals; (4) legality becomes a hard gate on the composite rather than a sibling display; (5) six product surfaces collapse to five with the player view unified. Everything else — the provider client, the rules registry, the provenance mixin, the four-state standard, the error contract — stays exactly as it is.

---

## 16. Final Product Vision

RosterLab should be **the trade tool that shows its work and refuses to bluff.**

A basketball ops analyst opens it, picks their team, and sees a workspace that already knows what the roster needs, what the books look like, and which picks are actually theirs. They build a deal. Before any score appears, the rules engine returns a real verdict with dollar figures — *"Incoming $48.2M exceeds the $31.4M maximum under the standard TPE; Boston is above the first apron after this trade."* When the deal is legal, four components appear, each with an interval, each traceable to a source, each with the option to see the exact calculation. Alongside the projection sit the five most similar completed trades since 2015 and what happened to those teams. Where data is missing, the component is absent and says why — never estimated, never quietly defaulted.

The analyst exports a one-page memo their GM can read in ninety seconds: recommendation, legality, projected impact with honest error bars, cap consequences, the historical comps, and the three questions the model cannot answer.

**Nothing in that vision requires a new model class.** It requires one dataset import, one calibration regression, one defensive metric replacement, three deletions, and a set of small correctness fixes. The engineering to support all of it already exists in this repository — that is the genuinely unusual thing about RosterLab, and the reason this audit is so blunt about the gap. The foundation is better than the product standing on it.

---

## Final Ranking

### 1. The ten highest-value improvements

| # | Improvement | Why |
| --- | --- | --- |
| 1 | **Import contracts; activate the CBA engine** (P0-2) | Turns 8 dead rules and 4 dead modules on. Smallest effort, largest effect in the entire report. |
| 2 | **Calibrate TEI → net rating; fix the ×5** (P0-3) | Every headline number currently rests on a docstring assertion plus a factor-of-5 error. |
| 3 | **Fix data-freshness attribution** (P0-1) | The honesty page is currently dishonest. |
| 4 | **Replace steals-as-defense; fix `NEED_TO_SKILL`** (P0-7) | "Acquiring Dončić improves your point-of-attack defense" ends demos. |
| 5 | **Gate on legality; floor vacated minutes** (P0-4) | Gutting a roster scores 72.85/100. |
| 6 | **Validate trade construction** (P0-5) | Duplicate players and phantom acquisitions return HTTP 200 today. |
| 7 | **Stop defaulting unknown players to league average** (P0-6) | 43 rostered players silently score as average NBA rotation players. |
| 8 | **Retire the ridge model and k-means archetypes** (P0-8) | 1.2% gain over a transparent index; "primary creator (3)" shipped to users. |
| 9 | **Collapse six components to four** (P1-1) | Removes double-counting and score saturation. |
| 10 | **Comparable trade retrieval** (P2-1) | The strongest available differentiator, grounded in fact rather than model output. |

### 2. The five most serious credibility risks

1. **Data Health calls 6-day-old NBA data "fresh"** because a local image-indexing job ran (`data_health.py:79,129`). The honesty layer is the product; this breaks it.
2. **The flagship win projection is dimensionally meaningless.** Tatum ↔ Dončić = +0.43 wins; Giddey → Curry = +0.00 net rating. `projection.py:92–95`.
3. **"Acquiring Luka Dončić improves Boston's point-of-attack defense"** — the largest positive contributor to the fit score, because `perimeter_defense = steals/min` (`archetypes.py:141`).
4. **Trading an entire roster away scores 72.85/100** and generates a "Proceed with further diligence" memo (QA-1).
5. **The executive report prints defaults as measurements** — "Historical availability of incoming players: 85%" with no incoming players (QA-8) — inside the document meant for a decision-maker.

### 3. The three strongest potential differentiators

1. **The four-state legality standard, once it can actually run.** No public tool refuses to say "legal" on partial data. `cba/context.py:overall_status` is already correct.
2. **Comparable trade retrieval.** *"Here are the five most similar completed deals and what happened."* No trade machine does this; it is the argument form front offices actually use.
3. **Full provenance and unavailability semantics as a product feature.** `ProvenanceMixin`, per-metric source lines, explicit unavailable states, weight renormalization. This is already built and is genuinely rare.

### 4. The single best next feature to build

**Import the contracts snapshot and activate the CBA engine (P0-2).** It is not a new feature — the parser, the rules, the payroll service, the UI, and the tests all already exist. One HTML file and one environment variable convert RosterLab from "cannot verify salary matching" to a tool that returns verified legal/illegal verdicts with exact dollar figures, unlocking salary matching, apron status, payroll, the Salary-Cap Center, and the contract-value component simultaneously. Nothing else in this report has a comparable value-to-effort ratio.

### 5. The single most important existing feature to improve

**Player impact (TEI) — specifically its calibration to net rating (P0-3).** It feeds the performance component, the wins projection, the Monte Carlo, the risk component, the contract heuristic, the age curve, the candidate generator, the rotation model, and every roster card. It is currently an arbitrary z-index asserted to be a per-100 measurement, with a uniform ±2.67 SD "interval" for all 512 players. Fixing the calibration fixes the credibility of nine downstream surfaces at once.

### 6. The single feature that should be removed or consolidated

**Remove the candidate generator (`POST /api/v1/trades/generate` / "Suggest deals", `services/candidates.py`).** It recommended Donovan Mitchell **and** James Harden for Jordan Walsh and marked it mutually acceptable; it targets turnover problems by acquiring high-assist guards; it cannot check salary legality; it silently searches ~20% of the league after exhausting a 400-evaluation budget in unordered team sequence; and it carries 19% test coverage. It is the highest demo-risk, lowest-value surface in the product. Rebuild it after P0-2 and P0-3 as a constrained, salary-matched, deterministic search.

### 7. Recommended implementation sequence

**Phase 0 — Make it true (1–2 weeks)**
`P0-1` freshness → `P0-2` contracts → `P0-5` validation → `P0-10` purge test data + Strengths/Needs fallback → `P0-9` rotation chart.
*Gate: every number displayed is either correct or explicitly unavailable.*

**Phase 1 — Make it defensible (2–4 weeks)**
`P0-3` TEI calibration → `P0-4` legality gate + replacement floor → `P0-6` no silent defaults → `P0-7` real defensive input + `NEED_TO_SKILL` fix → `P0-8` retire ridge + k-means.
*Gate: a Tatum ↔ Dončić swap produces a magnitude a basketball person recognizes, and no role label contains a numeric suffix.*

**Phase 2 — Make it useful (3–5 weeks)**
`P1-1` four components → `P1-2` pick valuation → `P1-3` per-player intervals → `P1-6` test the modeling path → `P1-5` N+1 and cold-cache → `P1-7` scheduled ingestion.
*Gate: >70% coverage on the modeling path; property tests pin the behaviors that failed QA.*

**Phase 3 — Make it different (4–8 weeks)**
`P2-1` comparable trades → `P2-4` need-driven entry → `P2-2` lineup-aware fit → `P2-5` decision memo export.
*Gate: every verdict ships with historical evidence attached.*

**Phase 4 — Polish (ongoing)**
All P3 items. `P1-4` unified player surface. Consolidate Salary-Cap Center into Team Outlook.

**Do not start Phase 2 before Phase 1 is complete.** Every P1 and P2 item inherits its numbers from TEI calibration and the defensive metric. Building on the current substrate compounds the error rather than fixing it.

---

*Audit performed 2026-07-27 against commit `f16dedc`. All quantitative claims were reproduced live against the running application and the shipped `backend/tradelab.db`. All file and line references are to the audited commit.*
