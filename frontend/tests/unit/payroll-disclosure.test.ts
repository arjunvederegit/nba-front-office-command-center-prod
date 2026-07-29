/**
 * R2c — how a payroll may be rendered when contract coverage is partial.
 *
 * The failure this guards against is not a crash. It is a screen that shows
 * `$188.2M` for a team whose real payroll is higher, with nothing on it to say so —
 * a number that is wrong in a direction the reader cannot detect. The rule is that a
 * partial figure is a *floor*: it carries `≥`, it carries its coverage, and the coverage
 * is not optional decoration a caller can drop.
 */
import { describe, expect, it } from "vitest";
import { payrollDisclosure } from "@/lib/format";

const coverage = (known: number, total: number) => ({
  players_known: known,
  players_total: total,
});

describe("payrollDisclosure", () => {
  it("renders a complete payroll as a plain number", () => {
    const shown = payrollDisclosure(216_000_000, 216_000_000, coverage(18, 18));
    expect(shown.kind).toBe("verified");
    expect(shown.value).toBe("$216.0M");
    expect(shown.value).not.toContain("≥");
  });

  it("marks a partial payroll as a floor, never as the payroll", () => {
    const shown = payrollDisclosure(null, 188_188_971, coverage(12, 18));
    expect(shown.kind).toBe("floor");
    expect(shown.value).toBe("≥ $188.2M");
  });

  it("always states the coverage beside a floor", () => {
    const shown = payrollDisclosure(null, 188_188_971, coverage(12, 18));
    expect(shown.note).toContain("12 of 18");
    expect(shown.note).toContain("6 unknown");
  });

  it("never invents a number when nothing is on file", () => {
    const shown = payrollDisclosure(null, null, coverage(0, 18));
    expect(shown.kind).toBe("unavailable");
    expect(shown.value).toBe("—");
  });

  it("treats zero priced contracts as nothing to disclose, not as a $0 payroll", () => {
    // `payroll_known` is 0 for a team with no contracts at all. Rendering "$0.0M" would
    // be a fabricated payroll for a roster that simply has no data.
    const shown = payrollDisclosure(null, 0, coverage(0, 18));
    expect(shown.kind).toBe("unavailable");
    expect(shown.value).toBe("—");
  });

  it("does not treat an absent coverage object as complete", () => {
    const shown = payrollDisclosure(null, 188_000_000, null);
    expect(shown.kind).toBe("unavailable");
  });

  it("is monotone: a floor is never rendered above the verified figure it replaces", () => {
    // Same team, before and after the missing contracts arrive. The floor must read
    // lower than the truth, which is the only direction a lower bound may err.
    const floor = payrollDisclosure(null, 188_000_000, coverage(12, 18));
    const truth = payrollDisclosure(204_000_000, 204_000_000, coverage(18, 18));
    const dollars = (v: string) => Number(v.replace(/[^0-9.]/g, ""));
    expect(dollars(floor.value)).toBeLessThan(dollars(truth.value));
  });
});
