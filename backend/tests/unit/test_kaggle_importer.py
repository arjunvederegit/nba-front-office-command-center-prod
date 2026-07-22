"""Kaggle importer tests.

All sqlite content built here is SYNTHETIC TEST FIXTURE data (clearly fake names
and IDs) — no real Kaggle download ever happens in tests: locate_dataset is
mocked, and import_history is fed a tiny local nba.sqlite built in tmp_path."""

import sqlite3
from datetime import date
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import DataQualityIssue, DataSource, DataSyncRun, Player
from app.integrations.kaggle_nba import importer
from app.integrations.kaggle_nba.importer import import_history, inspect_schema
from tests.conftest import make_player

# Synthetic person_ids — deliberately outside any real NBA id range.
FAKE_PID_A = 9_900_001
FAKE_PID_B = 9_900_002
FAKE_PID_UNKNOWN = 9_900_999


def build_fake_sqlite(
    tmp_path: Path,
    *,
    include_draft: bool = True,
    include_common: bool = True,
    draft_rows: list[tuple] | None = None,
    common_rows: list[tuple] | None = None,
) -> Path:
    """Build a tiny synthetic nba.sqlite mimicking the Kaggle schema subset we read."""
    path = tmp_path / "nba.sqlite"
    conn = sqlite3.connect(path)
    if include_draft:
        conn.execute(
            "CREATE TABLE draft_history ("
            "person_id INTEGER, player_name TEXT, season TEXT, "
            "round_number TEXT, overall_pick TEXT)"
        )
        conn.executemany(
            "INSERT INTO draft_history VALUES (?, ?, ?, ?, ?)",
            draft_rows
            if draft_rows is not None
            else [
                (FAKE_PID_A, "Synthetic Fixture Alpha", "2019", "1", "7"),
                (FAKE_PID_B, "Synthetic Fixture Beta", "2016", "2", "35"),
                (FAKE_PID_UNKNOWN, "Synthetic Fixture Nobody", "2010", "1", "1"),
            ],
        )
    if include_common:
        conn.execute(
            "CREATE TABLE common_player_info ("
            "person_id INTEGER, display_first_last TEXT, birthdate TEXT, "
            "height TEXT, weight TEXT)"
        )
        conn.executemany(
            "INSERT INTO common_player_info VALUES (?, ?, ?, ?, ?)",
            common_rows
            if common_rows is not None
            else [
                (FAKE_PID_A, "Synthetic Fixture Alpha", "1997-05-01 00:00:00", "6-7", "215"),
                (FAKE_PID_B, "Synthetic Fixture Beta", "1994-11-20 00:00:00", "6-10", "240"),
            ],
        )
    conn.commit()
    conn.close()
    return path


def _runs(db: Session) -> list[DataSyncRun]:
    return list(
        db.scalars(select(DataSyncRun).where(DataSyncRun.job_name == "import_kaggle_history"))
    )


def _issues(db: Session, check_name: str) -> list[DataQualityIssue]:
    return list(
        db.scalars(select(DataQualityIssue).where(DataQualityIssue.check_name == check_name))
    )


def test_inspect_schema(tmp_path: Path) -> None:
    path = build_fake_sqlite(tmp_path)
    schema = inspect_schema(path)
    assert set(schema) == {"draft_history", "common_player_info"}
    assert "person_id" in schema["draft_history"]
    assert "overall_pick" in schema["draft_history"]
    assert schema["common_player_info"][:2] == ["person_id", "display_first_last"]


def test_enrichment_fills_only_null_fields(db: Session, tmp_path: Path) -> None:
    player = make_player(db, FAKE_PID_A, "Synthetic Fixture Alpha", birth_date=None)
    assert player.draft_year is None and player.weight_lbs is None
    existing_height = player.height_inches  # 78, set by fixture — must survive

    summary = import_history(db, sqlite_path=build_fake_sqlite(tmp_path))

    assert summary["status"] == "succeeded"
    db.refresh(player)
    assert player.draft_year == 2019
    assert player.draft_round == 1
    assert player.draft_number == 7
    assert player.birth_date == date(1997, 5, 1)
    assert player.weight_lbs == 215
    # Non-NULL nba_api-sourced value is never overwritten (kaggle says 6-7 == 79).
    assert player.height_inches == existing_height
    assert summary["tables"]["draft_history"]["matched"] == 1
    assert summary["tables"]["common_player_info"]["matched"] == 1


