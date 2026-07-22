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

/** Fan-facing trade-rules language; the four-state honesty standard underneath. */
export const LEGALITY_LABEL: Record<string, string> = {
  verified_legal: "Passes rules check",
  verified_illegal: "Fails rules check",
  conditionally_valid: "Incomplete check — data missing",
  not_evaluated: "Not checked — data missing",
};

export const LEGALITY_EXPLAIN: Record<string, string> = {
  verified_legal: "Every trade rule we can verify with current data passed.",
  verified_illegal: "At least one verified NBA trade rule fails for this deal.",
  conditionally_valid:
    "All verifiable rules passed, but some checks (usually salary matching) need contract data that isn't configured.",
  not_evaluated: "Not enough data was available to run meaningful rule checks.",
};

export const VERDICT_LABEL: Record<string, string> = {
  strong: "Strong fit",
  mixed: "Mixed outcome",
  upside: "High-risk upside",
  poor: "Poor strategic fit",
  unknown: "Cannot fully evaluate",
};

/** Simple fan verdict derived from the composite score + confidence (documented). */
export function fanVerdict(utility: number | null | undefined, confidence?: string): keyof typeof VERDICT_LABEL {
  if (utility === null || utility === undefined) return "unknown";
  if (confidence === "low") return "unknown";
  if (utility >= 58) return "strong";
  if (utility >= 48) return "mixed";
  if (utility >= 40) return "upside";
  return "poor";
}

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
  performance: "On-court impact",
  fit: "Roster fit",
  contract: "Contract value",
  timeline: "Competitive window",
  assets: "Flexibility & future value",
  risk: "Downside risk",
};

export const COMPONENT_EXPLAIN: Record<string, string> = {
  performance: "Projected change in team performance after reallocating the rotation's minutes.",
  fit: "Whether incoming players address this roster's measured needs without redundancy.",
  contract: "Salary paid vs estimated on-court value (needs contract data).",
  timeline: "How player ages align with the team's competitive window and strategy.",
  assets: "Draft capital, payroll flexibility and roster optionality gained or lost.",
  risk: "Availability history and the share of simulations where the deal helps.",
};
