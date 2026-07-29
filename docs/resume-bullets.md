# Resume bullets

Truthful options, measured against this repository's actual build. Bracketed
placeholders remain until measured — do not fill them with estimates.

## Full-stack / product

- Built **TradeLab**, a full-stack NBA trade decision-support platform (Next.js 16,
  FastAPI, SQLAlchemy 2/PostgreSQL, Redis, scikit-learn) on live provider-backed
  NBA data via the open-source `nba_api` client, with provenance and freshness
  tracking on every record and screen.
- Designed a **four-state trade-legality standard** (verified legal / verified
  illegal / conditionally valid / not evaluated) and a modular 2023-CBA rules engine
  (salary-matching bands, apron restrictions, aggregation prohibition, roster
  limits) with rule-level audit trails and explicit handling of unavailable data —
  the system never overstates certainty.

## Quant / analytics

- Developed **TEI**, an original player-impact model: recency-weighted three-season
  features with strictly time-aware validation; the transparent index beat a
  persistence baseline **0.645 vs 0.717 held-out MAE** and a ridge challenger on
  team-level validity (**R² 0.751 vs 0.004**), with per-player
  uncertainty bands surfaced in every evaluation.
- Calibrated a net-rating→wins conversion on **90 ingested team-seasons (2.24
  wins/point, R² = 0.95)** instead of hard-coding a constant, and propagated its
  uncertainty through **2,000-draw Monte Carlo** trade simulations (median, p10/p90,
  P(positive)).
- Implemented **Dirichlet weight-sensitivity analysis** (first-place share, rank
  volatility, tornado charts) so recommendations are reported as robust or fragile
  with evidence, plus Pareto-dominance flags across alternatives.

## Data engineering

- Engineered a resilient NBA.com ingestion boundary — rate limiting, exponential
  backoff with jitter, per-endpoint circuit breakers, response caching, schema
  contract validation, classified errors, health metrics — feeding a 31-table
  normalized schema with idempotent, resumable sync jobs and 12 automated
  data-quality checks.
- Shipped CI (lint, typecheck, tests, migration check, Docker build, dependency
  review, secret scanning), 93 automated tests (76 backend, 14 frontend, 3
  Playwright e2e), and containerized deployment; reduced [MEASURED TASK] from
  [BASELINE] to [RESULT].

## One-liner

- Built an explainable NBA trade decision-support system on real NBA.com data —
  CBA-aware legality, validated impact modeling, Monte Carlo uncertainty, and
  sensitivity analysis — engineered end to end for data honesty.
