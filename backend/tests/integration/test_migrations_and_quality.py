"""Migration round-trip and data-quality checks."""

from datetime import UTC, datetime

from alembic.config import Config

from alembic import command
from app.config import BACKEND_DIR
from app.db.models import Contract, ContractYear, PlayerSeasonStats
from app.ingestion.quality import validate_data
from tests.conftest import make_player, make_team


def test_alembic_upgrade_head_on_fresh_database(tmp_sqlite_url, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", tmp_sqlite_url)
    from app.config import get_settings

    get_settings.cache_clear()
    try:
        config = Config(str(BACKEND_DIR / "alembic.ini"))
        config.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
        command.upgrade(config, "head")

        from sqlalchemy import create_engine, inspect

        inspector = inspect(create_engine(tmp_sqlite_url))
        tables = set(inspector.get_table_names())
        for expected in (
            "teams",
            "players",
            "rosters",
            "trade_proposals",
            "league_cap_parameters",
            "data_sync_runs",
        ):
            assert expected in tables
    finally:
        get_settings.cache_clear()


def test_quality_checks_flag_and_resolve_issues(db, cap_params, monkeypatch):
    # cap_params fixture is for 2026-27; quality checks look at the current season —
    # missing 2025-26 params should be flagged.
    team = make_team(db, 1, "AAA")
    player = make_player(db, 100, "Fixture Guy", team, salary=50_000)
    db.add(
        PlayerSeasonStats(
            player_id=player.id,
            season="2025-26",
            stat_type="base",
            games_played=50,
            minutes=-3.0,
            stats={},
        )
    )
    contract = db.query(Contract).filter_by(player_id=player.id).one()
    db.add(ContractYear(contract_id=contract.id, season="1999-XX", salary=-5))
    db.commit()

    issues = validate_data(db)
    checks = {i["check"] for i in issues}
    assert "team_count" in checks  # only 1 team, not 30
    assert "negative_minutes" in checks
    assert "impossible_salary" in checks
    assert "cap_parameters_missing" in checks

    # A second pass resolves the previous open issues and re-detects current ones
    from app.db.models import DataQualityIssue

    validate_data(db)
    open_rows = db.query(DataQualityIssue).filter(DataQualityIssue.resolved_at.is_(None)).all()
    resolved_rows = (
        db.query(DataQualityIssue).filter(DataQualityIssue.resolved_at.isnot(None)).all()
    )
    assert open_rows and resolved_rows


def test_stale_detection(db, cap_params):
    from datetime import timedelta

    from app.db.models import Standing

    team = make_team(db, 1, "AAA")
    db.add(
        Standing(
            team_id=team.id,
            season="2025-26",
            wins=41,
            losses=41,
            win_pct=0.5,
            source_retrieved_at=datetime.now(UTC) - timedelta(days=30),
        )
    )
    db.commit()
    issues = validate_data(db)
    assert any(i["check"] == "stale_records" for i in issues)
