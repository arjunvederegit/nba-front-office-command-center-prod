# R0 — Test scaffolding and CI teeth

**Branch:** `feat/rosterlab-autonomous-roadmap` · **Base:** `f16dedc` (main)
**Rule for this release:** no production behaviour changes. Verified below.

---

## 1. Scope completed

| Item | Delivered |
| --- | --- |
| **R0-1** | `seeded_league` fixture (two 15-man rosters on the full modelling path) plus 23 `xfail(strict=True)` QA pins across four files |
| **R0-2** | `alembic check` no longer swallowed by `\|\| true` |
| **R0-3** | `--cov-fail-under=68` in CI **and** `make test-backend` |
| **R0-4** | New `e2e` CI job: migrate → seed → train → score → build → Playwright, with artifact upload on failure |
| **R0-5** | `scripts/visual_qa.mjs` exits non-zero on problems; adds `/players/[id]`, an invalid player id and an invalid team id; detects empty bodies |
| **R0-6** | `make test-backend` mirrors CI; `make help` now lists `e2e` |

## 2. The xfail scaffolding

23 properties are pinned. Each is green today *because the defect is present*; the moment
it is fixed the run turns red, so an accidental early fix cannot pass silently.

| File | Pins |
| --- | --- |
| `backend/tests/unit/test_evaluation_sanity.py` | QA-1 (×2), QA-5, QA-6 (×2), QA-8, R1-4 (×2), C13 drivers, C2/R3-5 units, C13 `composite_utility`, C13 `normalize_weights` |
| `backend/tests/unit/test_data_health.py` | QA-4 (×2), C13 timezone mismatch, C13 open-issue total |
| `backend/tests/integration/test_api.py` | QA-2 (API + builder), QA-3, QA-7, QA-13, `?format=` validation |
| `backend/tests/unit/test_stats_csv.py` | QA-11 |
| `frontend/tests/unit/qa-pins.test.ts` | QA-12, the `-0.0` sign derivation (`it.fails`, vitest's strict-xfail) |

Five sanity tests **pass today** and must keep passing: the fixture self-checks (the
modelling path is genuinely exercised; the giveaway is genuinely detected as illegal),
`verified_legal` is never returned alongside an `unavailable` rule, excluded components
are reported and downgrade confidence, and the bucket *order* in `fanVerdict` is correct
(C12 — only the label text is inverted, not the thresholds).

### Fixture design notes

`seeded_league` carries three deliberate holes, each pinning a distinct property:

- `AAA[14]` has **no `PlayerImpactEstimate`** → the no-undisclosed-defaults property.
- `AAA[13]` / `BBB[13]` have **no `Contract`** → forces component exclusion and weight
  renormalization, which is the only condition under which the driver-reconciliation
  defect appears. This also mirrors the live database, where `contracts` = 0 rows.
- Impact bands use the **production width, 6.3106** (the single distinct value observed
  live), so `TEI_SIGMA_DEFAULT = 1.5` is *narrower* than a real player's band exactly as
  it is in production.

Two pins had to be strengthened after they initially XPASSed — recorded because they show
the scaffolding working as designed:

| Pin | First attempt | Why it XPASSed | Correction |
| --- | --- | --- | --- |
| unmodelled band | fixture band ±1.2 → σ 0.936 | 1.5 > 0.936, so the default looked *less* confident | band set to the production 6.3106 → σ 2.462 |
| MC vs point estimate | 1-for-1, `abs=0.05` | the gap scales with trade size (0.03 at n=1) | 5-for-5, where the gap is 0.31 |

## 3. Files changed

```
.github/workflows/ci.yml                    +67 −6
Makefile                                    +27 −4
backend/app/cli.py                          +12
backend/app/ingestion/demo_seed.py          new, 300 lines
backend/tests/conftest.py                   +191
backend/tests/integration/test_api.py       +124
backend/tests/unit/test_data_health.py      new
backend/tests/unit/test_demo_seed.py        new
backend/tests/unit/test_evaluation_sanity.py new
backend/tests/unit/test_stats_csv.py        +23
frontend/playwright.config.ts               +27 −11
frontend/tests/e2e/decision-flow.spec.ts    +28
frontend/tests/unit/qa-pins.test.ts         new
scripts/capture_screenshots.mjs             +8 −2
scripts/visual_qa.mjs                       +52 −13
```

No file under `backend/app/` changed except `cli.py` (a new dev-only subcommand) and the
new `demo_seed.py`. **No production code path was modified.**

## 4. Deviations from the plan

### D1 — `make seed-demo` and the e2e database were pulled forward from R1-7 into R0

R0-4 requires Playwright to run in CI. CI has no ingested database, so the job could not
have passed. `backend/app/ingestion/demo_seed.py` builds a dedicated, deterministic
database:

- **Team identity is real and provider-backed** — `nba_api`'s *bundled static* team table
  (offline, no network, no scraping), stamped `source_provider="nba_api_static"`.
- **Everything else is synthetic and labelled** — players named `Demo <TEAM> <n>`, every
  row stamped `source_provider="demo_seed"`.
- **It refuses to run** against a database that already holds `nba_api` rows, so it can
  never contaminate a development database.

This is not synthetic *production* data: it is written only to the database
`DATABASE_URL` points at, it is gitignored, and it is created and destroyed by CI.

### D2 — the coverage floor of 68 required raising coverage first

The plan specifies `--cov-fail-under=68`, "the measured value". The measured value is the
*displayed rounding*: the precise baseline was **67.74 %** (1375 missed of 4263), so a
floor of 68 fails at the baseline commit. Rather than lower the floor to 67, `demo_seed.py`
was covered by tests (it is code CI depends on), taking the total to **69.07 %**. The floor
of 68 now passes with real margin.

### D3 — `scripts/visual_qa.mjs` could not run at all

Its header says "run from `frontend/`, where `@playwright/test` resolves", but ESM
resolves bare specifiers from the *importing file's* directory upward, and there is no
`node_modules` at the repo root. Both harness scripts now resolve explicitly through
`createRequire(new URL("../frontend/package.json", import.meta.url))`. This is a
prerequisite for R0-5, not scope expansion — the exit code would be meaningless on a
script that throws on import.

### D4 — the e2e full-flow test only passed because of database pollution

Against a fresh database, step 8 ("Strategy Lab lists it") fails: the Strategy Lab is a
*comparison* board and renders an empty state below two saved deals. The suite passed
locally only because the development database already carried deals from earlier runs —
the exact pollution R1-7 exists to remove. The test now creates its comparison baseline
through the API as explicit setup.

## 5. Evidence

### Backend

```
pytest -q --cov=app --cov-report=term --cov-fail-under=68
125 passed, 23 xfailed, 1 warning in 8.65s
TOTAL   4345   1344   69%
Required test coverage of 68% reached. Total coverage: 69.07%
```

Baseline for comparison: `114 passed`, `TOTAL 4263 1375 68%` (67.74 % precise).

```
ruff check app tests   → All checks passed!
mypy app               → Success: no issues found in 77 source files
alembic upgrade head && alembic check → "No new upgrade operations detected." (exit 0)
```

### Frontend

```
npm run test -- --run  → 3 files, 18 passed | 2 expected fail (20)
npm run lint           → clean
npx tsc --noEmit       → clean
```

### End to end

Against the **dedicated demo database** (the CI path, `make seed-demo` + `npx playwright test`):

```
✓ overview presents the platform with honest data status
✓ renamed modules keep old links working
✓ data health reports sources and never hides a missing one
✓ player explorer lists imported season totals
✓ full flow: team outlook → strategy → trade evaluator → rules → evaluate → save → compare
5 passed (10.5s)
```

Against the developer's ingested database: **5 passed (7.5 s)**.

### Visual QA

`node scripts/visual_qa.mjs docs/qa/r0-baseline` — **98 screenshots**, 14 routes × 7
viewports (1920, 1440, 1366, 1280, 1024, 768, 390 px):

```
CLEAN: no horizontal overflow, no console errors, no empty pages   (exit 0)
```

The first run **exited 1** on the two newly-added invalid-id routes, where the browser's
own 404 fetch log was being counted as a page error. Expected-404 noise is now filtered
for routes marked `expectNotFound`, while `pageerror` and every other console error still
fail the run.

The invalid-id screenshots are themselves useful evidence — they show two defects R1 will
fix, now captured rather than merely described:

- `String(error)` leaks the `Error:` prefix into user copy:
  *"Could not load player: **Error:** player not-a-real-player-id not found"*
- The header still reads 🟢 **"Live data"** against a database whose NBA tables were last
  retrieved on Jul 21 (QA-4).

## 6. Release gate

- [x] No production code path changed (see §3).
- [x] Every known-wrong behaviour is pinned `xfail(strict=True)`; none flipped early.
- [x] CI `alembic check` and the coverage floor can now fail the build.
- [x] Playwright runs in CI against a reproducible database.
- [x] The visual-QA harness runs, and can fail.
- [x] Backend, frontend, lint, type-check, migration and e2e all green.

## 7. Known limitations

- The `e2e` CI job runs Chromium only.
- `make visual-qa` is not yet wired into CI; it needs a stack with data, which the e2e job
  builds but does not currently hand off. Deferred to R7.
- The demo league's `wins ~ net_rating` fit is meaningless on synthetic data (n = 30,
  R² = 0.003) and is reported as `calibrated: true` because the code's own n ≥ 30 rule
  fires. This is a property of the *code*, not of the seed, and is addressed in R3-2's
  labelling work.

## 8. Next eligible release

**R1 — correctness and honesty.** Order per the plan: A1 R1-3 → A2 R1-4 → A3 R1-2 →
A4 R1-5, with lane B (R1-1, R1-6, R1-8, R1-9) in parallel, then R1-7, then R1-D docs.
