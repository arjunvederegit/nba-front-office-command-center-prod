export interface Provenance {
  source_provider: string;
  upstream: string;
  source_retrieved_at: string | null;
}

export interface Team {
  id: string;
  nba_team_id: number;
  full_name: string;
  abbreviation: string;
  nickname?: string;
  city: string;
  conference: string | null;
  division: string | null;
  provenance?: Provenance | null;
}

export interface RosterPlayer {
  player_id: string;
  nba_player_id: number;
  name: string;
  position: string | null;
  jersey_number: string | null;
  age: number | null;
  height_inches: number | null;
  years_experience: number | null;
  tei: number | null;
  archetype: string | null;
  availability: number | null;
}

export interface RosterResponse {
  team: Team;
  season: string;
  roster: RosterPlayer[];
  source: string;
  source_retrieved_at: string | null;
}

export interface TeamNeedItem {
  need_key: string;
  severity: number;
  percentile: number | null;
  explanation: string;
}

export interface PayrollResponse {
  team_id: string;
  league_year: string;
  roster_size: number;
  players_with_salary: number;
  payroll: number | null;
  payroll_available: boolean;
  unavailable_reason?: string;
  contract_provider_configured: boolean;
  players: {
    player_id: string;
    name: string;
    salary: number | null;
    contract_type: string | null;
    source_name: string | null;
    source_date: string | null;
  }[];
  cap_context?: {
    salary_cap: number;
    luxury_tax: number;
    first_apron: number;
    second_apron: number;
    room_below_tax: number;
    cap_source: string;
  };
}

export type RuleStatus = "pass" | "fail" | "warning" | "unavailable";
export type LegalityStatus =
  | "verified_legal"
  | "verified_illegal"
  | "conditionally_valid"
  | "not_evaluated";

export interface RuleResult {
  rule_code: string;
  status: RuleStatus;
  team_id: string | null;
  message: string;
  calculation: Record<string, unknown>;
  source_reference: string;
  confidence: "high" | "medium" | "low";
}

export interface TeamLegality {
  abbreviation: string;
  status: LegalityStatus;
  outgoing_salary: number | null;
  incoming_salary: number | null;
  payroll_before: number | null;
  payroll_after: number | null;
  apron_status_before: string | null;
  apron_status_after: string | null;
  roster_before: number;
  roster_after: number;
}

export interface LegalityResponse {
  league_year: string;
  overall_status: LegalityStatus;
  teams: Record<string, TeamLegality>;
  rule_results: RuleResult[];
  cap_parameters_source: string;
  contract_provider_configured: boolean;
}

export interface Uncertainty {
  n_draws: number;
  median: number;
  p10: number;
  p90: number;
  prob_positive: number;
  top_uncertainty_drivers: { side: string; spread_wins: number }[];
}

export interface TornadoBar {
  component: string;
  utility_low: number;
  utility_high: number;
  base: number;
}

export interface TeamEvaluation {
  team_id: string;
  legality: TeamLegality;
  composite_utility: number;
  confidence: string;
  components: Record<string, number | null>;
  excluded_components: string[];
  drivers?: { component: string; score: number; weight: number; contribution: number }[];
  weights: Record<string, number>;
  detail: Record<string, Record<string, unknown>>;
  uncertainty: Uncertainty;
  sensitivity_tornado: TornadoBar[];
  incoming: { player_id: string; name: string; tei: number }[];
  outgoing: { player_id: string; name: string; tei: number }[];
  evaluated_at: string;
}

export interface PlayerMove {
  player_id: string;
  from_team_id: string;
  to_team_id: string;
}

export interface PickMove {
  from_team_id: string;
  to_team_id: string;
  draft_year: number;
  round_number: number;
  protections?: string | null;
  is_hypothetical: boolean;
}

export interface Scenario {
  id: string;
  name: string;
  focal_team_id: string;
  focal_team: { abbreviation: string; full_name: string };
  strategy: string;
  horizon_years: number;
  risk_tolerance: string;
  untouchable_player_ids: string[];
  preferred_outgoing_player_ids: string[];
  weights: Record<string, number>;
  created_at: string;
}

export interface TradeSummary {
  id: string;
  name: string;
  scenario_id: string | null;
  created_at: string;
  teams: string[];
  n_players: number;
  n_picks: number;
}

