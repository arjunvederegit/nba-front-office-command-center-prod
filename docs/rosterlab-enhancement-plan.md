# RosterLab enhancement plan

Working plan for the TradeLab → **RosterLab — NBA Front Office Simulator**
transformation (July 2026). This is the Phase-1 audit + design document; the
repository history shows the execution.

## Current-state findings (audit)

- **Stack is healthy**: FastAPI backend (31 tables, provenance columns, Alembic),
  Next.js 16 frontend, 76+14+3 passing tests, ruff/mypy/eslint/tsc clean, git in
  sync with `origin/main` (pushed via GitHub Desktop).
- **Data**: real 2025-26 NBA snapshot ingested via `nba_api` (530 rostered players,
  90 standings, 5,142 player-stat rows, 1,230 games); TEI/archetypes/needs trained.
  No contract provider configured (honest unavailable states).
- **Functional screens**: landing, decision room, teams/[id], players/[id],
  trade-builder, trades/[id], compare, methodology, data-health, about. All backed
  by real endpoints; none are placeholders. Presentation is admin-dashboard-ish:
  near-monochrome, initials-only avatars, no team identity, technical labels.
- **New user-supplied assets** (untracked, must never be committed wholesale):
  - `nbalogos/<abbr>.png` — 30 logos, CC0 Kaggle dataset. Naming quirks: `phl`→PHI,
    `uth`→UTA, `mia.gif` is a GIF.
  - `nbaplayerimages/<Player Name>/Image_N.jpg` — 2,476 name-keyed folders,
    10,216 files, ~171 MB. Requires name→`nba_player_id` identity resolution.
  - `~/Downloads/nba_player_stats_2026.csv` → staged at
    `data/imports/nba_player_stats_2026.csv` (gitignored): 582 rows of 2025-26
    **season totals**, one row per player, official `PLAYER_ID`/`TEAM_ID` keys,
    columns exactly as specified (GP/MIN/shooting/REB/AST/STL/BLK/TOV/PF/PTS/EFF/
    AST_TOV/STL_TOV). No duplicate players in this export.

## Data model changes

1. `media_assets` table — asset manifest with identity resolution:
   `entity_type` (player|team), internal FK id, `nba_id`, `file_path` (relative to
   asset root), `match_method` (nba_id | exact_name | normalized_name | manual),
   `confidence` (high|medium|unmatched), `alt_text`, provenance columns. Backend
   serves files via `/api/v1/assets/...` (no 171 MB in git or `public/`);
   deterministic frontend fallbacks (initials / abbreviation badge).
2. Imported season totals reuse `player_season_stats` with `stat_type="totals"`,
   `source_provider="user_import_csv"`, raw totals + safely derived per-game values
   in `stats` JSON, import timestamp in provenance. Totals are never presented as
   per-game.
3. Contracts reuse existing `contracts`/`contract_years` via a new
   `BasketballReferenceSnapshotProvider` (`CONTRACT_DATA_PROVIDER=bbref_snapshot`):
   parses a **user-downloaded** basketball-reference.com contracts page
   (HTML/CSV snapshot in `data/imports/contracts/`) — no fragile live scraping.
   Fixture-tested parser; unmatched rows preserved for review in
   `data_quality_issues`; option/guarantee markers only when present.
4. `external_datasets` registry rows (in `data_sources`) for: user CSV, image
   assets, logo assets, Kaggle basketball DB — handle, checksum, timestamp, run ID.
5. Kaggle (`wyattowalsh/basketball`): reproducible `import-kaggle` CLI using
   `kagglehub` with a configurable cache dir; schema inspection first; ingest only
   player career/season aggregates needed by Player Lab; idempotent; graceful,
   tested failure path when the dataset/network is unavailable.

Source hierarchy (per field/domain, conflicts logged, never silently overwritten):
nba_api (identity, rosters, stats, standings) → 2026 CSV (current totals snapshot)
→ Kaggle (pre-2023 history) → BBRef snapshot (contracts) → local images (visuals).

## UI architecture

- Rebrand: **RosterLab — NBA Front Office Simulator**; original SVG mark (basketball
  seam arc + rising chart line inside an R roundel); refreshed dark palette with
  team-color theming tokens (30-team map, contextual accents only).
- Nav: Home · Team Hub · Trade Machine · Compare Deals · Player Lab · Cap Lab ·
  Methodology · Data Status.
- Shared primitives: `TeamLogo`, `PlayerPhoto` (lazy, object-fit, alt text,
  deterministic fallbacks), `TeamThemeProvider` (CSS vars), toasts, skeletons,
  fan-vs-advanced disclosure components, "How is this calculated?" links.
- Pages: Home (hero + court SVG, team picker grid, tool suite, recent deals,
  compact freshness); Team Hub (position-grouped roster with photos,
  strengths/weaknesses, window summary, payroll honesty, CTAs); Trade Machine
  (team-color columns, player cards with photo/salary/stats, filters, drawer,
  fan verdict + advanced tabs, share URL); Compare Deals (deal cards, matrix,
  live weight sliders re-ranking client-side from stored components, plain-English
  Pareto); Player Lab (photo directory, totals + per-game, percentiles, 2–4 player
  compare); Cap Lab (payroll by season, top/expiring contracts, distribution chart —
  fully honest empty state without contract import); Data Status (6 source cards +
  expandable technical details); Methodology (plain layer + technical layer).
- Favorite team persisted in `localStorage`, personalizing Home/Trade defaults.

## Migration strategy

Additive Alembic migration only (`media_assets`); no changes to existing tables →
zero risk to ingested data. Frontend renames keep old routes redirecting
(`/decision-room` → `/trade-machine` context, `/data-health` → `/data-status`) so
saved links and e2e specs stay coherent (specs updated with the new flows).

## Risks & fallbacks

- **Name-keyed player images**: resolve by exact then normalized (diacritics,
  suffixes, punctuation) full-name match against `players`; ambiguous/unmatched →
  recorded in manifest as unmatched, UI falls back to initials; coverage % on Data
  Status.
- **BBRef access**: live fetch is fragile/ToS-sensitive → snapshot import path is
  primary; parser fixture-tested; provider absent ⇒ existing honest unavailable
  states remain.
- **Kaggle download size/credentials**: attempted opportunistically; failure leaves
  a tested "not configured" state, docs cover auth; app never depends on it.
- **CSV drift**: importer validates required columns/IDs, logs rejects to
  `data_quality_issues`, refuses silently-wrong data.
- **Scope**: prioritized order is Trade Machine → Home/Team Hub → Player Lab →
  Compare → Cap Lab/Data Status → docs; each lands as a working committed stage.
