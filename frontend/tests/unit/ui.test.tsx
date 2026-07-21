import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import {
  Badge,
  EmptyState,
  ErrorState,
  FreshnessBadge,
  PlayerAvatar,
  SourceLine,
  UnavailableNotice,
} from "@/components/ui";

describe("Badge", () => {
  it("renders legality statuses with distinct styling", () => {
    const { rerender } = render(<Badge status="verified_legal">legal</Badge>);
    expect(screen.getByText("legal").className).toContain("text-pass");
    rerender(<Badge status="verified_illegal">illegal</Badge>);
    expect(screen.getByText("illegal").className).toContain("text-fail");
    rerender(<Badge status="conditionally_valid">conditional</Badge>);
    expect(screen.getByText("conditional").className).toContain("text-warn");
    rerender(<Badge status="unavailable">n/a</Badge>);
    expect(screen.getByText("n/a").className).toContain("text-unavail");
  });
});

describe("FreshnessBadge", () => {
  it("shows no-data state when timestamp is missing", () => {
    render(<FreshnessBadge retrievedAt={null} />);
    expect(screen.getByText("no data")).toBeInTheDocument();
  });
  it("marks old data as stale", () => {
    const old = new Date(Date.now() - 72 * 3_600_000).toISOString();
    render(<FreshnessBadge retrievedAt={old} staleAfterHours={24} />);
    expect(screen.getByText(/stale/)).toBeInTheDocument();
  });
  it("marks recent data as fresh", () => {
    const recent = new Date(Date.now() - 3_600_000).toISOString();
    render(<FreshnessBadge retrievedAt={recent} staleAfterHours={24} />);
    expect(screen.getByText(/fresh/)).toBeInTheDocument();
  });
});

describe("UnavailableNotice", () => {
  it("labels missing data explicitly instead of hiding it", () => {
    render(<UnavailableNotice reason="Contract data unavailable from the configured provider." />);
    expect(screen.getByText("Unavailable.")).toBeInTheDocument();
    expect(screen.getByText(/Contract data unavailable/)).toBeInTheDocument();
  });
});

describe("SourceLine", () => {
  it("shows provenance and update time", () => {
    render(<SourceLine retrievedAt="2026-07-20T12:00:00Z" />);
    expect(screen.getByText(/Source: NBA.com via nba_api/)).toBeInTheDocument();
  });
});

describe("PlayerAvatar", () => {
  it("uses initials, never player photos", () => {
    render(<PlayerAvatar name="Test Player" />);
    expect(screen.getByText("TP")).toBeInTheDocument();
  });
});

describe("states", () => {
  it("renders empty and error states", () => {
    render(<EmptyState title="Nothing here" hint="Do the thing" />);
    expect(screen.getByText("Nothing here")).toBeInTheDocument();
    render(<ErrorState message="Something broke" />);
    expect(screen.getByText("Something broke")).toBeInTheDocument();
  });
});
