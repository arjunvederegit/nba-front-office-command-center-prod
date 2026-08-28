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
  it("gives each of the four legality states its own color", () => {
    const { rerender } = render(<Badge status="verified_legal">legal</Badge>);
    expect(screen.getByText("legal").className).toContain("text-legal");
    rerender(<Badge status="verified_illegal">illegal</Badge>);
    expect(screen.getByText("illegal").className).toContain("text-illegal");
    rerender(<Badge status="conditionally_valid">conditional</Badge>);
    expect(screen.getByText("conditional").className).toContain("text-conditional");
    rerender(<Badge status="unavailable">n/a</Badge>);
    expect(screen.getByText("n/a").className).toContain("text-unavail");
  });

  // Color alone must never carry status — each state also renders a glyph.
  it("pairs every status with a non-color glyph", () => {
    const glyphs: Record<string, string> = {
      verified_legal: "✓",
      verified_illegal: "✕",
      conditionally_valid: "~",
      unavailable: "—",
    };
    for (const [status, glyph] of Object.entries(glyphs)) {
      const { unmount } = render(<Badge status={status}>state</Badge>);
      expect(screen.getByText("state").textContent).toContain(glyph);
      unmount();
    }
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
    expect(screen.getByText("Not available.")).toBeInTheDocument();
    expect(screen.getByText(/Contract data unavailable/)).toBeInTheDocument();
  });
});

describe("SourceLine", () => {
  it("shows provenance and update time", () => {
    render(<SourceLine source="NBA.com via nba_api" retrievedAt="2026-07-20T12:00:00Z" />);
    expect(screen.getByText(/Source: NBA.com via nba_api/)).toBeInTheDocument();
  });

  it("renders whatever provenance it is given, and asserts nothing on its own", () => {
    // The prop used to default to "NBA.com via nba_api", so a rail rendered over
    // synthetic or user-imported data still claimed NBA.com. There is no default now;
    // this pins that the component is a renderer, not a source of truth.
    // Scoped to this render's own container: the suite does not auto-clean between
    // cases, so a document-wide query would still see the rail rendered above.
    const { container } = render(
      <SourceLine
        source="Synthetic demo data (not real NBA data)"
        retrievedAt="2026-07-20T12:00:00Z"
      />,
    );
    expect(container.textContent).toContain("Synthetic demo data");
    expect(container.textContent).not.toContain("NBA.com");
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
