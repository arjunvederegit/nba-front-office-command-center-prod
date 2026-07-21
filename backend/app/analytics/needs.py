"""Team needs from transparent percentile rules over real team statistics and roster
composition — no LLM involvement. Each need records its percentile and a plain-English
explanation shown in the UI."""

from dataclasses import dataclass

import pandas as pd

# (need_key, source, column, lower_is_need, explanation template, proxy_note)
STAT_RULES = [
    (
        "three_point_volume",
        "base",
        "FG3A",
        True,
        "Team ranks in the {pct:.0f}th percentile for three-point attempts per game",
        None,
    ),
    (
        "defense_overall",
        "advanced",
        "DEF_RATING",
        False,
        "Defensive rating is in the {pct:.0f}th percentile (higher = worse defense)",
        None,
    ),
    (
        "offense_overall",
        "advanced",
        "OFF_RATING",
        True,
        "Offensive rating is in the {pct:.0f}th percentile",
        None,
    ),
    (
        "defensive_rebounding",
        "advanced",
        "DREB_PCT",
        True,
        "Defensive rebound share is in the {pct:.0f}th percentile",
        None,
    ),
    (
        "playmaking",
        "advanced",
        "AST_PCT",
        True,
        "Share of baskets assisted is in the {pct:.0f}th percentile",
        None,
    ),
    (
        "ball_security",
        "advanced",
        "TM_TOV_PCT",
        False,
        "Turnover rate is in the {pct:.0f}th percentile (higher = more turnovers)",
        None,
    ),
    (
        "rim_protection",
        "base",
        "BLK",
        True,
        "Blocks per game is in the {pct:.0f}th percentile",
        "blocks are a partial proxy for rim protection",
    ),
    (
        "point_of_attack_defense",
        "base",
        "STL",
        True,
        "Steals per game is in the {pct:.0f}th percentile",
        "steals are a partial proxy for point-of-attack pressure",
    ),
    (
        "shooting_efficiency",
        "advanced",
        "TS_PCT",
        True,
        "True-shooting percentage is in the {pct:.0f}th percentile",
        None,
    ),
]


@dataclass
class NeedResult:
    need_key: str
    severity: float  # 0..1
    percentile: float
    explanation: str


def _percentile(series: pd.Series, value: float) -> float:
    series = pd.to_numeric(series, errors="coerce").dropna()
    if series.empty:
        return 50.0
    return float((series < value).mean() * 100)


def compute_team_needs(
    team_stats: dict[str, dict], league_stats: pd.DataFrame, roster_profile: dict | None = None
) -> list[NeedResult]:
    """team_stats: {"base": {...}, "advanced": {...}} for the team.
    league_stats: DataFrame with one row per team and columns like base_FG3A / advanced_DEF_RATING.
    roster_profile: optional {"avg_height": float, "n_creators": int, "avg_age": float}.
    """
    results: list[NeedResult] = []
    for need_key, source, column, lower_is_need, template, proxy_note in STAT_RULES:
        stats = team_stats.get(source) or {}
        value = stats.get(column)
        league_col = f"{source}_{column}"
        if value is None or league_col not in league_stats.columns:
            continue
        pct = _percentile(league_stats[league_col], float(value))
        # Need severity grows as the team falls below (or above, for inverted stats)
        # the league median.
        severity = max(0.0, (50.0 - pct) / 50.0) if lower_is_need else max(0.0, (pct - 50.0) / 50.0)
        results.append(
            NeedResult(
                need_key=need_key,
                severity=round(severity, 3),
                percentile=round(pct, 1),
                explanation=template.format(pct=pct) + (f" ({proxy_note})" if proxy_note else ""),
            )
        )

    if roster_profile:
        avg_height = roster_profile.get("avg_height")
        if avg_height is not None and avg_height < 77.5:
            results.append(
                NeedResult(
                    "lineup_size",
                    round(min(1.0, (77.5 - avg_height) / 2.5), 3),
                    0.0,
                    f'Average roster height {avg_height:.1f}" is below the league-typical ~78"',
                )
            )
        n_creators = roster_profile.get("n_creators")
        if n_creators is not None and n_creators < 2:
            results.append(
                NeedResult(
                    "secondary_creation",
                    0.6 if n_creators == 1 else 0.9,
                    0.0,
                    f"Roster has {n_creators} high-assist creator(s); most contenders carry 2+",
                )
            )

    return sorted(results, key=lambda r: r.severity, reverse=True)


# Mapping from need keys to the player skill dimensions that address them (see
# archetypes.SKILL_KEYS). Used by roster-fit.
NEED_TO_SKILL = {
    "three_point_volume": "shooting",
    "shooting_efficiency": "shooting",
    "offense_overall": "scoring",
    "defense_overall": "perimeter_defense",
    "point_of_attack_defense": "perimeter_defense",
    "rim_protection": "rim_protection",
    "defensive_rebounding": "rebounding",
    "playmaking": "creation",
    "secondary_creation": "creation",
    "ball_security": "creation",
    "lineup_size": "size",
}
