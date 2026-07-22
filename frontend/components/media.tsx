"use client";

/**
 * Team logos and player photos served by the backend asset manifest
 * (/api/v1/assets/...), with deterministic fallbacks so a missing image can never
 * break a page: players fall back to an initials disc, teams to an abbreviation
 * badge tinted with team colors. All images are lazy-loaded with real alt text.
 */

import { useState } from "react";
import { teamTheme } from "@/lib/teamTheme";

export function TeamLogo({
  abbreviation,
  name,
  size = 32,
  className,
}: {
  abbreviation: string | null | undefined;
  name?: string;
  size?: number;
  className?: string;
}) {
  const [failed, setFailed] = useState(false);
  const abbr = abbreviation?.toUpperCase() ?? "";
  if (!abbr || failed) {
    const theme = teamTheme(abbr);
    return (
      <span
        aria-hidden={!name}
        role={name ? "img" : undefined}
        aria-label={name ? `${name} badge` : undefined}
        className={`flex items-center justify-center rounded-full font-bold text-white ${className ?? ""}`}
        style={{
          width: size,
          height: size,
          fontSize: size * 0.32,
          background: `linear-gradient(135deg, ${theme.primary}, ${theme.secondary}66)`,
        }}
      >
        {abbr || "?"}
      </span>
    );
  }
  return (
    // eslint-disable-next-line @next/next/no-img-element -- backend-served asset with runtime fallback
    <img
      src={`/api/v1/assets/teams/${abbr}`}
      alt={`${name ?? abbr} logo`}
      width={size}
      height={size}
      loading="lazy"
      className={`object-contain ${className ?? ""}`}
      style={{ width: size, height: size }}
      onError={() => setFailed(true)}
    />
  );
}

export function PlayerPhoto({
  nbaPlayerId,
  name,
  size = 36,
  className,
}: {
  nbaPlayerId: number | null | undefined;
  name: string;
  size?: number;
  className?: string;
}) {
  const [failed, setFailed] = useState(false);
  if (!nbaPlayerId || failed) {
    const initials = name
      .split(" ")
      .map((part) => part[0])
      .filter(Boolean)
      .slice(0, 2)
      .join("");
    return (
      <span
        role="img"
        aria-label={`${name} (no photo available)`}
        className={`flex shrink-0 items-center justify-center rounded-full bg-panel2 font-semibold text-muted ${className ?? ""}`}
        style={{ width: size, height: size, fontSize: size * 0.34 }}
      >
        {initials}
      </span>
    );
  }
  return (
    // eslint-disable-next-line @next/next/no-img-element -- backend-served asset with runtime fallback
    <img
      src={`/api/v1/assets/players/${nbaPlayerId}`}
      alt={`Photo of ${name}`}
      width={size}
      height={size}
      loading="lazy"
      className={`shrink-0 rounded-full object-cover object-top ${className ?? ""}`}
      style={{ width: size, height: size }}
      onError={() => setFailed(true)}
    />
  );
}
