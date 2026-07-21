export function money(value: number | null | undefined): string {
  if (value === null || value === undefined) return "unavailable";
  return `$${(value / 1_000_000).toFixed(1)}M`;
}

export function formatDate(iso: string | null | undefined): string {
  if (!iso) return "unknown";
  const d = new Date(iso);
  return d.toLocaleString("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
    hour: "numeric",
    minute: "2-digit",
  });
}

export function tei(value: number | null | undefined): string {
  if (value === null || value === undefined) return "—";
  return value >= 0 ? `+${value.toFixed(1)}` : value.toFixed(1);
}

export function pct(value: number | null | undefined, digits = 0): string {
  if (value === null || value === undefined) return "—";
  return `${(value * 100).toFixed(digits)}%`;
}

export function height(inches: number | null | undefined): string {
  if (!inches) return "—";
  return `${Math.floor(inches / 12)}'${inches % 12}"`;
}

export const LEGALITY_LABEL: Record<string, string> = {
  verified_legal: "Verified legal",
  verified_illegal: "Verified illegal",
  conditionally_valid: "Conditionally valid",
  not_evaluated: "Not evaluated",
};

export const NEED_LABEL: Record<string, string> = {
  three_point_volume: "3PT volume",
  defense_overall: "Overall defense",
  offense_overall: "Overall offense",
  defensive_rebounding: "Defensive rebounding",
  playmaking: "Playmaking",
  ball_security: "Ball security",
  rim_protection: "Rim protection",
  point_of_attack_defense: "Point-of-attack defense",
  shooting_efficiency: "Shooting efficiency",
  lineup_size: "Lineup size",
  secondary_creation: "Secondary creation",
};

export const COMPONENT_LABEL: Record<string, string> = {
  performance: "Performance",
  fit: "Roster fit",
  contract: "Contract value",
  timeline: "Timeline",
  assets: "Flexibility",
  risk: "Risk-adjusted",
};
