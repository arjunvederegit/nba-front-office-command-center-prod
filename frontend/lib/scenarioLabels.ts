/**
 * Display identities for a list of saved scenarios.
 *
 * `name` is not an identity. Team Outlook generates "BOS — Contend now" every time the
 * button is pressed, so a user who explores a few weightings ends up with a dropdown of
 * rows that read exactly alike and pick differently.
 *
 * R1 added the team, the strategy and the save **date**, which is correct in direction and
 * insufficient in resolution: on the dev database sixteen scenarios share one afternoon,
 * so sixteen options rendered as the same string. R7 makes uniqueness a **property of the
 * output** rather than a hope about the input — labels are built for the whole list at
 * once, and detail is added only to the entries that actually collide:
 *
 *   1. team, name and strategy;
 *   2. ...plus the save date, for entries that still match;
 *   3. ...plus the time, for entries saved on the same day;
 *   4. ...plus an ordinal, for entries saved in the same minute.
 *
 * Escalating only on collision keeps the common case short. A user with three scenarios
 * saved on different days sees three dates and no timestamps.
 */

export interface LabelledScenario {
  id: string;
  name: string;
  strategy: string;
  created_at: string;
  focal_team?: { abbreviation?: string | null } | null;
}

function base(scenario: LabelledScenario): string {
  const team = scenario.focal_team?.abbreviation;
  const prefix = team && !scenario.name.includes(team) ? `${team} — ` : "";
  return `${prefix}${scenario.name} (${scenario.strategy.replaceAll("_", " ")})`;
}

function stamp(scenario: LabelledScenario, withTime: boolean): string {
  const saved = new Date(scenario.created_at);
  if (Number.isNaN(saved.getTime())) return "";
  const date = saved.toLocaleDateString("en-US", { month: "short", day: "numeric" });
  if (!withTime) return ` · ${date}`;
  const time = saved.toLocaleTimeString("en-US", { hour: "numeric", minute: "2-digit" });
  return ` · ${date}, ${time}`;
}

/** One label per scenario, in the input order, guaranteed distinct. */
export function scenarioOptionLabels(scenarios: LabelledScenario[]): string[] {
  const labels = scenarios.map(base);
  for (const withTime of [false, true]) {
    const counts = new Map<string, number>();
    for (const label of labels) counts.set(label, (counts.get(label) ?? 0) + 1);
    if (![...counts.values()].some((n) => n > 1)) return labels;
    scenarios.forEach((scenario, index) => {
      if ((counts.get(labels[index]) ?? 0) > 1) {
        labels[index] = base(scenario) + stamp(scenario, withTime);
      }
    });
  }
  // Same team, same name, same strategy, same minute. An ordinal is the only thing left
  // that distinguishes them, and an ambiguous option is worse than an inelegant one.
  const seen = new Map<string, number>();
  const total = new Map<string, number>();
  for (const label of labels) total.set(label, (total.get(label) ?? 0) + 1);
  return labels.map((label) => {
    if ((total.get(label) ?? 0) <= 1) return label;
    const n = (seen.get(label) ?? 0) + 1;
    seen.set(label, n);
    return `${label} #${n}`;
  });
}
