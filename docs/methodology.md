# Methodology

Everything below is computed from real NBA.com data ingested via `nba_api`; validation
numbers are from the actual trained models on this repository's July 2026 snapshot
(also visible at `/data-health`).

## 1. Composite utility — not a magic score

For focal team *t* and trade *d*:

```
U(t,d) = w_P·P + w_F·F + w_C·C + w_T·T + w_A·A + w_R·R        Σ w_k = 1
```

- Components are normalized to **0–100 with 50 = neutral** so the composite is
  readable at a glance; every component publishes its raw calculation alongside.
- Weights are user-controlled per scenario (strategy presets provided) and always
  renormalized.
- **Missing data shrinks scope, never fakes a number**: an unavailable component
  (e.g. contract value with no contract provider) is excluded and remaining weights
  renormalized; the exclusion is surfaced in the API (`excluded_components`) and UI.
  Driver contributions use the **renormalized** weights, so they sum to `U − 50`.
- **`U` can be absent, and absence has two meanings.** The response carries
  `decision_status`:
  - `scored` — `composite_utility` is a number;
  - `suppressed_illegal` — the deal fails a verified CBA rule, so it cannot be
    executed. No score is reported and `suppression.failing_rules` says why. A number
    here would invite comparing a deal that cannot happen against deals that can.
  - `insufficient_data` — no component could be scored. `null`, never 0.0: on a 0–100
    scale a zero reads as a catastrophic verdict rather than a refusal.
- **Verdict labels are monotone in the score**: ≥58 Clear win · 48–58 Roughly neutral ·
  40–48 Net negative · <40 Clear loss · low confidence ⇒ "Cannot fully evaluate". The
  thresholds are unchanged from the original design; the labels were not monotone before
  R1-9 (46 read "High-risk upside" while 52 read "Mixed outcome").
- **Zeroing every weight yields no score.** A weight vector summing to zero is a
  deliberate statement; substituting a uniform prior silently re-enabled components the
  user had switched off.

### Players the model has not scored

43 of 530 rostered players (8.1 %) have no impact estimate — mostly two-way and
late-signing players below the 200-minute window threshold the feature pipeline already
applies. They are **excluded from the projection and named**, never averaged in:
`has_unmodeled_players` and `unmodeled_players` appear on every evaluation, confidence
drops to low when one is inside the deal, and they remain in the roster count so roster
limits are unaffected.

Before R1-4 they carried `tei = 0.0`. That is the **63rd percentile** of rostered
players (306 of 487 sit below zero), so a player with no data was scored above the
median — a silent default considerably more favourable than the −0.293 league mean
suggests, and one that contradicted this document's own model card.

## 2. TEI — TradeLab Estimated Impact

TEI is this project's original per-100-possession impact estimate. It is **not**
RAPTOR, EPM, LEBRON, BPM, or any proprietary metric, and it is documented as a
portfolio-model estimate ([model card](model-card-player-impact.md)).

### Features

Per player-season from `LeagueDashPlayerStats` (Base + Advanced) and
`PlayerEstimatedMetrics` where available: pts/75 (via individual possessions), TS%,
USG%, AST%, TOV%, OREB%/DREB%, steals & blocks per minute, 3PA and FTA rates,
minutes, GP, age, PIE, on-court NET_RATING. Multi-season aggregation uses minutes ×
recency weights:

```
X̄ᵢ = Σₛ λ^(s−1)·mᵢ,ₛ·Xᵢ,ₛ / Σₛ λ^(s−1)·mᵢ,ₛ        λ = 0.7, s=1 most recent
```

Players under 200 window minutes are excluded (insufficient evidence), not imputed.
Cross-season comparability comes from minutes-weighted z-scores within each season.

### Candidates and validation

| Candidate | Description |
| --- | --- |
| Persistence baseline | this season's target repeats next season |
| **Transparent index (production)** | documented weighted z-score blend (weights in `impact.py::INDEX_WEIGHTS`) |
| ~~Ridge~~ | α=10 on next-season `0.6·z(PIE) + 0.4·z(NET_RATING)` — **retired in R3-1** |

Validation is **time-aware**: validate on the 2024-25→2025-26 transition (n=464).
Individual rows are never randomly split across seasons (leakage).

| Model | Held-out player MAE | Team-level R² (net rating) | Change-on-change R² |
| --- | --- | --- | --- |
| Transparent index | 0.645 | **0.7505** | **0.6236** |
| Persistence | 0.717 | — | — |
| ~~Ridge~~ (retired) | 0.637 | **0.0039** | 0.0030 |

The ridge won the player-level comparison and lost the one that matters. Held-out MAE
scores a *next-season player proxy*; the product uses TEI to project *team* impact, and
measured there the ridge explained essentially nothing. It is also a volume metric
(corr 0.716 with usage, 0.100 with net rating) and is not computable per season from
stored artifacts, so the R3-2 conversion could only ever have been fitted on n = 30 of
a metric carrying no signal.

### Serving scale (C5)

Served rows are z-scored against the **reference season's** minutes-weighted moments,
not against the recency-weighted window's own distribution. Before this fix the two
constructions correlated only **r = 0.387** at team level, and the two rescalings that
implied disagreed by 2.6× — which is the proof that no single transfer factor existed
and that train and serve had to share one reference instead. After it, team-level
served TEI regresses on season TEI with slope **1.015** (r = 0.911).

### Uncertainty bands (R3-4)

Per player, from that player's own playing time:

    σ² = 0.0326 + 240.9 / total_minutes

