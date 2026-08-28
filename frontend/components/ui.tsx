"use client";

/**
 * Pivot interface primitives.
 *
 * Two rules run through everything here:
 *  - Status is never carried by color alone — every status badge also carries a
 *    glyph and a word.
 *  - Panels are lit from their top edge rather than boxed on four sides, so a
 *    dense page doesn't read as a grid of identical rectangles.
 */

import clsx from "clsx";
import Link from "next/link";
import { useState } from "react";
import { formatDate } from "@/lib/format";

/* ------------------------------------------------------------------ surface */

export function Panel({
  children,
  className,
  title,
  subtitle,
  actions,
  accent,
  as: Tag = "section",
  padded = true,
}: {
  children?: React.ReactNode;
  className?: string;
  title?: React.ReactNode;
  subtitle?: React.ReactNode;
  actions?: React.ReactNode;
  /** Top-edge light color — pass a team color inside team context. */
  accent?: string;
  as?: "section" | "div" | "article" | "aside";
  padded?: boolean;
}) {
  return (
    <Tag
      className={clsx("panel", className)}
      style={accent ? ({ "--edge": accent } as React.CSSProperties) : undefined}
    >
      {(title || actions) && (
        <header className="flex flex-wrap items-start justify-between gap-x-4 gap-y-2 border-b border-hairline px-4 py-3">
          <div className="min-w-0">
            {title && <h2 className="title-md truncate text-foreground">{title}</h2>}
            {subtitle && <div className="mt-1 text-xs leading-relaxed text-muted">{subtitle}</div>}
          </div>
          {actions && <div className="flex shrink-0 items-center gap-2">{actions}</div>}
        </header>
      )}
      <div className={padded ? "p-4" : undefined}>{children}</div>
    </Tag>
  );
}

/** Kept for source compatibility with pages written before the redesign. */
export const Card = Panel;

/* ------------------------------------------------------------------- header */

export function PageHeader({
  eyebrow,
  title,
  lede,
  actions,
  meta,
  accent,
}: {
  eyebrow?: React.ReactNode;
  title: React.ReactNode;
  lede?: React.ReactNode;
  actions?: React.ReactNode;
  meta?: React.ReactNode;
  accent?: string;
}) {
  return (
    <header className="mb-5">
      <div
        className="h-px w-full"
        style={{
          background: `linear-gradient(90deg, ${accent ?? "var(--signal)"}, transparent 60%)`,
        }}
      />
      <div className="flex flex-wrap items-end justify-between gap-x-6 gap-y-3 pt-3">
        <div className="min-w-0">
          {eyebrow && <div className="eyebrow mb-1.5">{eyebrow}</div>}
          <h1 className="title-lg whitespace-nowrap text-foreground">{title}</h1>
          {lede && <p className="mt-1.5 max-w-2xl text-sm leading-relaxed text-muted">{lede}</p>}
        </div>
        {actions && <div className="flex shrink-0 flex-wrap items-center gap-2">{actions}</div>}
      </div>
      {meta && <div className="mt-2.5 flex flex-wrap items-center gap-2">{meta}</div>}
    </header>
  );
}

/* ------------------------------------------------------------------ actions */

const BUTTON_VARIANTS: Record<string, string> = {
  primary:
    "bg-brand text-court font-semibold hover:brightness-110 active:brightness-95 border border-transparent",
  signal:
    "bg-signal text-court font-semibold hover:brightness-110 active:brightness-95 border border-transparent",
  secondary: "border border-line bg-panel2 text-foreground hover:border-signal/50 hover:bg-panel3",
  ghost: "border border-transparent text-muted hover:bg-panel2 hover:text-foreground",
  danger: "border border-illegal/40 bg-illegal/10 text-illegal hover:bg-illegal/20",
};

type ButtonProps = {
  variant?: keyof typeof BUTTON_VARIANTS;
  size?: "sm" | "md";
  className?: string;
  children: React.ReactNode;
};

function buttonClass(variant: string, size: string, className?: string) {
  return clsx(
    "inline-flex items-center justify-center gap-1.5 whitespace-nowrap rounded-md transition-[filter,background-color,border-color] duration-150 disabled:cursor-not-allowed disabled:opacity-40",
    size === "sm" ? "px-3 py-1.5 text-[13px]" : "px-4 py-2 text-sm",
    BUTTON_VARIANTS[variant] ?? BUTTON_VARIANTS.secondary,
    className,
  );
}

