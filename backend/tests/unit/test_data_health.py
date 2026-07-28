"""Data-health freshness properties.

Pins QA-4 (a local-file job makes six-day-old NBA data read as "fresh") and the
invariant that outlives it: NBA freshness is a property of when NBA.com data was
*retrieved*, never of when some job *finished*.
"""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.orm import Session

from app.db.models import DataSyncRun, RosterEntry, Standing, Team
from app.services.data_health import data_health


def _nba_tables(health: dict) -> dict[str, dict]:
    return {
        name: health["tables"][name]
        for name in ("rosters", "standings", "player_season_stats", "team_season_stats", "teams")
        if name in health["tables"]
    }


@pytest.fixture()
def stale_nba_data(db: Session) -> Team:
    """NBA data retrieved six days ago, plus a local-file job that succeeded seconds ago."""
    now = datetime.now(UTC)
    long_ago = now - timedelta(days=6)
    team = Team(
        nba_team_id=1,
        full_name="Alpha Test Club",
        abbreviation="AAA",
        nickname="AAA",
        city="Testville",
        source_provider="nba_api",
        source_retrieved_at=long_ago,
    )
    db.add(team)
    db.flush()
    db.add(
        Standing(
            team_id=team.id,
            season="2025-26",
            wins=41,
            losses=41,
            win_pct=0.5,
            conference="East",
            source_provider="nba_api",
            source_retrieved_at=long_ago,
        )
    )
    db.add(
        DataSyncRun(
            job_name="sync_rosters",
            status="succeeded",
            started_at=long_ago,
            finished_at=long_ago,
            rows_written=530,
        )
    )
    # The local asset indexer touched no NBA.com data but finished moments ago.
    db.add(
        DataSyncRun(
            job_name="index_assets",
            status="succeeded",
            started_at=now - timedelta(minutes=2),
            finished_at=now - timedelta(minutes=1),
            rows_written=2478,
        )
    )
    db.commit()
    return team


def test_local_asset_job_does_not_refresh_nba_data(db: Session, stale_nba_data: Team) -> None:
    health = data_health(db)
    card = next(c for c in health["source_cards"] if c["key"] == "current_nba_data")
    assert card["status"] == "stale"


def test_nba_freshness_is_never_true_while_an_nba_table_is_stale(
    db: Session, stale_nba_data: Team
) -> None:
    health = data_health(db)
    card = next(c for c in health["source_cards"] if c["key"] == "current_nba_data")
    stale_tables = [n for n, t in _nba_tables(health).items() if t["stale"] is True]
    assert stale_tables, "the fixture must actually produce stale NBA tables"
    assert card["status"] != "fresh"


def test_freshness_timestamps_share_one_clock(db: Session, stale_nba_data: Team) -> None:
    """A naive timestamp beside tz-aware ones makes the browser parse them on different
    clocks — the same field the freshness fix touches."""
    health = data_health(db)
    last_sync = health["last_successful_sync"]
    assert last_sync is not None
    table_ts = health["tables"]["standings"]["last_retrieved_at"]
    assert table_ts is not None
    assert ("+" in last_sync[10:] or last_sync.endswith("Z")) == (
        "+" in table_ts[10:] or table_ts.endswith("Z")
    ), f"mixed tz-awareness: {last_sync!r} vs {table_ts!r}"


def test_open_quality_issue_total_is_reportable(db: Session, stale_nba_data: Team) -> None:
    """The API caps the issue list at 50 with no total, so the real backlog (562 open
    rows live) is unknowable from the response."""
    health = data_health(db)
    assert "open_quality_issue_total" in health


def test_rosters_row_count_is_reported(db: Session, stale_nba_data: Team) -> None:
    db.add(
        RosterEntry(
            team_id=stale_nba_data.id,
            player_id="00000000-0000-0000-0000-000000000000",
            season="2025-26",
            is_current=True,
            source_provider="nba_api",
            source_retrieved_at=datetime.now(UTC) - timedelta(days=6),
        )
    )
    db.commit()
    assert data_health(db)["tables"]["rosters"]["rows"] == 1


def test_a_csv_import_does_not_pass_for_an_nba_sync(db: Session, stale_nba_data: Team) -> None:
    """The audit suggested reusing `tables['player_season_stats'].last_retrieved_at`, but
    that table also carries CSV-import rows, so the unfiltered maximum is the CSV's
    timestamp — still wrong, by about 25 hours. Freshness filters on the provider."""
    from app.db.models import Player, PlayerSeasonStats

    now = datetime.now(UTC)
    player = Player(nba_player_id=1, full_name="Fixture Player", is_active=True)
    db.add(player)
    db.flush()
    db.add(
        PlayerSeasonStats(
            player_id=player.id,
            season="2025-26",
            stat_type="csv_totals",
            games_played=70,
            minutes=2100.0,
            stats={},
            source_provider="user_csv",
            source_retrieved_at=now,  # imported seconds ago
        )
    )
    db.commit()

    health = data_health(db)
    card = next(c for c in health["source_cards"] if c["key"] == "current_nba_data")
    assert card["status"] == "stale", "a CSV import must not make NBA.com data look fresh"
    assert health["tables"]["player_season_stats"]["stale"] is False  # the CSV row is fresh
    assert health["last_successful_sync"] is not None
    assert health["last_successful_sync"] < now.isoformat()


def test_contracts_distinguish_empty_from_unconfigured(db: Session, stale_nba_data: Team) -> None:
    card = next(c for c in data_health(db)["source_cards"] if c["key"] == "contracts")
    assert card["status"] == "unavailable"
    assert "no contract provider configured" in card["coverage"]


def test_open_issue_totals_report_the_real_backlog(db: Session, stale_nba_data: Team) -> None:
    from app.db.models import DataQualityIssue

    for i in range(60):
        db.add(
            DataQualityIssue(
                check_name="duplicate_name" if i % 2 else "future_dates",
                severity="warning",
                message=f"fixture issue {i}",
                detected_at=datetime.now(UTC),
            )
        )
    db.commit()
    health = data_health(db)
    assert len(health["open_quality_issues"]) == 50
    assert health["open_quality_issue_total"] == 60
    assert health["open_quality_issues_truncated"] is True
    assert health["open_quality_issue_counts"] == {"duplicate_name": 30, "future_dates": 30}
