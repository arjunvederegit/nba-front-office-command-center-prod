import { describe, expect, it } from "vitest";
import { scenarioOptionLabels } from "@/lib/scenarioLabels";
import type { LabelledScenario } from "@/lib/scenarioLabels";

function scenario(over: Partial<LabelledScenario> = {}): LabelledScenario {
  return {
    id: "s1",
    name: "Contend now",
    strategy: "contend",
    created_at: "2026-07-28T06:21:00Z",
    focal_team: { abbreviation: "BOS" },
    ...over,
  };
}

describe("scenarioOptionLabels", () => {
  it("keeps the short form when nothing collides", () => {
    const labels = scenarioOptionLabels([
      scenario({ id: "a", name: "Contend now" }),
      scenario({ id: "b", name: "Retool" }),
    ]);
    expect(labels).toEqual(["BOS — Contend now (contend)", "BOS — Retool (contend)"]);
  });

  it("adds a date only to the entries that collide", () => {
    const labels = scenarioOptionLabels([
      scenario({ id: "a", created_at: "2026-07-28T06:21:00Z" }),
      scenario({ id: "b", created_at: "2026-07-22T03:50:00Z" }),
      scenario({ id: "c", name: "Retool" }),
    ]);
    expect(labels[2]).toBe("BOS — Retool (contend)");
    expect(labels[0]).not.toBe(labels[1]);
    expect(new Set(labels).size).toBe(3);
  });

  it("escalates to the time for entries saved on the same day", () => {
    // The R7 defect: sixteen scenarios shared one afternoon and rendered as one string.
    const labels = scenarioOptionLabels([
      scenario({ id: "a", created_at: "2026-07-28T06:21:00Z" }),
      scenario({ id: "b", created_at: "2026-07-28T07:46:00Z" }),
      scenario({ id: "c", created_at: "2026-07-28T07:21:00Z" }),
    ]);
    expect(new Set(labels).size).toBe(3);
    for (const label of labels) expect(label).toMatch(/Jul 28, /);
  });

  it("falls back to an ordinal when even the minute is shared", () => {
    const same = "2026-07-28T07:46:04Z";
    const labels = scenarioOptionLabels([
      scenario({ id: "a", created_at: same }),
      scenario({ id: "b", created_at: same }),
    ]);
    expect(new Set(labels).size).toBe(2);
    expect(labels[0]).toMatch(/#1$/);
    expect(labels[1]).toMatch(/#2$/);
  });

  it("never returns two identical labels, whatever the input", () => {
    // The property the whole module exists for. An ambiguous option picks the wrong
    // weights and looks like it picked the right ones.
    const many = Array.from({ length: 16 }, (_, i) =>
      scenario({ id: `s${i}`, created_at: "2026-07-28T07:46:04Z" }),
    );
    expect(new Set(scenarioOptionLabels(many)).size).toBe(16);
  });

  it("does not repeat a team already written into the name", () => {
    const [label] = scenarioOptionLabels([scenario({ name: "BOS — Contend now" })]);
    expect(label).toBe("BOS — Contend now (contend)");
  });

  it("survives a scenario with no team and an unparseable timestamp", () => {
    const labels = scenarioOptionLabels([
      scenario({ id: "a", focal_team: null, created_at: "not-a-date" }),
      scenario({ id: "b", focal_team: null, created_at: "not-a-date" }),
    ]);
    expect(new Set(labels).size).toBe(2);
    expect(labels[0]).not.toContain("undefined");
    expect(labels[0]).not.toContain("NaN");
  });

  it("returns nothing for an empty list rather than throwing", () => {
    expect(scenarioOptionLabels([])).toEqual([]);
  });
});