export function Button({
  variant = "secondary",
  size = "md",
  className,
  children,
  ...rest
}: ButtonProps & React.ButtonHTMLAttributes<HTMLButtonElement>) {
  return (
    <button className={buttonClass(variant, size, className)} {...rest}>
      {children}
    </button>
  );
}

export function ButtonLink({
  variant = "secondary",
  size = "md",
  className,
  children,
  href,
  ...rest
}: ButtonProps & { href: string } & Omit<
    React.AnchorHTMLAttributes<HTMLAnchorElement>,
    "href" | "className" | "children"
  >) {
  return (
    <Link href={href} className={buttonClass(variant, size, className)} {...rest}>
      {children}
    </Link>
  );
}

/* ------------------------------------------------------------------- status */

interface StatusStyle {
  className: string;
  glyph: string;
}

const STATUS: Record<string, StatusStyle> = {
  pass: { className: "border-legal/40 bg-legal/12 text-legal", glyph: "✓" },
  verified_legal: { className: "border-legal/40 bg-legal/12 text-legal", glyph: "✓" },
  succeeded: { className: "border-legal/40 bg-legal/12 text-legal", glyph: "✓" },
  fresh: { className: "border-legal/40 bg-legal/12 text-legal", glyph: "✓" },
  fail: { className: "border-illegal/40 bg-illegal/12 text-illegal", glyph: "✕" },
  verified_illegal: { className: "border-illegal/40 bg-illegal/12 text-illegal", glyph: "✕" },
  failed: { className: "border-illegal/40 bg-illegal/12 text-illegal", glyph: "✕" },
  error: { className: "border-illegal/40 bg-illegal/12 text-illegal", glyph: "✕" },
  warning: { className: "border-conditional/40 bg-conditional/12 text-conditional", glyph: "!" },
  conditionally_valid: {
    className: "border-conditional/40 bg-conditional/12 text-conditional",
    glyph: "~",
  },
  stale: { className: "border-conditional/40 bg-conditional/12 text-conditional", glyph: "!" },
  incomplete: { className: "border-conditional/40 bg-conditional/12 text-conditional", glyph: "~" },
  unavailable: { className: "border-unavail/40 bg-unavail/12 text-unavail", glyph: "—" },
  not_evaluated: { className: "border-unavail/40 bg-unavail/12 text-unavail", glyph: "—" },
  derived: { className: "border-signal/40 bg-signal/12 text-signal", glyph: "≈" },
  info: { className: "border-signal/40 bg-signal/12 text-signal", glyph: "•" },
  running: { className: "border-signal/40 bg-signal/12 text-signal", glyph: "•" },
};

export function Badge({
  status,
  children,
  className,
  glyph = true,
}: {
  status?: string;
  children: React.ReactNode;
  className?: string;
  glyph?: boolean;
}) {
  const style = STATUS[status ?? "info"] ?? STATUS.info;
  return (
    <span
      className={clsx(
        "inline-flex items-center gap-1 whitespace-nowrap rounded-full border px-2 py-0.5 text-[11px] font-medium leading-tight",
        style.className,
        className,
      )}
    >
      {glyph && (
        <span aria-hidden className="font-mono text-[10px] leading-none">
          {style.glyph}
        </span>
      )}
      {children}
    </span>
  );
}

/* --------------------------------------------------------------- scoreboard */

/** A single scoreboard-style metric: quiet label, loud number, optional note. */
export function StatBlock({
  label,
  value,
  note,
  accent,
  align = "left",
  size = "md",
  title,
}: {
  label: React.ReactNode;
  value: React.ReactNode;
  note?: React.ReactNode;
  accent?: string;
  align?: "left" | "center" | "right";
  size?: "sm" | "md" | "lg";
  title?: string;
}) {
  return (
    <div
      className={clsx(
        align === "center" && "text-center",
        align === "right" && "text-right",
        "min-w-0",
      )}
      title={title}
    >
      <div className="eyebrow truncate text-[0.625rem]">{label}</div>
      <div
        className={clsx(
          "numeral mt-1 leading-none",
          size === "sm" && "text-xl",
          size === "md" && "text-[1.75rem]",
          size === "lg" && "text-[2.5rem]",
        )}
        style={accent ? { color: accent } : undefined}
      >
        {value}
      </div>
      {note && <div className="mt-1 text-[11px] leading-snug text-muted">{note}</div>}
    </div>
  );
}

