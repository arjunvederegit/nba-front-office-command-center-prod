"""Tests for the local media-asset indexer and serving endpoints.

All files and DB records here are SYNTHETIC TEST FIXTURES (fake bytes, fake names);
no real NBA data is fabricated or asserted."""

from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.assets.indexer import coverage, index_assets, normalize_name
from app.config import get_settings
from app.db.models import DataSyncRun, MediaAsset
from tests.conftest import make_player, make_team

PNG_BYTES = b"synthetic-test-png-bytes"
JPG_BYTES = b"synthetic-test-jpg-bytes"


@pytest.fixture()
def asset_dirs(tmp_path: Path, monkeypatch) -> SimpleNamespace:
    logos = tmp_path / "nbalogos"
    players = tmp_path / "nbaplayerimages"
    logos.mkdir()
    players.mkdir()
    settings = get_settings()
    monkeypatch.setattr(settings, "asset_logos_dir", str(logos))
    monkeypatch.setattr(settings, "asset_player_images_dir", str(players))
    return SimpleNamespace(logos=logos, players=players)


def _photo_dir(root: Path, name: str, image_names: tuple[str, ...] = ("Image_1.jpg",)) -> Path:
    folder = root / name
    folder.mkdir()
    for image_name in image_names:
        (folder / image_name).write_bytes(JPG_BYTES)
    return folder


# ------------------------------------------------------------------ normalize_name


def test_normalize_name_strips_diacritics():
    assert normalize_name("Dončić") == "doncic"
    assert normalize_name("Luka Dončić") == "luka doncic"
    assert normalize_name("Nikola Vučević") == "nikola vucevic"


def test_normalize_name_removes_punctuation_and_collapses_spaces():
    assert normalize_name("A.J. Lawson") == "aj lawson"
    assert normalize_name("De'Aaron Fox") == "deaaron fox"
    assert normalize_name("Shai  Gilgeous-Alexander") == "shai gilgeousalexander"


def test_normalize_name_drops_suffix_tokens():
    assert normalize_name("Jaren Jackson Jr.") == "jaren jackson"
    assert normalize_name("Gary Payton II") == "gary payton"
    assert normalize_name("Tim Hardaway Sr") == "tim hardaway"


# ------------------------------------------------------------------------- indexer


def test_index_logos_special_cases_and_unmatched(db: Session, asset_dirs):
    phi = make_team(db, 1, "PHI", "Test Philadelphia Club")
    mia = make_team(db, 2, "MIA", "Test Miami Club")
    (asset_dirs.logos / "phl.png").write_bytes(PNG_BYTES)
    (asset_dirs.logos / "mia.gif").write_bytes(PNG_BYTES)
    (asset_dirs.logos / "zzz.png").write_bytes(PNG_BYTES)
    (asset_dirs.logos / "dataset-metadata.json").write_text("{}")

    summary = index_assets(db)

    assert summary["teams_indexed"] == 2
    assert summary["teams_unmatched"] == 1
    phi_asset = db.scalar(
        select(MediaAsset).where(
            MediaAsset.entity_type == "team", MediaAsset.file_path == "phl.png"
        )
    )
    assert phi_asset is not None
    assert phi_asset.team_id == phi.id
    assert phi_asset.nba_id == phi.nba_team_id
    assert phi_asset.content_type == "image/png"
    assert phi_asset.match_method == "abbreviation"
    assert phi_asset.confidence == "high"
    assert phi_asset.source_label == "phl"
    assert phi_asset.alt_text == "Test Philadelphia Club logo"
    mia_asset = db.scalar(select(MediaAsset).where(MediaAsset.file_path == "mia.gif"))
    assert mia_asset is not None
    assert mia_asset.team_id == mia.id
    assert mia_asset.content_type == "image/gif"
    unmatched = db.scalar(select(MediaAsset).where(MediaAsset.file_path == "zzz.png"))
    assert unmatched is not None
    assert unmatched.confidence == "unmatched"
    assert unmatched.team_id is None
    # dataset-metadata.json is never indexed
    assert (
        db.scalar(select(MediaAsset).where(MediaAsset.file_path == "dataset-metadata.json")) is None
    )
    run = db.scalar(select(DataSyncRun).where(DataSyncRun.job_name == "index_assets"))
    assert run is not None and run.status == "succeeded"


def test_index_players_exact_normalized_unmatched_and_lowest_n(db: Session, asset_dirs):
    exact = make_player(db, 101, "Fixture Exact Player")
    accented = make_player(db, 102, "Tëst Áccented Plâyer")
    # Lowest numeric N wins (Image_2 over Image_10 despite lexicographic order).
    _photo_dir(asset_dirs.players, "Fixture Exact Player", ("Image_2.jpg", "Image_10.jpg"))
    _photo_dir(asset_dirs.players, "Test Accented Player")  # normalized-only match
    _photo_dir(asset_dirs.players, "Totally Unknown Fixture Guy")

    summary = index_assets(db)

    assert summary["player_dirs_scanned"] == 3
    assert summary["players_indexed"] == 2
    assert summary["players_unmatched"] == 1
    exact_asset = db.scalar(select(MediaAsset).where(MediaAsset.nba_id == 101))
    assert exact_asset is not None
    assert exact_asset.file_path == "Fixture Exact Player/Image_2.jpg"
    assert exact_asset.is_primary is True
    assert exact_asset.player_id == exact.id
    assert exact_asset.match_method == "exact_name"
    assert exact_asset.confidence == "high"
    assert exact_asset.alt_text == "Photo of Fixture Exact Player"
    norm_asset = db.scalar(select(MediaAsset).where(MediaAsset.nba_id == 102))
    assert norm_asset is not None
    assert norm_asset.player_id == accented.id
    assert norm_asset.match_method == "normalized_name"
    assert norm_asset.confidence == "medium"
    unmatched = db.scalar(
        select(MediaAsset).where(MediaAsset.source_label == "Totally Unknown Fixture Guy")
    )
    assert unmatched is not None
    assert unmatched.confidence == "unmatched"
    assert unmatched.player_id is None


