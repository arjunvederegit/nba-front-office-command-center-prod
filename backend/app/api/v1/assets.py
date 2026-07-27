"""Serve locally indexed media assets (team logos, player headshots) by stable id.

Lookups go through the MediaAsset manifest built by ``app.assets.indexer`` — only
files that were confidently matched to an identity are servable; anything else 404s.
"""

from datetime import UTC, datetime

from fastapi import APIRouter, Depends
from fastapi.responses import FileResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.assets.indexer import coverage
from app.config import get_settings
from app.core.errors import NotFoundError
from app.db.base import get_db
from app.db.models import MediaAsset, Team

router = APIRouter(prefix="/assets", tags=["assets"])

CACHE_HEADERS = {"Cache-Control": "public, max-age=86400"}


@router.get("/coverage")
def asset_coverage(db: Session = Depends(get_db)) -> dict:
    return {**coverage(db), "generated_at": datetime.now(UTC).isoformat()}


@router.get("/teams/{abbreviation}")
def team_logo(abbreviation: str, db: Session = Depends(get_db)) -> FileResponse:
    abbr = abbreviation.upper()
    asset = db.scalar(
        select(MediaAsset)
        .join(Team, MediaAsset.team_id == Team.id)
        .where(MediaAsset.entity_type == "team", func.upper(Team.abbreviation) == abbr)
    )
    if asset is None:
        raise NotFoundError(f"no logo indexed for team {abbr}")
    path = get_settings().logos_dir / asset.file_path
    if not path.is_file():
        raise NotFoundError(f"logo file for team {abbr} is missing on disk")
    return FileResponse(path, media_type=asset.content_type, headers=CACHE_HEADERS)


@router.get("/players/{nba_player_id:int}")
def player_photo(nba_player_id: int, db: Session = Depends(get_db)) -> FileResponse:
    asset = db.scalar(
        select(MediaAsset).where(
            MediaAsset.entity_type == "player",
            MediaAsset.nba_id == nba_player_id,
            MediaAsset.is_primary,
            MediaAsset.player_id.is_not(None),
        )
    )
    if asset is None:
        raise NotFoundError(f"no photo indexed for player {nba_player_id}")
    path = get_settings().player_images_dir / asset.file_path
    if not path.is_file():
        raise NotFoundError(f"photo file for player {nba_player_id} is missing on disk")
    return FileResponse(path, media_type=asset.content_type, headers=CACHE_HEADERS)


@router.get("/manifest")
def asset_manifest(db: Session = Depends(get_db)) -> dict:
    """Which identities actually have an indexed image.

    The client fetches this once and only requests a photo it knows exists, so a
    player without a matched image renders its initials fallback immediately
    instead of costing a 404 round-trip.
    """
    player_ids = db.scalars(
        select(MediaAsset.nba_id).where(
            MediaAsset.entity_type == "player",
            MediaAsset.is_primary,
            MediaAsset.player_id.is_not(None),
            MediaAsset.nba_id.is_not(None),
        )
    ).all()
    team_rows = db.execute(
        select(Team.abbreviation)
        .join(MediaAsset, MediaAsset.team_id == Team.id)
        .where(MediaAsset.entity_type == "team")
    ).all()
    return {
        "players": sorted({int(pid) for pid in player_ids if pid is not None}),
        "teams": sorted({row[0].upper() for row in team_rows}),
    }