/** Provenance rail — the structural device that carries the honesty standard. */
export function SourceRail({
  source = "NBA.com via nba_api",
  retrievedAt,
  extra,
  className,
}: {
  source?: string;
  retrievedAt?: string | null;
  extra?: React.ReactNode;
  className?: string;
}) {
  return (
    <div
      className={clsx(
        "mt-3 flex flex-wrap items-center gap-x-2 gap-y-1 border-t border-hairline pt-2 text-[11px] text-faint",
        className,
      )}
    >
      <span className="font-mono text-[10px] uppercase tracking-wider">source</span>
      <span className="text-muted">{source}</span>
      {retrievedAt !== undefined && (
        <>
          <span aria-hidden>·</span>
          <span>updated {formatDate(retrievedAt)}</span>
        </>
      )}
      {extra}
    </div>
  );
}

export function SourceLine({
  source = "NBA.com via nba_api",
  retrievedAt,
  className,
}: {
  source?: string;
  retrievedAt?: string | null;
  className?: string;
}) {
  return (
    <p className={clsx("text-[11px] text-faint", className)}>
      Source: {source} · Updated {formatDate(retrievedAt)}
    </p>
  );
}

export function FreshnessBadge({
  retrievedAt,
  staleAfterHours = 24,
}: {
  retrievedAt: string | null | undefined;
  staleAfterHours?: number;
}) {
  const [now] = useState(() => Date.now());
  if (!retrievedAt) return <Badge status="unavailable">no data</Badge>;
  const ageHours = (now - new Date(retrievedAt).getTime()) / 3_600_000;
  if (ageHours > staleAfterHours)
    return <Badge status="stale">stale · {Math.round(ageHours)}h old</Badge>;
  return <Badge status="pass">fresh · {formatDate(retrievedAt)}</Badge>;
}

/* ---------------------------------------------------------------- feedback */

export function Spinner({ label = "Loading…" }: { label?: string }) {
  return (
    <div className="flex items-center gap-2 py-8 text-sm text-muted" role="status">
      <span className="h-4 w-4 animate-spin rounded-full border-2 border-line border-t-signal" />
      {label}
    </div>
  );
}

export function Skeleton({ className }: { className?: string }) {
  return <div className={clsx("skeleton", className)} aria-hidden />;
}

export function SkeletonRows({ rows = 5, height = "h-11" }: { rows?: number; height?: string }) {
  return (
    <div className="space-y-2" role="status" aria-label="Loading">
      {Array.from({ length: rows }).map((_, i) => (
        <Skeleton key={i} className={height} />
      ))}
    </div>
  );
}

export function ErrorState({ message, action }: { message: string; action?: React.ReactNode }) {
  return (
    <div className="rounded-lg border border-illegal/40 bg-illegal/8 px-4 py-3">
      <p className="text-sm text-illegal">{message}</p>
      {action && <div className="mt-2">{action}</div>}
    </div>
  );
}

/** An empty screen is an invitation to act, so it always offers the next step. */
export function EmptyState({
  title,
  hint,
  action,
  className,
}: {
  title: string;
  hint?: React.ReactNode;
  action?: React.ReactNode;
  className?: string;
}) {
  return (
    <div
      className={clsx(
        "court-grid relative overflow-hidden rounded-lg border border-dashed border-line px-6 py-10 text-center",
        className,
      )}
    >
      <p className="title-md text-foreground">{title}</p>
      {hint && <p className="mx-auto mt-1.5 max-w-md text-sm leading-relaxed text-muted">{hint}</p>}
      {action && <div className="mt-4 flex justify-center gap-2">{action}</div>}
    </div>
  );
}