estimated from **921** same-player consecutive-season pairs. σ runs 0.72 at 500 minutes
to 0.36 at 2,500, replacing a single **2.462** inherited from the retired ridge's
residual spread — a band that was identical for a 2,800-minute starter and a 300-minute
rookie. Most bands are now narrower, which reads as overconfidence and is the opposite;
the thinnest-evidence players' bands are now **wider**. σ here is season-to-season
variability, which is the right input for a forward-looking interval and the wrong thing
to call "measurement error".

Scores are scaled ×2.5 to index points (elite ≈ +5).

### Index → net rating (R3-2)

A team's minutes-weighted index does **not** arrive in net-rating points. The conversion
is fitted change-on-change over 60 team transitions:

    Δnet = 14.977 · Δ(team TEI)      R² 0.624 · SE 1.528 · t 9.80 · n 60
    per-fold slopes 14.716 / 15.276  (within ±2% of pooled)
    leave-one-transition-out RMSE 2.944 / 3.773 vs 5.201 / 5.805 predicting zero

Change-on-change rather than levels because a team's *level* carries everything the
roster does not — coaching, health, schedule — and differencing removes the team fixed
effect. **Falsification note:** if TEI were already in additive per-player net-rating
units this fit would return ≈ 5. It returns ≈ 15, which is the quantitative statement of
how far the raw index scale is from net-rating points. The coefficient is valid only for
the regressor construction recorded alongside it in `model_versions`.

### Team minutes and replacement level (R3-3)

Team impact is normalised by the **240 minutes a team must field**, not by the minutes a
roster happens to fill; minutes it cannot fill are charged to a replacement-level player.
Replacement level is derived, not assumed: the old hardcoded −2.0 sat at the **14.1st
percentile** of player-season TEI. The rule is the mean TEI of player-seasons outside
their team's top 10 by minutes — **−1.214**.

## 3. Archetypes

K-means (k=8, fixed seed) over standardized role features (usage, assist rate, 3PA
rate, TS%, rebounding, stocks per minute, pts/75, height). Silhouette on the current
snapshot: **0.156** — modest and honestly reported; NBA roles overlap heavily, so
archetypes are used as descriptive labels and comparable-player groupings, not hard
class boundaries. Labels are assigned deterministically from cluster centers vs
league medians (rules in `archetypes.py::_label_from_center`).

## 4. Team needs

Transparent percentile rules over real team statistics — no LLM anywhere in the
calculation. Example: bottom-half FG3A → `three_point_volume` need with severity
`(50−pct)/50`. Proxies are labeled as proxies (blocks ≈ rim protection, steals ≈
point-of-attack pressure). Roster-composition rules add `lineup_size` (avg height <
77.5") and `secondary_creation` (< 2 players with AST% ≥ 25). Each need stores its
percentile and a plain-English explanation shown in the UI.

## 5. Roster fit

```
F = Σₖ n_k·Δs_k − γ·Σₖ max(0, r_k)        γ = 0.35
```

`n_k` = need severity; `Δs_k` = minutes-weighted change in skill *k* (incoming −
outgoing), where skills are percentiles of the scored population; `r_k` penalizes
adding to skills where the roster's top rotation is already above the 70th
percentile.

## 6. Team projection and rotation

Post-trade projection **reallocates the 240 regulation minutes** rather than summing
player values: proportional to established minutes (a proxy for coach trust), capped
at 36 min/player, user-overridable; availability discounts expected minutes with
replacement-level (TEI −2.0) fill-in. Team ΔNetRating ≈ change in minutes-weighted
average TEI (five players share the floor).

Wins conversion is **fit on ingested data**, not hard-coded:

```
wins = 40.93 + 2.235 × net_rating     (90 team-seasons, R² = 0.953, σ_resid = 2.9)
```

`ΔW = slope·ΔNet·(games/82)`. The calibration, sample size, and fit quality are
stored with the model version.

## 7. Contract value (when data permits)

With a configured contract provider, surplus = market share − actual salary share of
cap, where the market share uses a documented cap-dollar-per-impact curve
(replacement ≈ 2.5% of cap, average rotation ≈ 8%, star ≈ 25%, ceiling 35%). This is
labeled a heuristic: a proper market-salary regression requires historical contract
data no bundled provider supplies ([model card](model-card-market-value.md)). With no
provider, the component is excluded entirely.

## 8. Availability

```
Availability_i = Σₛ λ^(s−1)·GPᵢ,ₛ / Σₛ λ^(s−1)·82
```

over the seasons the player was in the league. This is historical availability, not
a medical prediction — TradeLab does not model injuries.

## 9. Age curve and timeline

A conservative piecewise curve (+0.8 TEI/yr under 21 → −1.0 over 36) applied
cumulatively for multi-year horizons; timeline alignment maps age → fit with the
scenario strategy (contenders prize 25–33; rebuilds prize ≤ 25). Documented in
`age_curve.py`; deliberately modest to avoid precise long-range claims.

## 10. Uncertainty

2,000 Monte Carlo draws (fixed seed) per evaluation over: player TEI (validation
residual σ per player), availability (Beta concentrated at the historical rate),
minutes noise (±12%), and wins-conversion slope (±15%). Reported: median, p10, p90,
P(Δwins > 0), and top per-player uncertainty contributions. Small differences are
never presented as certainty.

## 11. Sensitivity

500 weight vectors sampled from a Dirichlet centered on the user's weights
(concentration 50) → share of samples in which each alternative ranks first, rank
volatility, and median rank; plus one-at-a-time ±50% tornado bars. A recommendation
is called robust only if it survives these perturbations.

## Reproducibility

Fixed seed (20260720) for all stochastic steps; every model version records
algorithm, features, target, training window, validation metrics, artifact path,
code commit, and timestamp in `model_versions`. `make sync-data && make train &&
make score` reproduces the full pipeline.
