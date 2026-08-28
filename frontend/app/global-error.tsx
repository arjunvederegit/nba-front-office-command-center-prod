"use client";

/**
 * Last-resort boundary.
 *
 * This renders only when the root layout itself failed, which means the fonts,
 * the design tokens in globals.css, the query client and the nav are all
 * unavailable. So it renders its own document and carries its own styling
 * inline — including the palette, since `var(--chalk)` would resolve to nothing
 * here. Everything it needs is in this file; it imports no component and no
 * stylesheet, because anything it imported could be the thing that broke.
 *
 * The colors below are the literal values of the "arena at night" tokens
 * (--court-black, --arena, --hairline-soft, --chalk, --chalk-dim, --chalk-faint,
 * --illegal, --leather), duplicated here on purpose.
 */

const CSS = `
  *, *::before, *::after { box-sizing: border-box; }
  html, body { margin: 0; padding: 0; }
  .ge-btn {
    cursor: pointer;
    transition: filter 150ms ease, border-color 150ms ease;
  }
  .ge-btn:hover { filter: brightness(1.1); }
  .ge-btn:focus-visible, .ge-link:focus-visible {
    outline: 2px solid #22d3ee;
    outline-offset: 2px;
    border-radius: 3px;
  }
  .ge-link:hover { color: #e9f0fb; }
`;

const page: React.CSSProperties = {
  minHeight: "100vh",
  margin: 0,
  display: "flex",
  alignItems: "center",
  justifyContent: "center",
  padding: "2rem 1.25rem",
  background: "#060a12",
  backgroundImage:
    "radial-gradient(1200px 520px at 50% -10%, rgba(34,211,238,0.07), transparent 70%)",
  color: "#e9f0fb",
  fontFamily:
    "ui-sans-serif, system-ui, -apple-system, 'Segoe UI', Helvetica, Arial, sans-serif",
  fontSize: "15px",
  lineHeight: 1.55,
};

const card: React.CSSProperties = {
  width: "100%",
  maxWidth: "34rem",
  background: "linear-gradient(180deg, #131c30 0%, #0c1322 42%)",
  border: "1px solid #162036",
  borderRadius: "12px",
  boxShadow: "0 8px 24px -12px rgba(0,0,0,0.8)",
  padding: "1.75rem 1.5rem",
};

const eyebrow: React.CSSProperties = {
  display: "flex",
  alignItems: "center",
  gap: "0.5rem",
  fontSize: "0.6875rem",
  fontWeight: 600,
  letterSpacing: "0.18em",
  textTransform: "uppercase",
  color: "#fb7185",
};

const heading: React.CSSProperties = {
  margin: "0.625rem 0 0",
  fontSize: "1.75rem",
  fontWeight: 700,
  lineHeight: 1.05,
  letterSpacing: "0.005em",
};

const body: React.CSSProperties = {
  margin: "0.875rem 0 0",
  color: "#93a6c4",
  fontSize: "0.875rem",
};

const detailBox: React.CSSProperties = {
  margin: "1rem 0 0",
  padding: "0.75rem 0.875rem",
  border: "1px solid rgba(251,113,133,0.35)",
  borderRadius: "8px",
  background: "rgba(251,113,133,0.08)",
  fontFamily: "ui-monospace, SFMono-Regular, Menlo, Consolas, monospace",
  fontSize: "12px",
  wordBreak: "break-word",
};

const actions: React.CSSProperties = {
  display: "flex",
  flexWrap: "wrap",
  alignItems: "center",
  gap: "0.625rem",
  marginTop: "1.25rem",
};

const primaryButton: React.CSSProperties = {
  appearance: "none",
  border: "1px solid transparent",
  borderRadius: "8px",
  background: "#f97316",
  color: "#060a12",
  font: "inherit",
  fontWeight: 600,
  fontSize: "0.875rem",
  padding: "0.5rem 1rem",
};

const secondaryLink: React.CSSProperties = {
  border: "1px solid #1f2c46",
  borderRadius: "8px",
  background: "#131c30",
  color: "#e9f0fb",
  textDecoration: "none",
  fontWeight: 500,
  fontSize: "0.875rem",
  padding: "0.5rem 1rem",
  display: "inline-block",
};

const footnote: React.CSSProperties = {
  margin: "1rem 0 0",
  paddingTop: "0.75rem",
  borderTop: "1px solid #162036",
  color: "#6a7c9c",
  fontSize: "11px",
};

export default function GlobalError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  const detail = error.message?.trim();

  return (
    <html lang="en">
      <body style={page}>
        <style>{CSS}</style>
        <main style={card}>
          <div style={eyebrow}>
            {/* The ball glyph, inlined — this file imports nothing. */}
            <svg width="13" height="13" viewBox="0 0 24 24" fill="none" aria-hidden="true">
              <circle cx="12" cy="12" r="10.5" stroke="currentColor" strokeWidth="1.6" />
              <path d="M12 1.5v21M1.5 12h21" stroke="currentColor" strokeWidth="1.2" opacity="0.75" />
              <path
                d="M4.5 4.5c4 3.2 4 12 0 15M19.5 4.5c-4 3.2-4 12 0 15"
                stroke="currentColor"
                strokeWidth="1.2"
                opacity="0.75"
              />
            </svg>
            Application error
          </div>

          <h1 style={heading}>Pivot could not start this page</h1>

          <p style={body}>
            The failure happened outside any single view, so the interface around it —
            navigation, fonts, saved state — is not available either. This screen is what is
            left, and it is deliberately plain. No data was changed.
          </p>

          {detail && (
            <div style={detailBox}>
              <div
                style={{
                  fontFamily: "inherit",
                  fontSize: "10px",
                  letterSpacing: "0.18em",
                  textTransform: "uppercase",
                  color: "#fb7185",
                  marginBottom: "0.375rem",
                }}
              >
                What failed
              </div>
              {detail}
            </div>
          )}

          <div style={actions}>
            <button type="button" className="ge-btn" style={primaryButton} onClick={() => reset()}>
              Try again
            </button>
            {/* eslint-disable-next-line @next/next/no-html-link-for-pages -- a full document load is the point here: the router and root layout this boundary replaced are the things that failed, so a client-side transition would restore the broken state. */}
            <a href="/" className="ge-btn ge-link" style={secondaryLink}>
              Reload Command Center
            </a>
          </div>

          <p style={footnote}>
            {error.digest ? (
              <>
                <span style={{ letterSpacing: "0.1em", textTransform: "uppercase" }}>digest</span>{" "}
                <span style={{ color: "#93a6c4" }}>{error.digest}</span> · quote this when
                reporting the failure. If reloading does not clear it, the frontend build or the
                API it depends on is the place to look.
              </>
            ) : (
              <>
                If reloading does not clear this, the frontend build or the API it depends on is
                the place to look.
              </>
            )}
          </p>
        </main>
      </body>
    </html>
  );
}