def test_existing_values_never_overwritten_and_conflict_recorded(
    db: Session, tmp_path: Path
) -> None:
    player = make_player(db, FAKE_PID_B, "Synthetic Fixture Beta", birth_date=date(1994, 11, 20))
    player.draft_year = 2017  # disagrees with the synthetic kaggle row (2016)
    player.weight_lbs = 240  # agrees with kaggle — must not be a conflict
    db.commit()

    summary = import_history(db, sqlite_path=build_fake_sqlite(tmp_path))

    db.refresh(player)
    assert player.draft_year == 2017  # kaggle value NOT applied
    conflicts = _issues(db, "kaggle_source_conflict")
    assert len(conflicts) >= 1
    assert any(f"player:{FAKE_PID_B}" == issue.entity for issue in conflicts)
    assert any("draft_year" in issue.message for issue in conflicts)
    # height 6-10 == 82 vs fixture 78 is also a conflict; matching values are not.
    assert all("weight_lbs" not in issue.message for issue in conflicts)
    assert summary["conflicts"] == len(conflicts)


def test_unavailable_returns_status_with_succeeded_run(db: Session, monkeypatch) -> None:
    monkeypatch.setattr(importer, "locate_dataset", lambda download=True: None)

    result = import_history(db)

    assert result["status"] == "unavailable"
    assert "kagglehub" in result["hint"] or "Kaggle" in result["hint"]
    runs = _runs(db)
    assert len(runs) == 1
    assert runs[0].status == "succeeded"  # absence is an honest state, not a failure
    assert "not available" in runs[0].detail["note"]


def test_missing_tables_handled_gracefully(db: Session, tmp_path: Path) -> None:
    make_player(db, FAKE_PID_A, "Synthetic Fixture Alpha")
    path = build_fake_sqlite(tmp_path, include_draft=False, include_common=False)
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE unrelated_table (x INTEGER)")
    conn.commit()
    conn.close()

    summary = import_history(db, sqlite_path=path)

    assert summary["status"] == "succeeded"
    assert sorted(summary["missing_tables"]) == ["common_player_info", "draft_history"]
    assert summary["tables"] == {}
    assert _runs(db)[0].status == "succeeded"


def test_unparseable_rows_rejected_and_recorded(db: Session, tmp_path: Path) -> None:
    player = make_player(db, FAKE_PID_A, "Synthetic Fixture Alpha")
    path = build_fake_sqlite(
        tmp_path,
        draft_rows=[
            ("not-a-number", "Synthetic Fixture Broken", "2019", "1", "7"),
            (FAKE_PID_A, "Synthetic Fixture Alpha", "unknown", "1", "7"),
        ],
        include_common=False,
    )

    summary = import_history(db, sqlite_path=path)

    db.refresh(player)
    assert player.draft_year is None  # "unknown" was rejected, never guessed
    assert player.draft_round == 1  # parseable fields on the same row still fill
    counts = summary["tables"]["draft_history"]
    assert counts["rejected"] == 2  # bad person_id + bad season
    rejects = _issues(db, "kaggle_unparseable_row")
    assert len(rejects) == 1
    assert "draft_history" in rejects[0].message


def test_unmatched_players_skipped(db: Session, tmp_path: Path) -> None:
    summary = import_history(db, sqlite_path=build_fake_sqlite(tmp_path))
    counts = summary["tables"]["draft_history"]
    assert counts["rows"] == 3
    assert counts["matched"] == 0
    assert counts["players_updated"] == 0
    assert db.scalars(select(Player)).all() == []


def test_data_source_registered_with_checksum(db: Session, tmp_path: Path) -> None:
    path = build_fake_sqlite(tmp_path)
    import_history(db, sqlite_path=path)

    source = db.scalar(select(DataSource).where(DataSource.name == "kaggle_basketball"))
    assert source is not None
    assert source.upstream == "wyattowalsh/basketball"
    assert source.notes is not None
    assert str(path) in source.notes
    assert "sha256_first_1mb=" in source.notes
    # Re-import updates the registration instead of duplicating it.
    import_history(db, sqlite_path=path)
    rows = db.scalars(select(DataSource).where(DataSource.name == "kaggle_basketball")).all()
    assert len(rows) == 1


def test_locate_dataset_returns_none_on_download_failure(monkeypatch) -> None:
    import sys
    import types

    fake = types.ModuleType("kagglehub")

    def _boom(handle: str) -> str:
        raise ConnectionError("synthetic network failure (test)")

    fake.dataset_download = _boom  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "kagglehub", fake)

    assert importer.locate_dataset(download=True) is None


def test_import_history_accepts_directory_path(db: Session, tmp_path: Path) -> None:
    make_player(db, FAKE_PID_A, "Synthetic Fixture Alpha", birth_date=None)
    build_fake_sqlite(tmp_path)

    summary = import_history(db, sqlite_path=tmp_path)  # directory containing nba.sqlite

    assert summary["status"] == "succeeded"
    assert summary["players_updated"] == 1
