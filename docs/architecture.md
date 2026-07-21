# Architecture

## System overview

```
┌───────────────────────────── Browser ─────────────────────────────┐
│ Next.js 16 App Router · Tailwind · TanStack Query · dnd-kit       │
│ pages: / decision-room teams/[id] players/[id] trade-builder      │
│        trades/[id] compare methodology data-health about          │
└───────────────▲───────────────────────────────────────────────────┘
                │ /api/v1 (Next rewrite → FastAPI)
┌───────────────┴───────────────────────────────────────────────────┐
│ FastAPI (app/main.py)                                             │
│  middleware: request-id · rate limit · secure headers · CORS      │
│  errors: deterministic {error:{code,message,request_id}}          │
│                                                                   │
│  api/v1 ──► services ──► analytics / cba ──► db (SQLAlchemy 2)    │
│                │                                                  │
│                └──► integrations/nba_api (the ONLY NBA.com path)  │
│                └──► integrations/contracts (optional)             │
└───────────────────────────────────────────────────────────────────┘
   Postgres 16 (compose/prod) or SQLite (dev) · Redis or in-proc TTL cache
   worker: APScheduler container running the same idempotent jobs
```

## Layering rules

1. **Routers** never touch `nba_api` or raw provider payloads — they read normalized repository data and call services.
2. **All NBA.com traffic** flows through `integrations/nba_api/client.py::fetch_dataframe`: rate limiting (min-interval + concurrency semaphore), bounded retries with exponential backoff + jitter, per-endpoint circuit breaker, response caching, schema validation, classified errors, and health metrics live in exactly one place.
3. **The frontend never decides legality.** It renders `POST /trades/validate` results; the CBA engine is backend-authoritative.
4. **Analytics are pure** given a DataFrame — feature building, models, and simulations don't import FastAPI or the ORM session beyond loading rows, which makes them unit-testable with fixtures.

## Data flow

```
nba_api endpoints ──normalizers──► normalized dicts (+provenance)
     │                                    │
 [contract tests]                 ingestion/jobs.py (idempotent upserts,
                                   per-run DataSyncRun bookkeeping)
                                          │
                                   quality.py checks → data_quality_issues
                                          │
                     analytics: features → train (TEI, archetypes, wins map)
                                → score (needs) → model_versions + estimates
                                          │
                     services/evaluation: rotation → Δnet → Δwins → components
                     cba/engine: TradeContext → RuleResults → 4-state status
                                          │
                                   api/v1 + generated reports
```

## Key backend modules

| Module | Responsibility |
| --- | --- |
| `integrations/nba_api/{client,rate_limiter,retry,schemas,health}.py` | Reliability boundary for NBA.com |
| `integrations/nba_api/normalizers/` | Pure DataFrame→dict conversion, fixture-tested |
| `integrations/nba_api/provider.py` | `NBADataProvider` protocol + `SwarNBAApiProvider` |
| `integrations/contracts/` | `ContractProvider` protocol + file provider; `None` = honest default |
| `ingestion/jobs.py` | `sync_*` jobs; failures never destroy the last valid snapshot |
| `ingestion/quality.py` | 12 data-quality checks, flag/resolve lifecycle |
| `db/models.py` | 31 tables; UUID PKs; ProvenanceMixin (`source_provider`, `source_record_id`, `source_retrieved_at`, `valid_from/to`, `ingestion_run_id`) |
| `cba/` | `TradeContext` builder, rule registry, four-state engine |
| `analytics/` | TEI training/scoring, archetypes, needs, fit, projection, MC, sensitivity |
| `services/` | evaluation orchestration, candidate search, reports, payroll, data health |

## Frontend structure

- `lib/api.ts` — typed fetch client with deterministic error unwrapping.
- `lib/types.ts` — TS mirrors of API payloads.
- `components/ui.tsx` — Card/Badge/SourceLine/FreshnessBadge/UnavailableNotice/EmptyState primitives; the honesty vocabulary of the UI.
- `components/charts.tsx` — component bars, tornado, uncertainty strip, Pareto scatter, rank-share bars (Recharts).
- Interactive pages are client components with TanStack Query; static content (methodology/about) is server-rendered.

## Reliability & security

- Circuit breaker opens after 3 consecutive classified failures per endpoint (300 s cooldown, half-open probe).
- Response cache keys embed a data-version bumped after each `sync_all`, so stale evaluations invalidate on refresh.
- `POST /api/v1/admin/sync` requires `ADMIN_TOKEN` (403 disabled when unset) so anonymous demo users can't exhaust NBA.com quota.
- Secrets only via environment; logs redact `key=`/`token=` patterns; provider payloads are not logged wholesale.
- In-process per-IP rate limiting (240 req/min) + secure headers; ORM-only SQL.

## Scheduling

`docker compose` runs `app/worker.py` (APScheduler): rosters/standings every 6 h, stats/games/contracts daily — all configurable via env; every job is safe to re-run (idempotent upserts on natural keys). The CLI (`python -m app.cli`) exposes the same jobs for manual/CI use.
