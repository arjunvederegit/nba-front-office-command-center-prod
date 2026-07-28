"""The demo seed is what makes the CI end-to-end gate runnable, so it is tested like
production code: identity provenance, synthetic labelling, and the refusal that stops it
contaminating a real database.
"""

from datetime import UTC, datetime

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import (
    Player,
    PlayerSeasonStats,
    RosterEntry,
    Standing,
    Team,
    TeamSeasonStats,
)
from app.ingestion.demo_seed import (
    DEMO_PROVIDER,
    PLAYERS_PER_TEAM,
    STATIC_PROVIDER,
    DemoSeedRefused,
    seed_demo,
)


def test_seeds_thirty_real_teams_and_a_full_synthetic_league(db: Session) -> None:
    summary = seed_demo(db, seasons=("2024-25", "2025-26"))
    assert summary["teams"] == 30
    assert summary["players"] == 30 * PLAYERS_PER_TEAM

    assert db.scalar(select(func.count()).select_from(Team)) == 30
    assert db.scalar(select(func.count()).select_from(RosterEntry)) == 450
    assert db.scalar(select(func.count()).select_from(Standing)) == 30
    assert db.scalar(select(func.count()).select_from(TeamSeasonStats)) == 60

    boston = db.scalar(select(Team).where(Team.abbreviation == "BOS"))
    assert boston is not None
    assert boston.full_name == "Boston Celtics"
    assert boston.nba_team_id == 1610612738


def test_team_identity_is_provider_backed_and_the_rest_is_labelled_synthetic(
    db: Session,
) -> None:
    seed_demo(db, seasons=("2025-26",))
    providers = {p for (p,) in db.execute(select(Team.source_provider).distinct())}
    assert providers == {STATIC_PROVIDER}, "team identity must be attributed to nba_api's static table"

    for model in (Player, RosterEntry, PlayerSeasonStats, Standing, TeamSeasonStats):
        distinct = {p for (p,) in db.execute(select(model.source_provider).distinct())}
        assert distinct == {DEMO_PROVIDER}, f"{model.__tablename__} must be labelled synthetic"

    names = [n for (n,) in db.execute(select(Player.full_name))]
    assert all(n.startswith("Demo ") for n in names), "synthetic players must be named as such"


def test_refuses_to_seed_a_database_holding_real_provider_rows(db: Session) -> None:
    db.add(
        Team(
            nba_team_id=1610612738,
            full_name="Boston Celtics",
            abbreviation="BOS",
            nickname="Celtics",
            city="Boston",
            source_provider="nba_api",
            source_retrieved_at=datetime.now(UTC),
        )
    )
    db.commit()
    with pytest.raises(DemoSeedRefused):
        seed_demo(db)


def test_is_idempotent(db: Session) -> None:
    seed_demo(db, seasons=("2025-26",))
    again = seed_demo(db, seasons=("2025-26",))
    assert again["teams"] == 0
    assert db.scalar(select(func.count()).select_from(Team)) == 30


def test_produces_a_frame_the_modelling_path_can_consume(db: Session) -> None:
    """The seed exists to exercise the real pipeline, so the feature builder must find
    varying, non-degenerate rows — otherwise the e2e gate would pass on empty screens."""
    from app.analytics.features import build_player_season_features, recency_weighted_features

    seed_demo(db, seasons=("2024-25", "2025-26"))
    season_df = build_player_season_features(db)
    assert len(season_df) == 900  # 450 players × 2 seasons
    weighted = recency_weighted_features(season_df, ["2024-25", "2025-26"])
    assert len(weighted) == 450
    for column in ("TS_PCT", "USG_PCT", "AST_PCT", "PIE", "NET_RATING"):
        assert weighted[column].nunique() > 5, f"{column} is near-constant in the demo league"
