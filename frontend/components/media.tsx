"use client";

/**
 * Team crests and player photos.
 *
 * Sources are user-supplied local datasets served by the backend asset manifest
 * and keyed by stable NBA identity. Two invariants:
 *  - nothing is ever stretched: logos letterbox with object-contain, headshots
 *    fill with object-cover anchored to the top so faces survive the crop;
 *  - a missing file can never break a page — logos fall back to a team-colored
 *    abbreviation crest, players to an initials disc.
 */

import clsx from "clsx";
import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { api } from "@/lib/api";
import { playerPhotoSrc, teamIdentity, teamLogoSrc } from "@/lib/teamIdentity";

interface AssetManifest {
  players: number[];
  teams: string[];
}

/**
 * Which identities actually have an indexed image. Fetched once per session so a
 * player without a matched photo renders its fallback immediately rather than
 * costing a 404 round-trip — roughly 12% of rostered players are unmatched.
 */
function useAssetManifest() {
  const { data } = useQuery({
    queryKey: ["asset-manifest"],
    queryFn: () => api.get<AssetManifest>("/assets/manifest"),
    staleTime: Infinity,
    gcTime: Infinity,
    retry: 1,
  });
  return data;
}

export function TeamLogo({
  abbreviation,
  name,
  size = 32,
  className,
  decorative = false,
}: {
  abbreviation: string | null | undefined;
  name?: string;
  size?: number;
  className?: string;
  /** True when an adjacent label already names the team. */
  decorative?: boolean;
}) {
  const [failed, setFailed] = useState(false);
  const manifest = useAssetManifest();
  const abbr = abbreviation?.toUpperCase() ?? "";
  const identity = teamIdentity(abbr);
  const known = manifest ? manifest.teams.includes(abbr) : false;
  const src = known ? teamLogoSrc(abbr) : null;
  const label = name ?? identity.name;

  if (!src || failed) {
    return (
      <span
        role={decorative ? undefined : "img"}
        aria-label={decorative ? undefined : `${label} crest`}
        aria-hidden={decorative || undefined}
        className={clsx(
          "numeral flex shrink-0 items-center justify-center rounded-md",
          className,
        )}
        style={{
          width: size,
          height: size,
          fontSize: size * 0.34,
          color: identity.contrast,
          background: `linear-gradient(140deg, ${identity.primary}, ${identity.secondary}88)`,
        }}
      >
        {abbr || "NBA"}
      </span>
    );
  }

  return (
    // eslint-disable-next-line @next/next/no-img-element -- backend-served asset with runtime fallback
    <img
      src={src}
      alt={decorative ? "" : `${label} logo`}
      aria-hidden={decorative || undefined}
      width={size}
      height={size}
      loading="lazy"
      decoding="async"
      className={clsx("shrink-0 object-contain", className)}
      style={{ width: size, height: size }}
      onError={() => setFailed(true)}
    />
  );
}

/** Larger crest treatment for team headers — the logo sits in its own light. */
export function TeamCrest({
  abbreviation,
  name,
  size = 72,
}: {
  abbreviation: string | null | undefined;
  name?: string;
  size?: number;
}) {
  const identity = teamIdentity(abbreviation);
  return (
    <span
      className="relative flex shrink-0 items-center justify-center"
      style={{ width: size, height: size }}
    >
      <span
        aria-hidden
        className="absolute inset-0 rounded-full blur-xl"
        style={{ background: identity.primary, opacity: 0.28 }}
      />
      <TeamLogo abbreviation={abbreviation} name={name} size={size} className="relative" />
    </span>
  );
}

export function PlayerPhoto({
  nbaPlayerId,
  name,
  size = 36,
  className,
  square = false,
}: {
  nbaPlayerId: number | null | undefined;
  name: string;
  size?: number;
  className?: string;
  /** Rounded-rect crop for card layouts; default is a circular token. */
  square?: boolean;
}) {
  const [failed, setFailed] = useState(false);
  const manifest = useAssetManifest();
  const known = manifest && nbaPlayerId ? manifest.players.includes(nbaPlayerId) : false;
  const src = known ? playerPhotoSrc(nbaPlayerId) : null;
  const shape = square ? "rounded-lg" : "rounded-full";

  if (!src || failed) {
    const initials = name
      .split(" ")
      .map((part) => part[0])
      .filter(Boolean)
      .slice(0, 2)
      .join("");
    return (
      <span
        role="img"
        aria-label={`${name} — no photo available`}
        className={clsx(
          "numeral flex shrink-0 items-center justify-center bg-panel3 text-muted",
          shape,
          className,
        )}
        style={{ width: size, height: size, fontSize: size * 0.38 }}
      >
        {initials}
      </span>
    );
  }

  return (
    // eslint-disable-next-line @next/next/no-img-element -- backend-served asset with runtime fallback
    <img
      src={src}
      alt={`${name} headshot`}
      width={size}
      height={size}
      loading="lazy"
      decoding="async"
      className={clsx("shrink-0 bg-panel3 object-cover object-top", shape, className)}
      style={{ width: size, height: size }}
      onError={() => setFailed(true)}
    />
  );
}
