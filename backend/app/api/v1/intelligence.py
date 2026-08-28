"""Pivot intelligence endpoints — the read surface the decision workflow starts from.

    GET /api/v1/intelligence/vocabulary            what Pivot measures, and what it cannot
    GET /api/v1/intelligence/players/{id}          one player's capabilities
    GET /api/v1/intelligence/teams/{id}/profile    one roster's contents, strengths, needs
    GET /api/v1/intelligence/fit                   Fit(player, team) — team-conditional

A new resource family rather than additions to `/players` and `/teams`, for two reasons.
It keeps the existing routers' contracts untouched, so nothing that reads them can break;
and it groups the endpoints a future GM Copilot would call as tools under one prefix, which
is where `services/tools.py` points.

**There is deliberately no `GET /intelligence/fit/{player_id}`.** Fit requires a team, so
the team is a required query parameter and a fit score with no team named is a 422 rather
than a default. Pivot's position is that no universal player fit score exists; a route
shape that allowed one to be requested would contradict it before any handler ran.
"""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.db.base import get_db
from app.services.intelligence import IntelligenceService

router = APIRouter(prefix="/intelligence", tags=["intelligence"])


@router.get("/vocabulary")
def get_vocabulary() -> dict:
    """The declared basketball vocabulary: skill dimensions, archetypes, needs.

    Generated from the same records the engines read, so the methodology surface cannot
    drift away from what is actually computed. Includes the dimensions Pivot has declared
    it cannot measure, each with the reason.
    """
    return IntelligenceService.vocabulary()


@router.get("/players/{player_id}")
def get_player_intelligence(player_id: str, db: Session = Depends(get_db)) -> dict:
    """One player's measured capabilities.

    Every declared dimension is present. A dimension Pivot cannot measure carries
    `available: false` and the reason, rather than being omitted or filled with a median.
    """
    return IntelligenceService(db).player_intelligence(player_id)


@router.get("/teams/{team_id}/profile")
def get_team_profile(team_id: str, db: Session = Depends(get_db)) -> dict:
    """What a roster contains, what it is good at, and what it lacks.

    Strength and weakness classification is applied here, from the thresholds in
    `domain.needs`, so every client is served one answer rather than deciding for itself.
    """
    return IntelligenceService(db).team_profile(team_id)


@router.get("/fit")
def get_player_team_fit(
    player_id: str = Query(..., description="The player being considered."),
    team_id: str = Query(..., description="The roster he would join. Required — fit is conditional."),
    db: Session = Depends(get_db),
) -> dict:
    """How this player would fit THIS roster.

    Modelled as an addition against the roster's own minutes-weighted skill profile — the
    measured one-way baseline, not a fabricated median player. Scored on the shipped `fit`
    scale where 50 means "changes nothing".
    """
    return IntelligenceService(db).player_team_fit(player_id, team_id)
