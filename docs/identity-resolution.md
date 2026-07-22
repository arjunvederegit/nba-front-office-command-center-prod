# Identity resolution

RosterLab joins five data sources. Stable NBA identifiers are the canonical keys;
names are a last resort with recorded confidence — **never a silent guess**.

## Canonical keys

- `players.nba_player_id` — official NBA `PLAYER_ID` (from `nba_api` static data +
  roster ingestion). Internal relationships use UUID PKs; the NBA id is the external
  join key.
- `teams.nba_team_id` / `teams.abbreviation` — official `TEAM_ID` and 3-letter code.

## Per-source resolution

| Source | Join method | Confidence recorded |
| --- | --- | --- |
| nba_api rosters/stats | `PLAYER_ID`/`TEAM_ID` (exact) | high (authoritative) |
| 2026 season-totals CSV | `PLAYER_ID` exact only — name is never used; unmatched ids → `data_quality_issues` (`csv_unmatched_player`) and the row is skipped | high or rejected |
| Kaggle basketball DB | `person_id == nba_player_id` exact; fills **only NULL** fields; disagreements with existing non-null values → `kaggle_source_conflict` issue, value not overwritten | high; conflicts logged |
| Player image folders | folder name → exact case-insensitive `full_name` match (`exact_name`, high) → normalized match (`normalized_name`, medium: lowercase, NFD diacritic strip, punctuation removed, Jr/Sr/II–V suffixes dropped) → active-player tie-break → otherwise **unmatched** row kept for review | per-row in `media_assets.match_method`/`confidence` |
| Team logo files | filename stem → abbreviation with explicit overrides (`phl→PHI`, `uth→UTA`) | `abbreviation`, high |
| BBRef contract snapshot | player name (+ BBRef team code mapped `BRK→BKN, CHO→CHA, PHO→PHX`) matched downstream by name against `players`; unmatched names preserved in the sync run detail for review | medium; unmatched listed |

## Source hierarchy (per field/domain)

1. **nba_api** — identity, rosters, current stats, standings (authoritative).
2. **2026 CSV** — the explicitly-imported current-season totals snapshot (`stat_type="totals"`, kept separate from nba_api per-game rows; never mixed).
3. **Kaggle** — historical/bio enrichment, NULL-fill only.
4. **BBRef snapshot** — contracts/salaries (a domain nba_api does not cover).
5. **Local images** — presentation only.

Conflicts are recorded (`data_quality_issues`), surfaced on Data Status, and never
silently resolved by overwriting. Current live counts (July 2026 import): 2,196 of
2,476 image folders matched (280 unmatched, kept for review), 573/582 CSV rows
imported (9 unmatched ids recorded), 273 Kaggle field conflicts preserved.
