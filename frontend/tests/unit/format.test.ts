import { describe, expect, it } from "vitest";
import { height, money, pct, tei } from "@/lib/format";

describe("money", () => {
  it("formats millions", () => {
    expect(money(25_500_000)).toBe("$25.5M");
  });
  it("is honest about missing values", () => {
    expect(money(null)).toBe("unavailable");
    expect(money(undefined)).toBe("unavailable");
  });
});

describe("tei", () => {
  it("signs positive values", () => {
    expect(tei(2.34)).toBe("+2.3");
    expect(tei(-1.2)).toBe("-1.2");
  });
  it("dashes missing values", () => {
    expect(tei(null)).toBe("—");
  });
});

describe("pct", () => {
  it("renders share as percent", () => {
    expect(pct(0.873)).toBe("87%");
    expect(pct(null)).toBe("—");
  });
});

describe("height", () => {
  it("converts inches to feet notation", () => {
    expect(height(80)).toBe(`6'8"`);
    expect(height(null)).toBe("—");
  });
});
