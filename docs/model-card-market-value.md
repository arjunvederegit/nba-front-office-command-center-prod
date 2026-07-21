# Model card — Contract / market value

**Status: heuristic, inactive by default.** A market-salary regression requires
historical contract data; no lawful bundled source exists in this repository, so the
contract-value component is **excluded from every composite score until a contract
provider is configured** — it is never estimated silently.

## Intended use (when contract data is present)

Rank the salary-efficiency direction of a trade (surplus in vs surplus out) as one
of six components, with the raw cap-share calculation attached.

## Excluded uses

Contract negotiation, arbitration, or any real financial decision · presenting the
heuristic as a fitted market model.

## Method (documented heuristic)

`surplus_i = market_share(TEI_i) − actual_salary_i / cap`, where `market_share` is a
piecewise curve anchored at: replacement ≈ 2.5% of cap (veteran-minimum
neighborhood), league-average rotation player ≈ 8%, star (TEI +5) ≈ 25%, ceiling 35%
(max-contract share). Component score = 50 + 250 × net surplus (clipped 0–100).

## Upgrade path (defined, not yet built)

With multi-year historical salaries from a configured provider: log-salary
regression on impact, age, minutes, role, availability, and contract year, using
cap-percentage rather than nominal dollars across seasons; cross-validated MAE
reported here and in `model_versions`.

## Limitations

The anchors are judgment calls (documented, tunable); no aging-curve interaction; no
option/incentive structure modeling. All of this is visible in the UI as the
"cap-dollar-per-impact heuristic" label.

## Update cadence

Re-derived on each evaluation; anchors reviewed when cap parameters change.
