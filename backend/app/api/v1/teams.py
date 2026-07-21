from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.schemas import Provenance, RosterPlayerOut, TeamOut
from app.config import get_settings
from app.core.errors import NotFoundError
from app.db.base import get_db
from app.db.models import (
    ModelVersion,
    PlayerArchetype,
    PlayerImpactEstimate,
    PlayerSeasonStats,
    RosterEntry,
    Standing,
    Team,
    TeamNeed,
    TeamSeasonStats,
)
from app.services.payroll import team_payroll_summary

router = APIRouter(prefix="/teams", tags=["teams"])


def _team_out(team: Team) -> TeamOut:
    return TeamOut(
        id=team.id,
        nba_team_id=team.nba_team_id,
        full_name=team.full_name,
        abbreviation=team.abbreviation,
        nickname=team.nickname,
        city=team.city,
        conference=team.conference,
        division=team.division,
        provenance=Provenance(source_retrieved_at=team.source_retrieved_at),
    )


def _get_team(db: Session, team_id: str) -> Team:
    team = db.get(Team, team_id)
    if team is None:
        raise NotFoundError(f"team {team_id} not found")
    return team


@router.get("")
def list_teams(db: Session = Depends(get_db)) -> list[TeamOut]:
    teams = db.scalars(select(Team).order_by(Team.full_name)).all()
    return [_team_out(t) for t in teams]


@router.get("/{team_id}")
def get_team(team_id: str, db: Session = Depends(get_db)) -> dict:
    settings = get_settings()
    team = _get_team(db, team_id)
    season = settings.current_season
    standing = db.scalar(
        select(Standing).where(Standing.team_id == team.id, Standing.season == season)
    )
    stats: dict[str, dict] = {}
    stats_retrieved_at = None
    for row in db.scalars(
        select(TeamSeasonStats).where(
            TeamSeasonStats.team_id == team.id, TeamSeasonStats.season == season
        )
    ).all():
        stats[row.stat_type] = row.stats or {}
        stats_retrieved_at = row.source_retrieved_at
    return {
        "team": _team_out(team).model_dump(),
        "season": season,
        "standing": {
            "wins": standing.wins,
            "losses": standing.losses,
            "win_pct": standing.win_pct,
            "conference": standing.conference,
            "playoff_rank": standing.playoff_rank,
            "details": standing.details,
            "source_retrieved_at": standing.source_retrieved_at.isoformat()
            if standing.source_retrieved_at
            else None,
        }
        if standing
        else None,
        "stats": stats,
        "stats_retrieved_at": stats_retrieved_at.isoformat() if stats_retrieved_at else None,
    }


@router.get("/{team_id}/roster")
def get_roster(team_id: str, db: Session = Depends(get_db)) -> dict:
    settings = get_settings()
    team = _get_team(db, team_id)
    entries = db.scalars(
        select(RosterEntry)
        .where(
            RosterEntry.team_id == team.id,
            RosterEntry.season == settings.current_season,
            RosterEntry.is_current,
        )
        .order_by(RosterEntry.position)
    ).all()

    impact_model = db.scalar(
        select(ModelVersion).where(
            ModelVersion.model_name == "player_impact", ModelVersion.is_active
        )
    )
    impacts = {}
    if impact_model:
        impacts = {
            r.player_id: r
            for r in db.scalars(
                select(PlayerImpactEstimate).where(
                    PlayerImpactEstimate.model_version_id == impact_model.id
                )
            ).all()
        }
    archetypes = {
        a.player_id: a.label
        for a in db.scalars(
            select(PlayerArchetype).where(PlayerArchetype.season == settings.current_season)
        ).all()
    }

    players = []
    retrieved_at = None
    for entry in entries:
        impact = impacts.get(entry.player_id)
        retrieved_at = entry.source_retrieved_at or retrieved_at
        players.append(
            RosterPlayerOut(
                player_id=entry.player_id,
                nba_player_id=entry.player.nba_player_id,
                name=entry.player.full_name,
                position=entry.position,
                jersey_number=entry.jersey_number,
                age=entry.age,
                height_inches=entry.player.height_inches,
                years_experience=entry.player.years_experience,
                tei=round(impact.tei, 2) if impact else None,
                archetype=archetypes.get(entry.player_id),
                availability=round(impact.availability, 3)
                if impact and impact.availability is not None
                else None,
            ).model_dump()
        )
    return {
        "team": _team_out(team).model_dump(),
        "season": settings.current_season,
        "roster": players,
        "source": "NBA.com via nba_api (CommonTeamRoster)",
        "source_retrieved_at": retrieved_at.isoformat() if retrieved_at else None,
    }


@router.get("/{team_id}/needs")
def get_needs(team_id: str, db: Session = Depends(get_db)) -> dict:
    settings = get_settings()
    team = _get_team(db, team_id)
    needs = db.scalars(
        select(TeamNeed)
        .where(TeamNeed.team_id == team.id, TeamNeed.season == settings.current_season)
        .order_by(TeamNeed.severity.desc())
    ).all()
    return {
        "team_id": team.id,
        "season": settings.current_season,
        "computed": bool(needs),
        "note": None
        if needs
        else "Needs not computed yet — run `make score` after ingesting data.",
        "needs": [
            {
                "need_key": n.need_key,
                "severity": n.severity,
                "percentile": n.percentile,
                "explanation": n.explanation,
            }
            for n in needs
        ],
        "method": "Transparent percentile rules over real team statistics and roster "
        "composition (see /methodology); no LLM involvement.",
    }


@router.get("/{team_id}/payroll")
def get_payroll(team_id: str, db: Session = Depends(get_db)) -> dict:
    team = _get_team(db, team_id)
    return {"team_id": team.id, **team_payroll_summary(db, team)}


@router.get("/{team_id}/season-stats")
def get_player_season_stats(team_id: str, db: Session = Depends(get_db)) -> dict:
    """Per-player current-season stats for this team's roster (for the team page)."""
    settings = get_settings()
    team = _get_team(db, team_id)
    entries = db.scalars(
        select(RosterEntry).where(
            RosterEntry.team_id == team.id,
            RosterEntry.season == settings.current_season,
            RosterEntry.is_current,
        )
    ).all()
    player_ids = [e.player_id for e in entries]
    rows = db.scalars(
        select(PlayerSeasonStats).where(
            PlayerSeasonStats.player_id.in_(player_ids),
            PlayerSeasonStats.season == settings.current_season,
            PlayerSeasonStats.stat_type == "base",
        )
    ).all()
    by_player = {r.player_id: r for r in rows}
    return {
        "season": settings.current_season,
        "stats": {
            pid: {
                "GP": by_player[pid].games_played,
                "MIN": by_player[pid].minutes,
                **{
                    k: (by_player[pid].stats or {}).get(k)
                    for k in ("PTS", "REB", "AST", "STL", "BLK", "FG3_PCT", "FG_PCT")
                },
            }
            for pid in player_ids
            if pid in by_player
        },
    }
