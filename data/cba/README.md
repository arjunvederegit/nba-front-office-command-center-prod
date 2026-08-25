# data/cba/

League-wide CBA money: cap, tax, floor, aprons and the exception amounts, one record per
league year. These are **published league-wide figures**, not per-player contract data —
that distinction is why this directory is committed while `data/contracts/` and
`data/imports/` are not.

## `nba_cap_parameters.yml`

| Field | Meaning |
| --- | --- |
| `status` | `confirmed` · `nba_estimate` · `projected` — **never collapse these** |
| `confirmation_or_projection` | the sentence that justifies the `status` |
| `source_name` | which of the `sources:` entries the row came from |
| `notes` | per-row caveat |

Only **2026-27 is `confirmed`** (NBA Communications, official release of June 30, 2026).
Every later season is an estimate or a projection and must be rendered with its status
attached. 2030-31 onward sits beyond the currently guaranteed CBA horizon — the 2023 CBA
runs through 2029-30 with an opt-out after 2028-29 — so those rows are projections of a
cap formula that may not exist.

The 2026-27 row agrees exactly with `backend/app/config/cap_rules/2026-27.yaml`
(cap 164,961,000 · tax 200,428,000 · apron 1 209,015,000 · apron 2 221,686,000 ·
floor 148,465,000), which is the file `make seed-config` actually loads.

### What loads this file

**Nothing, today.** `make seed-config` reads `backend/app/config/cap_rules/*.yaml`, which
carries the four thresholds plus `minimum_team_salary` for the two league years the
product evaluates under. This file is the wider reference set — MLE/BAE amounts and the
projection horizon — kept version-controlled and source-attributed so a future release
that needs a 2029-30 exception amount has a citable origin rather than a literal in code.
It is committed as a *reference dataset*, and it is not a second source of truth for the
seeded league years.

### Redistribution

Cap, tax and apron thresholds are published figures announced by the league and reported
league-wide; the projections are attributed to their publisher. No provider payload,
no per-player salary, and no scraped page is stored here — those stay local and
gitignored (see `data/README.md` and `data/contracts/README.md`).
