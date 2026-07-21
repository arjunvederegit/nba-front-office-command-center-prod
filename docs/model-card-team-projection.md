# Model card — Team projection (net rating → wins)

**Model:** linear regression `wins = a + b · net_rating` fit on ingested
team-seasons, feeding the rotation-based trade projection.

## Intended use

Convert modeled post-trade net-rating changes into an interpretable "projected
wins" delta, with the conversion's own uncertainty propagated into the Monte Carlo
band.

## Excluded uses

Season win-total forecasting for betting or public prediction · standings
projections presented as authoritative.

## Training data

90 team-seasons (2023-24 → 2025-26): NBA.com Advanced team NET_RATING (via
`LeagueDashTeamStats`) joined to final standings (via `LeagueStandingsV3`).

## Validation (actual, from this snapshot)

slope **2.235 wins per net-rating point**, intercept 40.93, **R² = 0.953**, residual
σ = 2.9 wins, n = 90. Falls back to the widely replicated ~2.7 wins/point with an
explicit `calibrated: false` flag if fewer than 30 team-seasons are available.

## How it's used

`ΔNetRating` comes from the 240-minute rotation reallocation (availability-discounted
minutes-weighted TEI). `ΔW = slope · ΔNet · games/82`. In Monte Carlo, the slope is
drawn with ±15% noise alongside player-level draws.

## Limitations

Cross-sectional fit assumes roster-context stability (same-season relationship
applied to a hypothetical roster change); minute reallocation is a model of coach
behavior, not a prediction of it; three seasons of calibration data.

## Update cadence

Refit on every `make train`; slope, R², and n stored with the model version and
displayed on /data-health.
