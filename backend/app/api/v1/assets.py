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
