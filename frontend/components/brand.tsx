/**
 * RosterLab mark: a ball's seams where one seam has become a rising line of
 * data. Orange holds the ball, cyan holds the analysis — the same division of
 * labor the whole palette uses.
 */
export function BrandMark({ size = 30 }: { size?: number }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 40 40"
      role="img"
      aria-label="RosterLab"
      className="shrink-0"
      fill="none"
    >
      <circle cx="20" cy="20" r="18" stroke="var(--leather)" strokeWidth="2" />
      {/* seams */}
      <path d="M20 2v13M20 25v13" stroke="var(--leather)" strokeWidth="1.5" opacity="0.55" />
      <path
        d="M6.5 7.5c4.2 4.4 4.2 20.6 0 25M33.5 7.5c-4.2 4.4-4.2 20.6 0 25"
        stroke="var(--leather)"
        strokeWidth="1.5"
        opacity="0.55"
      />
      {/* the seam that became data */}
      <path
        d="M6 26l7.5-6.5 6 3L34 10"
        stroke="var(--signal)"
        strokeWidth="2.6"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <circle cx="34" cy="10" r="3.2" fill="var(--signal)" />
    </svg>
  );
}

export function BrandWordmark({ compact = false }: { compact?: boolean }) {
  return (
    <span className="flex min-w-0 items-baseline gap-2">
      <span className="display text-[1.35rem] leading-none tracking-tight text-foreground">
        ROSTER<span className="text-brand">LAB</span>
      </span>
      {!compact && (
        <span className="eyebrow hidden whitespace-nowrap text-[0.6rem] text-faint xl:inline">
          Basketball Decision Intelligence
        </span>
      )}
    </span>
  );
}
