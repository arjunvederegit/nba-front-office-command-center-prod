"""Data-quality checks. Findings are stored in data_quality_issues and shown on
/data-health — problems are surfaced, never auto-corrected."""

from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db.models import (
    ContractYear,
    DataQualityIssue,
    Game,
    LeagueCapParameters,
    Player,
    PlayerSeasonStats,
    RosterEntry,
    Standing,
    Team,
)


def _record(db: Session, check: str, message: str, severity: str = "warning", entity: str | None = None) -> dict:
    issue = DataQualityIssue(check_name=check, severity=severity, message=message, entity=entity)
    db.add(issue)
    return {"check": check, "severity": severity, "message": message}


def validate_data(db: Session) -> list[dict]:
    settings = get_settings()
    season = settings.current_season
    issues: list[dict] = []

    # Resolve previously recorded open issues; current state is re-derived each run.
    open_issues = db.scalars(
        select(DataQualityIssue).where(DataQualityIssue.resolved_at.is_(None))
    ).all()
    now = datetime.now(UTC)
    for issue in open_issues:
        issue.resolved_at = now

    team_count = db.scalar(select(func.count(Team.id))) or 0
    if team_count != 30:
        issues.append(
            _record(db, "team_count", f"expected 30 teams, found {team_count}", "error")
        )

    dup_players = db.execute(
        select(Player.nba_player_id, func.count(Player.id))
        .group_by(Player.nba_player_id)
        .having(func.count(Player.id) > 1)
    ).all()
    for nba_id, count in dup_players:
        issues.append(
            _record(db, "duplicate_external_id", f"nba_player_id {nba_id} appears {count} times", "error")
        )

    multi_roster = db.execute(
        select(RosterEntry.player_id, func.count(RosterEntry.id))
        .where(RosterEntry.is_current, RosterEntry.season == season)
        .group_by(RosterEntry.player_id)
        .having(func.count(RosterEntry.id) > 1)
    ).all()
    for player_id, count in multi_roster:
        player = db.get(Player, player_id)
        issues.append(
            _record(
                db,
                "player_on_multiple_rosters",
                f"{player.full_name if player else player_id} appears on {count} current rosters",
                "warning",
                entity=player_id,
            )
        )

    roster_counts = db.execute(
        select(RosterEntry.team_id, func.count(RosterEntry.id))
        .where(RosterEntry.is_current, RosterEntry.season == season)
        .group_by(RosterEntry.team_id)
    ).all()
    for team_id, count in roster_counts:
        if count < 10 or count > 21:
            team = db.get(Team, team_id)
            issues.append(
                _record(
                    db,
                    "roster_count_anomaly",
                    f"{team.abbreviation if team else team_id} roster snapshot has {count} players",
                    "warning",
                    entity=team_id,
                )
            )

    negative_minutes = db.scalar(
        select(func.count(PlayerSeasonStats.id)).where(PlayerSeasonStats.minutes < 0)
    ) or 0
    if negative_minutes:
        issues.append(
            _record(db, "negative_minutes", f"{negative_minutes} season-stat rows with negative minutes", "error")
        )

    bad_salaries = db.scalar(
        select(func.count(ContractYear.id)).where(
            (ContractYear.salary <= 0) | (ContractYear.salary > 100_000_000)
        )
    ) or 0
    if bad_salaries:
        issues.append(
            _record(db, "impossible_salary", f"{bad_salaries} contract years with impossible salaries", "error")
        )

    future_games = db.scalar(
        select(func.count(Game.id)).where(
            Game.game_date > (now + timedelta(days=365)).date(), Game.status == "final"
        )
    ) or 0
    if future_games:
        issues.append(
            _record(db, "future_dates", f"{future_games} final games dated more than a year ahead", "error")
        )

    cap = db.scalar(
        select(LeagueCapParameters).where(LeagueCapParameters.league_year == season)
    )
    if cap is None:
        issues.append(
            _record(
                db,
                "cap_parameters_missing",
                f"no cap parameters loaded for league year {season}; run `make seed-config`",
                "error",
            )
        )

    stale_cutoff = now - timedelta(seconds=settings.nba_api_stale_after_seconds)
    stale_standings = db.scalar(
        select(func.count(Standing.id)).where(
            Standing.season == season, Standing.source_retrieved_at < stale_cutoff
        )
    ) or 0
    if stale_standings:
        issues.append(
            _record(db, "stale_records", f"{stale_standings} standings rows older than the staleness TTL")
        )

    malformed_seasons = db.scalar(
        select(func.count(PlayerSeasonStats.id)).where(~PlayerSeasonStats.season.like("____-__"))
    ) or 0
    if malformed_seasons:
        issues.append(
            _record(db, "malformed_seasons", f"{malformed_seasons} stat rows with malformed season strings", "error")
        )

    db.commit()
    return issues