def test_index_players_prefers_active_and_never_guesses(db: Session, asset_dirs):
    active = make_player(db, 201, "Fixture Shared Name")
    retired = make_player(db, 202, "Fixture Shared Name")
    retired.is_active = False
    make_player(db, 203, "Fixture Twin Name")
    make_player(db, 204, "Fixture Twin Name")  # both active -> ambiguous
    db.commit()
    _photo_dir(asset_dirs.players, "Fixture Shared Name")
    _photo_dir(asset_dirs.players, "Fixture Twin Name")

    summary = index_assets(db)

    assert summary["players_indexed"] == 1
    assert summary["players_unmatched"] == 1
    shared = db.scalar(select(MediaAsset).where(MediaAsset.source_label == "Fixture Shared Name"))
    assert shared is not None
    assert shared.player_id == active.id
    assert shared.nba_id == 201
    twin = db.scalar(select(MediaAsset).where(MediaAsset.source_label == "Fixture Twin Name"))
    assert twin is not None
    assert twin.confidence == "unmatched"
    assert twin.player_id is None


def test_index_assets_is_idempotent(db: Session, asset_dirs):
    make_team(db, 1, "PHI")
    make_player(db, 101, "Fixture Exact Player")
    (asset_dirs.logos / "phl.png").write_bytes(PNG_BYTES)
    _photo_dir(asset_dirs.players, "Fixture Exact Player")
    _photo_dir(asset_dirs.players, "Totally Unknown Fixture Guy")

    first = index_assets(db)
    count_after_first = db.scalars(select(MediaAsset)).all()
    second = index_assets(db)
    count_after_second = db.scalars(select(MediaAsset)).all()

    assert first == second
    assert len(count_after_first) == len(count_after_second) == 3


def test_coverage_math(db: Session, asset_dirs):
    team_a = make_team(db, 1, "PHI")
    make_team(db, 2, "BOS")
    make_player(db, 101, "Fixture Rostered One", team_a)
    make_player(db, 102, "Fixture Rostered Two", team_a)
    make_player(db, 103, "Fixture Unrostered Guy")  # no roster entry -> not in denominator
    (asset_dirs.logos / "phl.png").write_bytes(PNG_BYTES)
    _photo_dir(asset_dirs.players, "Fixture Rostered One")
    _photo_dir(asset_dirs.players, "Fixture Unrostered Guy")
    index_assets(db)

    cov = coverage(db)

    assert cov["team_logo_coverage"] == 0.5  # 1 of 2 teams
    assert cov["teams_total"] == 2
    assert cov["teams_with_logo"] == 1
    assert cov["rostered_players"] == 2
    assert cov["rostered_players_with_photo"] == 1
    assert cov["player_photo_coverage"] == 0.5
    assert cov["players_with_photo"] == 2  # includes the unrostered matched player
    assert cov["unmatched_player_dirs"] == 0


# ----------------------------------------------------------------------- endpoints


@pytest.fixture()
def client(db: Session):
    from app.api.v1.assets import router
    from app.core.errors import DomainError, domain_error_handler
    from app.db.base import get_db

    app = FastAPI()
    app.include_router(router, prefix="/api/v1")
    app.add_exception_handler(DomainError, domain_error_handler)
    app.dependency_overrides[get_db] = lambda: db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def test_team_logo_endpoint_serves_file_with_cache_headers(db, asset_dirs, client):
    make_team(db, 1, "PHI")
    (asset_dirs.logos / "phl.png").write_bytes(PNG_BYTES)
    index_assets(db)

    response = client.get("/api/v1/assets/teams/phi")  # case-insensitive lookup
    assert response.status_code == 200
    assert response.content == PNG_BYTES
    assert response.headers["cache-control"] == "public, max-age=86400"
    assert response.headers["content-type"] == "image/png"

    missing = client.get("/api/v1/assets/teams/ZZZ")
    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "not_found"


def test_player_photo_endpoint_and_404(db, asset_dirs, client):
    make_player(db, 101, "Fixture Exact Player")
    _photo_dir(asset_dirs.players, "Fixture Exact Player")
    _photo_dir(asset_dirs.players, "Totally Unknown Fixture Guy")  # unmatched: not servable
    index_assets(db)

    response = client.get("/api/v1/assets/players/101")
    assert response.status_code == 200
    assert response.content == JPG_BYTES
    assert response.headers["content-type"] == "image/jpeg"
    assert response.headers["cache-control"] == "public, max-age=86400"

    missing = client.get("/api/v1/assets/players/999999")
    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "not_found"


def test_coverage_endpoint(db, asset_dirs, client):
    make_team(db, 1, "PHI")
    (asset_dirs.logos / "phl.png").write_bytes(PNG_BYTES)
    index_assets(db)

    response = client.get("/api/v1/assets/coverage")
    assert response.status_code == 200
    body = response.json()
    assert body["team_logo_coverage"] == 1.0
    assert body["teams_with_logo"] == 1
    assert "generated_at" in body
