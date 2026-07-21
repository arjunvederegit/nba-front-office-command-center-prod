"""Team performance projection with an explicit rotation allocator.

Post-trade projection reallocates the 240 regulation minutes per game rather than
naively summing player values: departing minutes are redistributed to arrivals and
incumbents under per-player caps. Net-rating deltas convert to wins through a
historically calibrated linear mapping (fit on ingested team-seasons, not a
hard-coded constant)."""

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

TEAM_MINUTES = 240.0
DEFAULT_MAX_MINUTES = 36.0
GAMES = 82.0
PLAYERS_ON_COURT = 5.0


@dataclass
class RotationPlayer:
    player_id: str
    name: str
    tei: float
    baseline_minutes: float  # minutes per game last observed
    availability: float = 1.0
    max_minutes: float = DEFAULT_MAX_MINUTES
    user_minutes: float | None = None  # user-editable override


@dataclass
class RotationResult:
    minutes: dict[str, float]
    team_tei_per_minute: float
    detail: list[dict] = field(default_factory=list)


def allocate_rotation(players: list[RotationPlayer]) -> RotationResult:
    """Distribute 240 minutes proportionally to baseline minutes (a proxy for coach
    trust) with user overrides and per-player caps. Availability discounts expected
    minutes: a 70%-available player contributes 70% of allocated minutes in
    expectation."""
    minutes: dict[str, float] = {}
    remaining = TEAM_MINUTES

    fixed = [p for p in players if p.user_minutes is not None]
    flexible = [p for p in players if p.user_minutes is None]
    for p in fixed:
        allotted = min(max(p.user_minutes or 0.0, 0.0), p.max_minutes)
        minutes[p.player_id] = allotted
        remaining -= allotted
    remaining = max(remaining, 0.0)

    weights = np.array([max(p.baseline_minutes, 2.0) for p in flexible], dtype=float)
    if flexible and weights.sum() > 0:
        raw = weights / weights.sum() * remaining
        # Iteratively clip at caps, redistributing overflow
        for _ in range(6):
            caps = np.array([p.max_minutes for p in flexible])
            over = raw > caps
            overflow = float(np.clip(raw - caps, 0, None).sum())
            raw = np.where(over, caps, raw)
            under = ~over
            if overflow <= 1e-6 or not under.any():
                break
            raw = raw + under * (weights * under / max((weights * under).sum(), 1e-9)) * overflow
        for p, m in zip(flexible, raw, strict=False):
            minutes[p.player_id] = float(m)

    total = sum(minutes.values()) or 1.0
    # Weighted per-minute team impact, availability-discounted with replacement-level
    # (TEI = -2.0) fill-in for missed games.
    REPLACEMENT_TEI = -2.0
    weighted = 0.0
    detail = []
    for p in players:
        m = minutes.get(p.player_id, 0.0)
        effective_tei = p.availability * p.tei + (1 - p.availability) * REPLACEMENT_TEI
        weighted += m / total * effective_tei
        detail.append(
            {
                "player_id": p.player_id,
                "name": p.name,
                "minutes": round(m, 1),
                "tei": round(p.tei, 2),
                "availability": round(p.availability, 3),
            }
        )
    return RotationResult(minutes=minutes, team_tei_per_minute=weighted, detail=detail)


def team_tei_to_net_rating_delta(before: RotationResult, after: RotationResult) -> float:
    """TEI is on a per-100 individual scale; five players share the floor, so a team's
    net-rating shift is approximately the change in minutes-weighted average TEI."""
    return after.team_tei_per_minute - before.team_tei_per_minute


def calibrate_wins_per_net_rating(team_seasons: pd.DataFrame) -> dict:
    """Fit wins = a + b * net_rating on ingested team-seasons (NET_RATING vs actual
    wins). Returns the mapping with fit diagnostics; falls back to the widely
    replicated ~2.7 wins/point with an explicit flag when data is insufficient."""
    df = team_seasons.dropna(subset=["net_rating", "wins"])
    if len(df) < 30:
        return {"slope": 2.7, "intercept": 41.0, "r2": None, "n": len(df), "calibrated": False}
    x = df["net_rating"].to_numpy(dtype=float)
    y = df["wins"].to_numpy(dtype=float)
    slope, intercept = np.polyfit(x, y, 1)
    predictions = slope * x + intercept
    ss_res = float(((y - predictions) ** 2).sum())
    ss_tot = float(((y - y.mean()) ** 2).sum())
    return {
        "slope": float(slope),
        "intercept": float(intercept),
        "r2": 1 - ss_res / ss_tot if ss_tot else None,
        "residual_std": float(np.std(y - predictions)),
        "n": len(df),
        "calibrated": True,
    }


def net_rating_delta_to_wins(
    delta_net: float, mapping: dict, games_remaining: float = GAMES
) -> float:
    return float(mapping["slope"]) * delta_net * (games_remaining / GAMES)
