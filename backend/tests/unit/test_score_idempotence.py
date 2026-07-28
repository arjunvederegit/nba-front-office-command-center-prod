"""`make score` must survive being run twice.

It did not. `score_all` deleted a team's existing `TeamNeed` rows and added the
replacements in the same flush; with `autoflush=False` both landed together, and
SQLAlchemy emits a mapper's INSERTs before its DELETEs, so the second run raised

    UNIQUE constraint failed: team_needs.team_id, team_needs.season, team_needs.need_key

Reproduced on the development database against the code at `f16dedc`. It only ever
worked the first time, which is why a fresh clone never saw it — and why neither the
audit nor the plan caught it.
"""

from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.analytics.score import score_all
from app.db.models import TeamNeed, TeamSeasonStats


def _seed_team_stats(db: Session, teams: list) -> None:
    now = datetime.now(UTC)
    for index, team in enumerate(teams):
        db.add(
            TeamSeasonStats(
                team_id=team.id,
                season="2025-26",
                stat_type="advanced",
                stats={
                    "OFF_RATING": 110.0 + index,
                    "DEF_RATING": 112.0 - index,
                    "NET_RATING": -2.0 + 2 * index,
                    "AST_PCT": 0.58 + index * 0.01,
                    "DREB_PCT": 0.70,
                    "TM_TOV_PCT": 0.13 - index * 0.01,
                    "TS_PCT": 0.56 + index * 0.01,
                },
                source_retrieved_at=now,
            )
        )
        db.add(
            TeamSeasonStats(
                team_id=team.id,
                season="2025-26",
                stat_type="base",
                stats={"FG3A": 30.0 + index * 4, "STL": 7.0, "BLK": 4.5},
                source_retrieved_at=now,
            )
        )
    db.commit()


def test_scoring_twice_produces_the_same_rows(db: Session, seeded_league: dict) -> None:
    _seed_team_stats(db, [seeded_league["team_a"], seeded_league["team_b"]])
    db.query(TeamNeed).delete()
    db.commit()

    first = score_all(db)
    snapshot = {
        (r.team_id, r.need_key): (r.severity, r.percentile)
        for r in db.scalars(select(TeamNeed)).all()
    }
    assert first["needs_written"] > 0

    second = score_all(db)  # this raised IntegrityError before the fix
    assert second["needs_written"] == first["needs_written"]

    again = {
        (r.team_id, r.need_key): (r.severity, r.percentile)
        for r in db.scalars(select(TeamNeed)).all()
    }
    assert again == snapshot
    assert db.scalar(select(func.count()).select_from(TeamNeed)) == len(snapshot)


def test_a_need_that_no_longer_applies_is_removed(db: Session, seeded_league: dict) -> None:
    """Rows are updated in place, so a rule that stops firing must not leave a stale row
    behind claiming the team still has that need."""
    _seed_team_stats(db, [seeded_league["team_a"], seeded_league["team_b"]])
    db.query(TeamNeed).delete()
    db.commit()
    score_all(db)

    db.add(
        TeamNeed(
            team_id=seeded_league["team_a"].id,
            season="2025-26",
            need_key="a_rule_that_no_longer_exists",
            severity=0.9,
            percentile=5.0,
            explanation="stale row from an earlier rule set",
        )
    )
    db.commit()

    score_all(db)
    keys = {
        r.need_key
        for r in db.scalars(
            select(TeamNeed).where(TeamNeed.team_id == seeded_league["team_a"].id)
        ).all()
    }
    assert "a_rule_that_no_longer_exists" not in keys
