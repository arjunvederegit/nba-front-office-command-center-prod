# Model card — TradeLab Estimated Impact (TEI)

**Model:** ridge regression (α=10), chosen over a transparent weighted index and a
persistence baseline by time-aware validation. Version metadata in `model_versions`
(algorithm, features, target, metrics, artifact, commit).

## Intended use

Comparative, per-100-possession impact estimates for exploratory trade analysis in
TradeLab: rotation-weighted team projections, player comparisons, candidate
filtering. Always displayed with uncertainty bands.

## Excluded uses

Player valuation for real transactions or contracts · performance management ·
public player rankings presented as authoritative · any use that strips the
uncertainty bands · claiming equivalence to RAPTOR/EPM/LEBRON/BPM (it is none of
these).

## Training data

NBA.com per-season Base + Advanced + Estimated player statistics (2023-24 →
2025-26) ingested via `nba_api`; players with ≥200 minutes in the window. No
synthetic data.

## Target

Next-season `0.6·z(PIE) + 0.4·z(NET_RATING)`, minutes-weighted z-scores within each
season — a box-derived impact **proxy** (documented as such; see ADR-10).

## Features

Recency-weighted (λ=0.7, minutes-weighted) z-scores of: pts/75, TS%, USG%, AST%,
TOV%, OREB%, DREB%, steals/min, blocks/min, 3PA rate, FTA rate, minutes, PIE,
on-court net rating; plus age.

## Validation (actual, from this snapshot)

- Split: train 2023-24→2024-25 transitions (n=447); validate 2024-25→2025-26
  (n=464). No random row splits across seasons.
- Held-out MAE (z-units): **ridge 0.637** · index 0.645 · persistence 0.717.
- Residual σ 0.985 z-units → the ±band shown as `tei_low/high` (10th/90th pct,
  normal-residual approximation).

## Limitations

Box-score-only: no tracking, matchup, or lineup-context data; defense is
under-measured (stocks + DREB + net-rating echo). One validation transition (three
seasons ingested); residual-based bands understate tail risk for role changes,
injuries, and aging outliers. Minutes threshold excludes fringe players (shown as
"no estimate", not zero).

## Fairness considerations

The model scores on-court production only, is not used for any employment or
compensation decision, and inherits any measurement biases present in NBA.com box
statistics (e.g., defensive contributions that don't appear in counting stats are
under-credited).

## Update cadence

Retrain weekly or after each data refresh (`make train`); every run writes a new
version and deactivates the old one; the UI's /data-health lists the active version
and metrics.
