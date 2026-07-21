"use client";

import clsx from "clsx";
import { useState } from "react";
import { formatDate } from "@/lib/format";

export function Card({
  children,
  className,
  title,
  subtitle,
  actions,
}: {
  children: React.ReactNode;
  className?: string;
  title?: string;
  subtitle?: React.ReactNode;
  actions?: React.ReactNode;
}) {
  return (
    <section className={clsx("rounded-lg border border-line bg-panel", className)}>
      {(title || actions) && (
        <header className="flex items-start justify-between gap-3 border-b border-line px-4 py-3">
          <div>
            {title && <h2 className="text-sm font-semibold tracking-wide">{title}</h2>}
            {subtitle && <div className="mt-0.5 text-xs text-muted">{subtitle}</div>}
          </div>
          {actions}
        </header>
      )}
      <div className="p-4">{children}</div>
    </section>
  );
}

const STATUS_STYLES: Record<string, string> = {
  pass: "bg-pass/15 text-pass border-pass/40",
  verified_legal: "bg-pass/15 text-pass border-pass/40",
  succeeded: "bg-pass/15 text-pass border-pass/40",
  fail: "bg-fail/15 text-fail border-fail/40",
  verified_illegal: "bg-fail/15 text-fail border-fail/40",
  failed: "bg-fail/15 text-fail border-fail/40",
  error: "bg-fail/15 text-fail border-fail/40",
  warning: "bg-warn/15 text-warn border-warn/40",
  conditionally_valid: "bg-warn/15 text-warn border-warn/40",
  stale: "bg-warn/15 text-warn border-warn/40",
  unavailable: "bg-unavail/15 text-unavail border-unavail/40",
  not_evaluated: "bg-unavail/15 text-unavail border-unavail/40",
  info: "bg-accent/15 text-accent border-accent/40",
  running: "bg-accent/15 text-accent border-accent/40",
};

export function Badge({
  status,
  children,
  className,
}: {
  status?: string;
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <span
      className={clsx(
        "inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[11px] font-medium whitespace-nowrap",
        STATUS_STYLES[status ?? "info"] ?? STATUS_STYLES.info,
        className,
      )}
    >
      {children}
    </span>
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
    <p className={clsx("text-[11px] text-muted", className)}>
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
  if (ageHours > staleAfterHours) {
    return <Badge status="stale">stale · {Math.round(ageHours)}h old</Badge>;
  }
  return <Badge status="pass">fresh · {formatDate(retrievedAt)}</Badge>;
}

export function Spinner({ label = "Loading…" }: { label?: string }) {
  return (
    <div className="flex items-center gap-2 py-8 text-sm text-muted" role="status">
      <span className="h-4 w-4 animate-spin rounded-full border-2 border-line border-t-accent" />
      {label}
    </div>
  );
}

export function ErrorState({ message }: { message: string }) {
  return (
    <div className="rounded-md border border-fail/40 bg-fail/10 px-4 py-3 text-sm text-fail">
      {message}
    </div>
  );
}

export function EmptyState({ title, hint }: { title: string; hint?: string }) {
  return (
    <div className="rounded-md border border-dashed border-line px-4 py-8 text-center">
      <p className="text-sm text-foreground">{title}</p>
      {hint && <p className="mt-1 text-xs text-muted">{hint}</p>}
    </div>
  );
}

export function UnavailableNotice({ reason }: { reason: string }) {
  return (
    <div className="rounded-md border border-unavail/40 bg-unavail/10 px-4 py-3 text-sm text-unavail">
      <span className="font-semibold">Unavailable.</span> {reason}
    </div>
  );
}

export function MeterBar({
  value,
  max = 1,
  color = "var(--accent)",
  className,
}: {
  value: number;
  max?: number;
  color?: string;
  className?: string;
}) {
  const width = Math.max(0, Math.min(100, (value / max) * 100));
  return (
    <div className={clsx("h-2 w-full rounded-full bg-panel2", className)}>
      <div className="h-2 rounded-full" style={{ width: `${width}%`, background: color }} />
    </div>
  );
}

export function PlayerAvatar({ name, size = 32 }: { name: string; size?: number }) {
  const initials = name
    .split(" ")
    .map((part) => part[0])
    .slice(0, 2)
    .join("");
  return (
    <span
      aria-hidden
      className="flex items-center justify-center rounded-full bg-panel2 font-semibold text-muted"
      style={{ width: size, height: size, fontSize: size * 0.36 }}
    >
      {initials}
    </span>
  );
}

export function Th({ children, className }: { children?: React.ReactNode; className?: string }) {
  return (
    <th
      className={clsx(
        "px-2 py-1.5 text-left text-[11px] font-semibold uppercase tracking-wider text-muted",
        className,
      )}
    >
      {children}
    </th>
  );
}

export function Td({ children, className }: { children?: React.ReactNode; className?: string }) {
  return <td className={clsx("px-2 py-1.5 text-sm", className)}>{children}</td>;
}
