# RosterLab — Autonomous Run State

**Purpose:** resumable state for the autonomous roadmap execution described in
`ROSTERLAB_IMPLEMENTATION_PLAN.md`. A fresh session can read this file alone and continue safely.

---

## Environment

| Fact | Value |
| --- | --- |
| Repo root | `/Users/arjunvedere/Desktop/nba-front-office-command-center-prod/nba front office command center prod` |
| Working branch | `feat/rosterlab-autonomous-roadmap` |
| Base commit | `f16dedc` (main, the audited/planned commit) |
| Remote | `origin` → `https://github.com/arjunvederegit/nba-front-office-command-center-prod.git` |
| `gh auth` | ✅ `arjunvederegit`, scopes `gist, read:org, repo, workflow` |
| Backend venv | `backend/.venv` (Python 3.11.14) |
| Node | v25.5.0, `frontend/node_modules` present |
| DB backup | `<scratchpad>/backups/tradelab.db.baseline` (17 MB, taken before any change) |

## Baseline measurements (commit `f16dedc`)

| Metric | Value |
| --- | --- |
| Backend tests | **114 passed**, 1 warning, 4.32 s |
| Backend coverage (`--cov=app`) | **68 %** (4263 statements, 1375 missed) |
| Frontend unit tests | **15 passed** (2 files) |
| `data/external/` | **empty** — the Kaggle `nbadb` dataset is NOT present |

## Datasets present (inspected)

| Path | Bytes | Nature |
| --- | --- | --- |
| `data/cba/nba_cap_parameters.yml` | ~4 K | Cap/tax/apron/MLE 2026-27 (**confirmed**, NBA Communications) → 2032-33 (estimates/projections, SalarySwish). Carries an explicit `status` per season. |
| `data/imports/contracts/players.html` | 454 K | Basketball-Reference contracts snapshot, saved 2026-07-28 |
| `data/imports/draft_picks/realgm_future_drafts.html` | 291 K | RealGM "NBA Future Drafts Detailed", page datetime 2026-07-28 00:49:32 |
| `data/imports/nba_player_stats_2026.csv` | 820 K (dir) | 2025-26 season totals, already wired to `make import-stats-csv` |
| `data/external/` | 0 | **empty — Kaggle `nbadb` unavailable** |

---

## Current position

**Release:** R0 — test scaffolding and CI teeth
**Work item:** R0-1 (sanity fixtures + xfail scaffolding)
**Status:** in progress

## Completed work

_(none yet)_

## Commits

_(none yet)_

## Decisions and deviations

_(none yet)_

## Active blockers

- **Kaggle `nbadb` absent.** Expected at `data/external/` (see `backend/app/integrations/kaggle_nba/importer.py`
  for the tables consumed). All lineup-aware fit, tracking and play-type work is deferred; nothing in R0–R5 is
  blocked by it.

## Exact next step

Implement R0-1: add a `seeded_league` fixture to `backend/tests/conftest.py` and
`backend/tests/unit/test_evaluation_sanity.py` with `@pytest.mark.xfail(strict=True)` on every property that
currently fails.

## Push status

Branch created locally; nothing pushed yet.
