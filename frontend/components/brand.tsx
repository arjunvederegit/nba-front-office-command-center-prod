/**
 * Pivot mark: a ball's seams where one seam has become a rising line of data, turning
 * about a fixed point — the pivot foot. Orange holds the ball, cyan holds the analysis —
 * the same division of labor the whole palette uses.
 *
 * The geometry is inherited from the RosterLab mark and deliberately not redrawn: the
 * visual language developed through R1–R7 is the part of this product that was already
 * right. What changed is where the data line turns, and the anchored foot it turns on.
 */

export const PRODUCT_NAME = "Pivot";
export const PRODUCT_TAGLINE = "Basketball Intelligence for Better Decisions";

export function BrandMark({ size = 30 }: { size?: number }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 40 40"
      role="img"
      aria-label={PRODUCT_NAME}
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
      {/* the seam that became data, turning about the planted foot */}
      <path
        d="M7 29l7-9 6 5 13-15"
        stroke="var(--signal)"
        strokeWidth="2.6"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      {/* the pivot point: the foot the turn happens on */}
      <circle cx="14" cy="20" r="2.6" fill="var(--signal)" />
      <circle cx="33" cy="10" r="3" fill="var(--signal)" />
    </svg>
  );
}

export function BrandWordmark({ compact = false }: { compact?: boolean }) {
  return (
    <span className="flex min-w-0 items-baseline gap-2">
      <span className="display text-[1.35rem] leading-none tracking-tight text-foreground">
        PIV<span className="text-brand">O</span>T
      </span>
      {!compact && (
        <span className="eyebrow hidden whitespace-nowrap text-[0.6rem] text-faint xl:inline">
          {PRODUCT_TAGLINE}
        </span>
      )}
    </span>
  );
}
