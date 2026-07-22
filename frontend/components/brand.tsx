/**
 * RosterLab brand mark: a basketball seam arc crossed by a rising chart line,
 * set in a roundel. Original geometry — no NBA marks, no affiliation implied.
 */
export function BrandMark({ size = 30 }: { size?: number }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 48 48"
      role="img"
      aria-label="RosterLab logo"
      className="shrink-0"
    >
      <defs>
        <linearGradient id="rl-court" x1="0" y1="1" x2="1" y2="0">
          <stop offset="0" stopColor="#f97316" />
          <stop offset="1" stopColor="#fdba74" />
        </linearGradient>
      </defs>
      <circle cx="24" cy="24" r="22" fill="none" stroke="url(#rl-court)" strokeWidth="2.5" />
      {/* basketball seam arcs */}
      <path
        d="M6 30 Q 24 18 42 30"
        fill="none"
        stroke="url(#rl-court)"
        strokeWidth="2"
        strokeLinecap="round"
        opacity="0.55"
      />
      <path
        d="M10 14 Q 24 26 38 14"
        fill="none"
        stroke="url(#rl-court)"
        strokeWidth="2"
        strokeLinecap="round"
        opacity="0.55"
      />
      {/* rising chart line with shot-dot */}
      <path
        d="M12 34 L 20 27 L 27 30 L 36 17"
        fill="none"
        stroke="#f8fafc"
        strokeWidth="2.6"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <circle cx="36" cy="17" r="3" fill="#f97316" stroke="#f8fafc" strokeWidth="1.4" />
    </svg>
  );
}

export function BrandWordmark({ compact = false }: { compact?: boolean }) {
  return (
    <span className="flex items-baseline gap-2">
      <span className="text-lg font-bold tracking-tight text-foreground">
        Roster<span className="text-brand">Lab</span>
      </span>
      {!compact && (
        <span className="hidden text-[11px] text-muted lg:inline">NBA Front Office Simulator</span>
      )}
    </span>
  );
}

/** Lightweight half-court line art for hero/empty states (pure SVG, no rasters). */
export function CourtLines({ className }: { className?: string }) {
  return (
    <svg
      viewBox="0 0 400 200"
      className={className}
      aria-hidden
      preserveAspectRatio="xMidYMax slice"
    >
      <g fill="none" stroke="currentColor" strokeWidth="1.5">
        <line x1="0" y1="198" x2="400" y2="198" />
        <path d="M 40 198 A 160 160 0 0 1 360 198" opacity="0.5" />
        <rect x="140" y="118" width="120" height="80" opacity="0.6" />
        <path d="M 140 118 A 60 60 0 0 1 260 118" opacity="0.6" transform="rotate(180 200 118)" />
        <circle cx="200" cy="198" r="24" opacity="0.7" />
      </g>
    </svg>
  );
}
