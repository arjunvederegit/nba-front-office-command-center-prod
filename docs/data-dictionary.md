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
| `transactions` | reserved for a per-player transaction provider; unused |
| `draft_picks` | `is_verified` false unless an authoritative provider exists |
| `league_cap_parameters` | per league year: cap, tax, aprons, minimum, source + verification timestamp, `extras` JSON |

## Completed trades (R6)

Separate from `trade_proposals` on purpose: a proposal is something a user built and can
edit, a historical trade is something that happened and cannot be. Separate from
`transactions` because that table is one row per (player, team, type) and cannot express
a trade at all — the corpus holds 69 trades with three or more teams, one with seven,
where the same franchise both sends and receives.

| Table | Grain | Notes |
| --- | --- | --- |
| `historical_trades` | one completed trade | season, date, `n_teams`, the source's sentence and notes kept **verbatim**, `unparsed_assets` (phrases the grammar could not read — five in ten seasons, kept rather than dropped), `trade_exception_team_ids` resolved against the trade's own participants and `trade_exception_unresolved` where a city names two of them |
| `historical_trade_assets` | one asset moving one way | direction lives on the asset, because a three-team trade has legs both ways between the same pair. Player legs carry `player_name` as printed, `source_player_slug` (Basketball-Reference's id, kept so a resolution can be re-checked against the source) and `resolution_method`, which is `ambiguous` or `none` where the name did not resolve. Pick legs carry `conveyance` in the same vocabulary `draft_picks` uses, the source's `note_text`, `note_binding_ambiguous` where a trade moved two picks of one year and round, and `later_selected` where the source says who the pick became |

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