export function UnavailableNotice({
  reason,
  steps,
}: {
  reason: React.ReactNode;
  steps?: React.ReactNode;
}) {
  return (
    <div className="rounded-lg border border-unavail/35 bg-unavail/8 px-4 py-3">
      <p className="flex items-start gap-2 text-sm text-muted">
        <span aria-hidden className="mt-0.5 font-mono text-unavail">
          —
        </span>
        <span>
          <span className="font-semibold text-foreground">Not available. </span>
          {reason}
        </span>
      </p>
      {steps && <div className="mt-2.5 border-t border-hairline pt-2.5">{steps}</div>}
    </div>
  );
}

/* -------------------------------------------------------------- navigation */

export function Tabs({
  tabs,
  active,
  onChange,
  ariaLabel,
}: {
  tabs: { id: string; label: string }[];
  active: string;
  onChange: (id: string) => void;
  ariaLabel: string;
}) {
  return (
    <div
      role="tablist"
      aria-label={ariaLabel}
      className="scroll-thin -mx-1 flex gap-1 overflow-x-auto px-1 pb-px"
    >
      {tabs.map((tab) => {
        const selected = tab.id === active;
        return (
          <button
            key={tab.id}
            role="tab"
            type="button"
            aria-selected={selected}
            onClick={() => onChange(tab.id)}
            className={clsx(
              "whitespace-nowrap rounded-t-md border-b-2 px-3 py-2 text-[13px] transition-colors",
              selected
                ? "border-signal font-semibold text-foreground"
                : "border-transparent text-muted hover:text-foreground",
            )}
          >
            {tab.label}
          </button>
        );
      })}
    </div>
  );
}

export function SegmentedControl({
  options,
  value,
  onChange,
  ariaLabel,
}: {
  options: { value: string; label: string }[];
  value: string;
  onChange: (value: string) => void;
  ariaLabel: string;
}) {
  return (
    <div
      role="radiogroup"
      aria-label={ariaLabel}
      className="inline-flex rounded-md border border-line bg-panel2 p-0.5"
    >
      {options.map((option) => (
        <button
          key={option.value}
          type="button"
          role="radio"
          aria-checked={value === option.value}
          onClick={() => onChange(option.value)}
          className={clsx(
            "whitespace-nowrap rounded px-2.5 py-1 text-[12px] transition-colors",
            value === option.value
              ? "bg-signal/15 font-semibold text-signal"
              : "text-muted hover:text-foreground",
          )}
        >
          {option.label}
        </button>
      ))}
    </div>
  );
}

/* ------------------------------------------------------------------ atoms */

export function MeterBar({
  value,
  max = 1,
  color = "var(--signal)",
  className,
  label,
}: {
  value: number;
  max?: number;
  color?: string;
  className?: string;
  label?: string;
}) {
  const pct = Math.max(0, Math.min(100, (value / max) * 100));
  return (
    <div
      className={clsx("h-1.5 w-full overflow-hidden rounded-full bg-panel3", className)}
      role={label ? "img" : undefined}
      aria-label={label}
    >
      <div
        className="h-full rounded-full transition-[width] duration-500"
        style={{ width: `${pct}%`, background: color }}
      />
    </div>
  );
}

export function PlayerAvatar({ name, size = 32 }: { name: string; size?: number }) {
  const initials = name
    .split(" ")
    .map((part) => part[0])
    .filter(Boolean)
    .slice(0, 2)
    .join("");
  return (
    <span
      aria-hidden
      className="numeral flex items-center justify-center rounded-full bg-panel3 text-muted"
      style={{ width: size, height: size, fontSize: size * 0.4 }}
    >
      {initials}
    </span>
  );
}

export function Th({
  children,
  className,
  numeric,
}: {
  children?: React.ReactNode;
  className?: string;
  numeric?: boolean;
}) {
  return (
    <th
      scope="col"
      className={clsx(
        "eyebrow whitespace-nowrap px-2 py-2 text-[0.625rem]",
        numeric ? "text-right" : "text-left",
        className,
      )}
    >
      {children}
    </th>
  );
}

export function Td({
  children,
  className,
  numeric,
}: {
  children?: React.ReactNode;
  className?: string;
  numeric?: boolean;
}) {
  return (
    <td className={clsx("px-2 py-1.5 text-sm", numeric && "data text-right", className)}>
      {children}
    </td>
  );
}