export interface TradeDetail {
  id: string;
  name: string;
  scenario_id: string | null;
  notes: string | null;
  created_at: string;
  teams: { team_id: string; abbreviation: string; name: string }[];
  assets: {
    asset_type: string;
    from_team_id: string;
    to_team_id: string;
    player_id: string | null;
    player_name: string | null;
    draft_year: number | null;
    round_number: number | null;
    protections: string | null;
    is_hypothetical: boolean;
  }[];
  legality: LegalityResponse;
  evaluations: Record<string, TeamEvaluation>;
}

export interface ComparisonAlternative {
  trade_id: string;
  name: string;
  legality_status: LegalityStatus;
  composite_utility: number;
  components: Record<string, number | null>;
  delta_wins: number | null;
  uncertainty: Uncertainty;
  payroll_after: number | null;
  apron_status_after: string | null;
  incoming: { name: string; tei: number }[];
  outgoing: { name: string; tei: number }[];
  dominated_by: string | null;
}

export interface ComparisonResponse {
  id: string;
  name: string;
  focal_team_id: string | null;
  weights: Record<string, number>;
  alternatives: ComparisonAlternative[];
  sensitivity: {
    first_place_share: Record<string, number>;
    rank_volatility: Record<string, number>;
    median_rank: Record<string, number>;
  };
  note: string;
}

export interface DataHealth {
  generated_at: string;
  current_season: string;
  cap_league_year: string;
  providers: Record<
    string,
    {
      configured?: boolean;
      enabled?: boolean;
      package_version?: string;
      upstream?: string;
      provider?: string | null;
      note?: string | null;
      endpoints?: {
        endpoint: string;
        successes: number;
        failures: number;
        last_error: string | null;
        last_latency_ms: number | null;
      }[];
    }
  >;
  cache_backend: string;
  tables: Record<string, { rows: number; last_retrieved_at: string | null; stale: boolean | null }>;
  cap_parameter_years: string[];
  last_successful_sync: string | null;
  recent_sync_runs: {
    job: string;
    status: string;
    rows: number;
    started_at: string | null;
    finished_at: string | null;
    error: string | null;
  }[];
  open_quality_issues: { check: string; severity: string; message: string; detected_at: string | null }[];
  active_models: {
    name: string;
    version: string;
    algorithm: string;
    trained_at: string | null;
    validation: Record<string, unknown>;
  }[];
  source_cards: SourceCard[];
  asset_coverage: Record<string, number>;
}

/** Fan-readable data-source summary card served by /data-health. */
export interface SourceCard {
  key: string;
  title: string;
  status: "fresh" | "stale" | "derived" | "incomplete" | "unavailable" | "failed";
  last_update: string | null;
  coverage: string;
  source: string;
  action: string | null;
}

export interface GeneratedCandidate {
  counterparty: { team_id: string; abbreviation: string; name: string };
  outgoing: { player_id: string; name: string; tei: number }[];
  incoming: { player_id: string; name: string; tei: number }[];
  legality_status: LegalityStatus;
  focal_utility: number;
  counterparty_utility: number;
  focal_components: Record<string, number | null>;
  rationale: string;
}

export interface SeasonTotalsPlayer {
  player_id: string;
  nba_player_id: number;
  name: string;
  position: string | null;
  team_abbr: string | null;
  gp: number;
  totals: Record<string, number | null>;
  per_game: Record<string, number | null>;
  rates: Record<string, number | null>;
}

export interface SeasonTotalsResponse {
  season: string;
  count: number;
  available: boolean;
  note: string | null;
  source: string;
  imported_at: string | null;
  players: SeasonTotalsPlayer[];
}

export interface CapOutlookContractSeason {
  season: string;
  salary: number;
  player_option: boolean;
  team_option: boolean;
}

export interface CapOutlookPlayer {
  player_id: string;
  name: string;
  seasons: CapOutlookContractSeason[];
  expiring: boolean;
  no_trade_clause: boolean;
  source_name: string | null;
  source_date: string | null;
}

export interface CapParameters {
  salary_cap: number;
  luxury_tax: number;
  first_apron: number;
  second_apron: number;
}

export interface CapOutlookUnavailable {
  team_id: string;
  available: false;
  reason: string;
  contract_provider_configured: boolean;
}

export interface CapOutlookAvailable {
  team_id: string;
  available: true;
  cap_league_year: string;
  roster_size: number;
  players_with_contracts: number;
  complete: boolean;
  seasons: { season: string; total: number; players: number }[];
  players: CapOutlookPlayer[];
  cap_parameters: CapParameters | null;
  note: string;
}

export type CapOutlookResponse = CapOutlookUnavailable | CapOutlookAvailable;
