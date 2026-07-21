"""Scoring pipeline: team needs from current stats + roster composition.

Run after ingestion and training (`make score`). Needs are transparent percentile
rules (see needs.py) — results are persisted with explanations for the UI."""

from typing import Any

import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.core.logging import get_logger
from app.db.models import (
    Player,
    PlayerSeasonStats,
    RosterEntry,
    Team,
    TeamNeed,
    TeamSeasonStats,
)

from .needs import compute_team_needs

logger = get_logger(__name__)


def _league_stats_frame(db: Session, season: str) -> pd.DataFrame:
    """One row per team; columns prefixed base_/advanced_."""
    rows: dict[str, dict[str, Any]] = {}
    for stats in db.scalars(
        select(TeamSeasonStats).where(TeamSeasonStats.season == season)
    ).all():
        entry = rows.setdefault(stats.team_id, {"team_id": stats.team_id})
        for key, value in (stats.stats or {}).items():
            entry[f"{stats.stat_type}_{key}"] = value
    return pd.DataFrame(list(rows.values()))


def _roster_profile(db: Session, team_id: str, season: str) -> dict[str, Any] | None:
    entries = db.scalars(
        select(RosterEntry).where(
            RosterEntry.team_id == team_id, RosterEntry.season == season, RosterEntry.is_current
        )
    ).all()
    if not entries:
        return None
    heights = [e.player.height_inches for e in entries if e.player.height_inches]
    ages = [e.age for e in entries if e.age]

    # High-assist creators: AST_PCT >= 25% in current-season advanced stats
    creator_count = 0
    for entry in entries:
        adv = db.scalar(
            select(PlayerSeasonStats).where(
                PlayerSeasonStats.player_id == entry.player_id,
                PlayerSeasonStats.season == season,
                PlayerSeasonStats.stat_type == "advanced",
            )
        )
        ast_pct = (adv.stats or {}).get("AST_PCT") if adv else None
        if ast_pct is not None and float(ast_pct) >= 0.25:
            creator_count += 1
    return {
        "avg_height": sum(heights) / len(heights) if heights else None,
        "avg_age": sum(ages) / len(ages) if ages else None,
        "n_creators": creator_count,
        "roster_size": len(entries),
    }


def score_all(db: Session) -> dict[str, Any]:
    settings = get_settings()
    season = settings.current_season
    league = _league_stats_frame(db, season)
    if league.empty:
        return {"error": "no team stats ingested; run `make sync-data` first"}

    teams = db.scalars(select(Team)).all()
    total_needs = 0
    for team in teams:
        team_stats: dict[str, dict] = {}
        for stats in db.scalars(
            select(TeamSeasonStats).where(
                TeamSeasonStats.team_id == team.id, TeamSeasonStats.season == season
            )
        ).all():
            team_stats[stats.stat_type] = stats.stats or {}
        if not team_stats:
            continue
        profile = _roster_profile(db, team.id, season)
        needs = compute_team_needs(team_stats, league, profile)

        for existing in db.scalars(
            select(TeamNeed).where(TeamNeed.team_id == team.id, TeamNeed.season == season)
        ).all():
            db.delete(existing)
        for need in needs:
            db.add(
                TeamNeed(
                    team_id=team.id,
                    season=season,
                    need_key=need.need_key,
                    severity=need.severity,
                    percentile=need.percentile,
                    explanation=need.explanation,
                )
            )
            total_needs += 1
    db.commit()
    logger.info("scored team needs: %d rows", total_needs)
    return {"teams": len(teams), "needs_written": total_needs, "season": season}


def player_count_check(db: Session) -> int:
    return len(db.scalars(select(Player).where(Player.is_active)).all())
