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
| Transparent index | documented weighted z-score blend (weights in `impact.py::INDEX_WEIGHTS`) |
| **Ridge (chosen)** | α=10, predicts next-season `0.6·z(PIE) + 0.4·z(NET_RATING)` |

Validation is **time-aware**: train on the 2023-24→2024-25 transition (n=447),
validate on 2024-25→2025-26 (n=464). Individual rows are never randomly split across
seasons (leakage).

| Model | Held-out MAE |
| --- | --- |
| Ridge | **0.637** |
| Transparent index | 0.645 |
| Persistence | 0.717 |

Scores are scaled ×2.5 to index points (elite ≈ +5). Uncertainty bands
(`tei_low/high` = 10th/90th pct) come from the validation residual σ (0.985 z-units)
under a normal-residual assumption — a documented approximation.

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
