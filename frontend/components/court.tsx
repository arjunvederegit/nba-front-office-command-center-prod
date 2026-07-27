/**
 * Court geometry as product furniture.
 *
 * Every shape here is real basketball geometry used for a functional purpose —
 * the half-court frames the hero, the key holds a verdict, the lane carries
 * assets between teams. None of it is decorative filler.
 */

/** Half-court in true proportions (50ft wide × 47ft deep), drawn as line art. */
export function HalfCourt({ className }: { className?: string }) {
  return (
    <svg
      viewBox="0 0 500 470"
      className={className}
      aria-hidden
      fill="none"
      preserveAspectRatio="xMidYMax meet"
    >
      <g stroke="currentColor" strokeWidth="2" vectorEffect="non-scaling-stroke">
        {/* sidelines + baseline */}
        <rect x="1" y="1" width="498" height="468" opacity="0.35" />
        {/* the key (16ft lane) + free-throw circle */}
        <rect x="170" y="310" width="160" height="159" opacity="0.6" />
        <circle cx="250" cy="310" r="60" opacity="0.6" />
        {/* restricted arc + rim */}
        <path d="M210 449a40 40 0 0 0 80 0" opacity="0.5" />
        <circle cx="250" cy="440" r="9" opacity="0.75" />
        <line x1="220" y1="455" x2="280" y2="455" opacity="0.75" />
        {/* three-point line: corners then arc */}
        <path d="M30 469V330" opacity="0.6" />
        <path d="M470 469V330" opacity="0.6" />
        <path d="M30 330a222 222 0 0 0 440 0" opacity="0.6" />
        {/* half-court arc */}
        <path d="M130 1a120 120 0 0 0 240 0" opacity="0.3" />
      </g>
    </svg>
  );
}

/**
 * The free-throw key, used as a container shape for headline verdicts.
 * Renders as a trapezoid-topped block with the semicircle implied by a border.
 */
export function KeyFrame({
  children,
  accent = "var(--signal)",
  className,
}: {
  children: React.ReactNode;
  accent?: string;
  className?: string;
}) {
  return (
    <div className={`relative ${className ?? ""}`}>
      <span
        aria-hidden
        className="absolute inset-x-0 -top-px mx-auto h-px w-2/3"
        style={{ background: `linear-gradient(90deg, transparent, ${accent}, transparent)` }}
      />
      <span
        aria-hidden
        className="absolute -top-2.5 left-1/2 h-5 w-5 -translate-x-1/2 rounded-full border"
        style={{ borderColor: accent, background: "var(--arena)" }}
      />
      {children}
    </div>
  );
}

/**
 * The transaction lane: the strip between two team workspaces that carries
 * assets. Direction is encoded by arrow heads AND by label text, never by
 * color alone.
 */
export function TransactionLane({
  leftColor = "var(--signal)",
  rightColor = "var(--leather)",
  active = false,
  orientation = "horizontal",
  className,
}: {
  leftColor?: string;
  rightColor?: string;
  active?: boolean;
  orientation?: "horizontal" | "vertical";
  className?: string;
}) {
  if (orientation === "vertical") {
    return (
      <svg viewBox="0 0 40 120" className={className} aria-hidden fill="none">
        <line x1="20" y1="0" x2="20" y2="120" stroke="var(--hairline)" strokeWidth="1" />
        <circle cx="20" cy="60" r="13" stroke="var(--hairline)" strokeWidth="1" fill="var(--arena)" />
        <circle cx="20" cy="60" r="3" fill={active ? "var(--signal)" : "var(--hairline)"} />
        <path d="M20 16v14m0 0-5-5m5 5 5-5" stroke={rightColor} strokeWidth="2" strokeLinecap="round" />
        <path d="M20 104V90m0 0-5 5m5-5 5 5" stroke={leftColor} strokeWidth="2" strokeLinecap="round" />
      </svg>
    );
  }
  return (
    <svg viewBox="0 0 120 44" className={className} aria-hidden fill="none">
      <line x1="0" y1="22" x2="120" y2="22" stroke="var(--hairline)" strokeWidth="1" />
      <circle cx="60" cy="22" r="14" stroke="var(--hairline)" strokeWidth="1" fill="var(--arena)" />
      <circle cx="60" cy="22" r="3.5" fill={active ? "var(--signal)" : "var(--hairline)"} />
      {/* rightward path */}
      <path
        d="M78 14h22m0 0-6-5m6 5-6 5"
        stroke={rightColor}
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      {/* leftward path */}
      <path
        d="M42 30H20m0 0 6-5m-6 5 6 5"
        stroke={leftColor}
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

/** Basketball seams — used at small sizes as the "ball" glyph in the brand system. */
export function BallGlyph({ size = 16, className }: { size?: number; className?: string }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" className={className} aria-hidden fill="none">
      <circle cx="12" cy="12" r="10.5" stroke="currentColor" strokeWidth="1.6" />
      <path d="M12 1.5v21M1.5 12h21" stroke="currentColor" strokeWidth="1.2" opacity="0.75" />
      <path
        d="M4.5 4.5c4 3.2 4 12 0 15M19.5 4.5c-4 3.2-4 12 0 15"
        stroke="currentColor"
        strokeWidth="1.2"
        opacity="0.75"
      />
    </svg>
  );
}

/** Shot-chart scatter used only where "where the value comes from" is the point. */
export function ShotChartMotif({ className }: { className?: string }) {
  const dots = [
    [250, 430, 5], [190, 415, 4], [310, 418, 4], [140, 380, 3], [360, 384, 3],
    [250, 350, 4], [205, 330, 3], [295, 332, 3], [60, 430, 3], [440, 430, 3],
    [120, 300, 2.5], [380, 302, 2.5], [250, 268, 3], [170, 258, 2], [330, 260, 2],
  ];
  return (
    <svg viewBox="0 0 500 470" className={className} aria-hidden fill="none">
      {dots.map(([x, y, r], i) => (
        <circle
          key={i}
          cx={x}
          cy={y}
          r={r}
          fill="currentColor"
          opacity={0.15 + (i % 5) * 0.12}
        />
      ))}
    </svg>
  );
}
