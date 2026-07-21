# Data dictionary

All tables use UUID string primary keys. Provider-derived tables carry the
provenance columns `source_provider`, `source_record_id`, `source_retrieved_at`,
`valid_from`, `valid_to`, `ingestion_run_id`, plus `created_at`/`updated_at`.
External NBA identifiers are separate columns (`nba_team_id`, `nba_player_id`,
`nba_game_id`) so internal relationships never depend on provider IDs.

## Identity & basketball data

| Table | Grain | Key fields |
| --- | --- | --- |
| `teams` | NBA team | `nba_team_id` (unique), name/abbr/city, conference/division (from standings) |
| `players` | NBA player | `nba_player_id` (unique), name, `is_active`, bio (birth_date, height_inches, weight_lbs, position, years_experience, draft_*) enriched from rosters |
| `player_team_history` | observed player→team assignment | player, team, season, `observed_at` |
| `rosters` | roster snapshot row | team, player, season, jersey, position, age, `is_current` (previous snapshots keep `valid_to`) |
| `games` | completed game | `nba_game_id`, season, date, home/away team + scores, status |
| `player_game_stats` | player-game (reserved; populated when game-log-P ingestion is enabled) | game, player, minutes, `stats` JSON |
| `player_season_stats` | player-season-stattype | `stat_type` ∈ base/advanced/estimated; GP, minutes, full `stats` JSON |
| `team_season_stats` | team-season-stattype | `stat_type`, `stats` JSON (OFF/DEF/NET_RATING, four factors, …) |
| `standings` | team-season | W/L, win%, conference, playoff_rank, `details` JSON |

## Contracts & league finance (optional providers)

| Table | Notes |
| --- | --- |
| `contracts` | header: type, signed_date, no_trade_clause, **source_name/source_date shown in UI** |
| `contract_years` | season, salary, guaranteed, player/team options |
| `injuries` | empty unless an injury provider is configured — never fabricated |
| `transactions` | reserved for a transaction provider |
| `draft_picks` | `is_verified` false unless an authoritative provider exists |
| `league_cap_parameters` | per league year: cap, tax, aprons, minimum, source + verification timestamp, `extras` JSON |

## Data engineering

| Table | Notes |
| --- | --- |
| `data_sources` | registered providers + package versions |
| `data_sync_runs` | one row per job run: status, rows_written, error class/message, detail JSON |
| `data_quality_issues` | check name, severity, message; `resolved_at` set when a later pass no longer detects it |

## Modeling

| Table | Notes |
| --- | --- |
| `model_versions` | name (player_impact / player_archetype / team_projection), version, algorithm, training period, features, target, validation metrics JSON, artifact path, code commit, `is_active` |
| `player_impact_estimates` | per player-season-modelversion: `tei`, offense/defense splits, `tei_low/high` band, availability, minutes_estimate, inputs JSON |
| `player_archetypes` | cluster id + human label + distance |
| `team_needs` | need_key, severity 0–1, percentile, plain-English explanation |

## Decision objects

| Table | Notes |
| --- | --- |
| `scenarios` / `scenario_weights` | strategy frame + normalized component weights |
| `trade_proposals` / `trade_teams` / `trade_assets` | 2–3 teams; assets are players or (hypothetical, labeled) picks |
| `trade_rule_results` | persisted rule-level audit trail per saved trade |
| `trade_evaluations` | per team: legality status, composite, components, uncertainty, sensitivity, explanation JSON, data_version |
| `comparison_sets` | named list of 2–5 trade ids |
| `generated_reports` | rendered executive memos (markdown/html), `llm_enhanced` flag (false unless an LLM polished prose) |
