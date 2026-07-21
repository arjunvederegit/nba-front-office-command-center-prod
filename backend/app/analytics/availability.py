"""Availability from real games-played history — never a medical prediction.

    Availability_i = sum_s(decay^(s-1) * GP_{i,s}) / sum_s(decay^(s-1) * TeamGames_s)

With no injury provider configured this is the only availability signal, and it is
labeled as historical availability in the UI."""

import pandas as pd

TEAM_GAMES_PER_SEASON = 82.0


def availability_from_history(
    season_df: pd.DataFrame, seasons: list[str], decay: float = 0.7
) -> pd.DataFrame:
    """Returns player_id → availability in [0, 1] using GP across the season window."""
    ordered = list(reversed(seasons))  # most recent first
    weights = {season: decay**i for i, season in enumerate(ordered)}
    df = season_df[season_df["season"].isin(seasons)][["player_id", "season", "GP"]].copy()
    df["w"] = df["season"].map(weights)
    df["gp_w"] = pd.to_numeric(df["GP"], errors="coerce").fillna(0) * df["w"]

    grouped = df.groupby("player_id").agg(gp_w=("gp_w", "sum"), seasons=("season", "nunique"))
    # Denominator: the seasons the player was in the league (not all window seasons),
    # so young players are not penalized for seasons before their careers began.
    denominators = df.groupby("player_id")["w"].sum() * TEAM_GAMES_PER_SEASON
    grouped["availability"] = (grouped["gp_w"] / denominators).clip(0.0, 1.0)
    return grouped.reset_index()[["player_id", "availability", "seasons"]]
