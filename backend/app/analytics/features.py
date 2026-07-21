"""Feature engineering from ingested provider-backed season stats.

One row per (player, season) combining base, advanced, and (when available) estimated
metrics. All features derive from real NBA.com data — nothing is imputed beyond
documented, conservative minute-weighted league means for optional columns."""

from typing import Any

import numpy as np
import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Player, PlayerSeasonStats

RANDOM_SEED = 20260720

# Advanced-table columns kept as features.
ADVANCED_COLS = [
    "OFF_RATING", "DEF_RATING", "NET_RATING", "AST_PCT", "AST_TO", "OREB_PCT",
    "DREB_PCT", "REB_PCT", "TM_TOV_PCT", "EFG_PCT", "TS_PCT", "USG_PCT", "PACE", "PIE", "POSS",
]
BASE_COLS = ["PTS", "REB", "AST", "STL", "BLK", "TOV", "FGA", "FG3A", "FTA", "PLUS_MINUS", "AGE"]
ESTIMATED_COLS = ["E_OFF_RATING", "E_DEF_RATING", "E_NET_RATING", "E_USG_PCT"]


def build_player_season_features(db: Session) -> pd.DataFrame:
    """Wide feature frame: one row per player-season with GP/MIN and stat columns."""
    rows = db.execute(
        select(
            PlayerSeasonStats.player_id,
            PlayerSeasonStats.season,
            PlayerSeasonStats.stat_type,
            PlayerSeasonStats.games_played,
            PlayerSeasonStats.minutes,
            PlayerSeasonStats.stats,
            Player.full_name,
            Player.nba_player_id,
            Player.birth_date,
            Player.height_inches,
            Player.position,
            Player.is_active,
        ).join(Player, Player.id == PlayerSeasonStats.player_id)
    ).all()
    if not rows:
        return pd.DataFrame()

    by_key: dict[tuple[str, str], dict[str, Any]] = {}
    for r in rows:
        key = (r.player_id, r.season)
        entry = by_key.setdefault(
            key,
            {
                "player_id": r.player_id,
                "season": r.season,
                "full_name": r.full_name,
                "nba_player_id": r.nba_player_id,
                "height_inches": r.height_inches,
                "position": r.position,
                "is_active": r.is_active,
            },
        )
        stats = r.stats or {}
        if r.stat_type == "base":
            entry["GP"] = r.games_played
            entry["MIN"] = r.minutes
            for col in BASE_COLS:
                entry[col] = stats.get(col)
        elif r.stat_type == "advanced":
            for col in ADVANCED_COLS:
                entry[col] = stats.get(col)
        elif r.stat_type == "estimated":
            for col in ESTIMATED_COLS:
                entry[col] = stats.get(col)

    df = pd.DataFrame(list(by_key.values()))
    df = df.dropna(subset=["GP", "MIN"])
    df["total_minutes"] = df["GP"].astype(float) * df["MIN"].astype(float)

    # Derived rates (per-minute to sidestep pace-of-play distortion in per-game stats)
    for col, name in (("PTS", "pts_per_min"), ("STL", "stl_per_min"), ("BLK", "blk_per_min"),
                      ("REB", "reb_per_min"), ("AST", "ast_per_min"), ("TOV", "tov_per_min")):
        df[name] = pd.to_numeric(df[col], errors="coerce") / df["MIN"].astype(float)
    fga = pd.to_numeric(df["FGA"], errors="coerce")
    df["fg3a_rate"] = pd.to_numeric(df["FG3A"], errors="coerce") / fga.replace(0, np.nan)
    df["fta_rate"] = pd.to_numeric(df["FTA"], errors="coerce") / fga.replace(0, np.nan)
    # Points per 75 possessions using individual possessions when available
    poss = pd.to_numeric(df.get("POSS"), errors="coerce")
    pts_total = pd.to_numeric(df["PTS"], errors="coerce") * df["GP"].astype(float)
    df["pts_per75"] = np.where(poss > 0, pts_total / poss * 75, np.nan)
    return df


MODEL_FEATURES = [
    "pts_per75", "TS_PCT", "USG_PCT", "AST_PCT", "TM_TOV_PCT", "OREB_PCT", "DREB_PCT",
    "stl_per_min", "blk_per_min", "fg3a_rate", "fta_rate", "MIN", "GP", "AGE", "PIE",
    "NET_RATING",
]


def minutes_weighted_league_mean(df: pd.DataFrame, col: str) -> float:
    values = pd.to_numeric(df[col], errors="coerce")
    weights = df["total_minutes"].astype(float)
    mask = values.notna() & weights.notna()
    if not mask.any():
        return 0.0
    return float(np.average(values[mask], weights=weights[mask]))


def zscore_by_season(df: pd.DataFrame, col: str, out_col: str | None = None) -> pd.DataFrame:
    """Minutes-weighted z-score within each season (cross-season comparability)."""
    out_col = out_col or f"z_{col}"

    result = pd.Series(np.zeros(len(df)), index=df.index, dtype=float)
    for _, group in df.groupby("season"):
        values = pd.to_numeric(group[col], errors="coerce")
        weights = group["total_minutes"].astype(float)
        mask = values.notna() & (weights > 0)
        if mask.sum() < 10:
            continue
        mean = np.average(values[mask], weights=weights[mask])
        var = np.average((values[mask] - mean) ** 2, weights=weights[mask])
        std = np.sqrt(var) if var > 0 else 1.0
        result.loc[group.index] = ((values - mean) / std).fillna(0.0)
    df[out_col] = result
    return df


def recency_weighted_features(
    df: pd.DataFrame, seasons: list[str], decay: float = 0.7, min_total_minutes: float = 200.0
) -> pd.DataFrame:
    """Collapse multi-season rows to one row per player using minutes x recency weights:

        X_weighted = sum(decay^(s-1) * minutes_s * X_s) / sum(decay^(s-1) * minutes_s)

    where s=1 is the most recent season. Players below min_total_minutes across the
    window are excluded from modeling (insufficient evidence, not imputed)."""
    ordered = list(reversed(seasons))  # most recent first
    weight_by_season = {season: decay**i for i, season in enumerate(ordered)}
    df = df[df["season"].isin(seasons)].copy()
    df["recency_w"] = df["season"].map(weight_by_season) * df["total_minutes"].astype(float)

    numeric_cols = [c for c in MODEL_FEATURES if c in df.columns]
    records: list[dict[str, Any]] = []
    for player_id, group in df.groupby("player_id"):
        weights = group["recency_w"].astype(float)
        if weights.sum() <= 0 or group["total_minutes"].sum() < min_total_minutes:
            continue
        latest = group.sort_values("season").iloc[-1]
        record: dict[str, Any] = {
            "player_id": player_id,
            "full_name": latest["full_name"],
            "nba_player_id": latest["nba_player_id"],
            "height_inches": latest["height_inches"],
            "position": latest["position"],
            "is_active": latest["is_active"],
            "latest_season": latest["season"],
            "seasons_observed": len(group),
            "total_minutes_window": float(group["total_minutes"].sum()),
        }
        for col in numeric_cols:
            values = pd.to_numeric(group[col], errors="coerce")
            mask = values.notna()
            if mask.any():
                record[col] = float(np.average(values[mask], weights=weights[mask]))
            else:
                record[col] = None
        records.append(record)
    return pd.DataFrame(records)
