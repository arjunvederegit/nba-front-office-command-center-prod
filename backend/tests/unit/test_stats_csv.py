"""Unit tests for the user-supplied season-totals CSV importer.

All rows written here are SYNTHETIC TEST FIXTURES ("Fixture Player ..."), never real
NBA data. The real staged CSV is intentionally not read by tests.
"""

from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import DataQualityIssue, PlayerSeasonStats
from app.ingestion.stats_csv import import_stats_csv
from tests.conftest import make_player, make_team

HEADER = (
    "PLAYER_ID,RANK,PLAYER,TEAM_ID,TEAM,GP,MIN,FGM,FGA,FG_PCT,FG3M,FG3A,FG3_PCT,"
    "FTM,FTA,FT_PCT,OREB,DREB,REB,AST,STL,BLK,TOV,PF,PTS,EFF,AST_TOV,STL_TOV"
)
COLUMNS = HEADER.split(",")

BASE_ROW = {
    "PLAYER_ID": "900001",
    "RANK": "1",
    "PLAYER": "Fixture Player A",
    "TEAM_ID": "1",
    "TEAM": "AAA",
    "GP": "4",
    "MIN": "100",
    "FGM": "20",
    "FGA": "40",
    "FG_PCT": "0.5",
    "FG3M": "4",
    "FG3A": "10",
    "FG3_PCT": "0.4",
    "FTM": "6",
    "FTA": "8",
    "FT_PCT": "0.75",
    "OREB": "4",
    "DREB": "12",
    "REB": "16",
    "AST": "10",
    "STL": "5",
    "BLK": "3",
    "TOV": "8",
    "PF": "9",
    "PTS": "50",
    "EFF": "60",
    "AST_TOV": "1.25",
    "STL_TOV": "0.63",
}


def _row(**overrides: str) -> str:
    values = {**BASE_ROW, **overrides}
    return ",".join(values[column] for column in COLUMNS)


def _write_csv(tmp_path: Path, rows: list[str], header: str = HEADER) -> str:
    path = tmp_path / "fixture_stats.csv"
    path.write_text("\n".join([header, *rows]) + "\n", encoding="utf-8")
    return str(path)


def test_happy_path_import(db: Session, tmp_path: Path) -> None:
    team = make_team(db, 1, "AAA")
    player_a = make_player(db, 900001, "Fixture Player A", team)
    make_player(db, 900002, "Fixture Player B", team)
    csv_path = _write_csv(
        tmp_path,
        [
            _row(),
            _row(PLAYER_ID="900002", RANK="2", PLAYER="Fixture Player B", GP="2", PTS="31"),
        ],
    )

    result = import_stats_csv(db, csv_path, season="2025-26")

    assert result == {
        "rows": 2,
        "imported": 2,
        "unmatched": 0,
        "rejected": 0,
        "season": "2025-26",
    }
    stat = db.scalar(select(PlayerSeasonStats).where(PlayerSeasonStats.player_id == player_a.id))
    assert stat is not None
    assert stat.season == "2025-26"
    assert stat.stat_type == "totals"
    assert stat.games_played == 4
    assert stat.minutes == 100.0
    assert stat.team_id == team.id
    assert stat.stats["PTS"] == 50
    assert stat.stats["REB"] == 16
    assert stat.stats["rates"]["FG_PCT"] == 0.5
    assert stat.stats["rates"]["AST_TOV"] == 1.25
    assert stat.stats["source_file"] == "fixture_stats.csv"
    assert stat.source_provider == "user_import_csv"
    assert stat.source_record_id == "900001:2025-26:totals"
    assert stat.source_retrieved_at is not None
    assert stat.ingestion_run_id is not None


def test_per_game_derivation(db: Session, tmp_path: Path) -> None:
    team = make_team(db, 1, "AAA")
    player = make_player(db, 900001, "Fixture Player A", team)
    csv_path = _write_csv(tmp_path, [_row()])

    import_stats_csv(db, csv_path)

    stat = db.scalar(select(PlayerSeasonStats).where(PlayerSeasonStats.player_id == player.id))
    assert stat is not None
    assert stat.stats["per_game"] == {
        "MIN": 25.0,
        "PTS": 12.5,
        "REB": 4.0,
        "AST": 2.5,
        "STL": 1.25,
        "BLK": 0.75,
        "TOV": 2.0,
        "FGA": 10.0,
        "FG3A": 2.5,
        "FG3M": 1.0,
        "FTA": 2.0,
        # R7: a season total the source may omit is divided by GP like any other total.
        "EFF": 15.0,
    }


def test_unmatched_player_recorded_not_imported(db: Session, tmp_path: Path) -> None:
    team = make_team(db, 1, "AAA")
    make_player(db, 900001, "Fixture Player A", team)
    csv_path = _write_csv(
        tmp_path,
        [_row(), _row(PLAYER_ID="999999", PLAYER="Fixture Ghost")],
    )

    result = import_stats_csv(db, csv_path)

    assert result["imported"] == 1
    assert result["unmatched"] == 1
    assert result["rejected"] == 0
    assert len(db.scalars(select(PlayerSeasonStats)).all()) == 1
    issue = db.scalar(
        select(DataQualityIssue).where(DataQualityIssue.check_name == "csv_unmatched_player")
    )
    assert issue is not None
    assert issue.severity == "warning"
    assert "Fixture Ghost" in issue.message
    assert "999999" in issue.message


def test_implausible_gp_rejected(db: Session, tmp_path: Path) -> None:
    team = make_team(db, 1, "AAA")
    make_player(db, 900001, "Fixture Player A", team)
    make_player(db, 900002, "Fixture Player B", team)
    csv_path = _write_csv(
        tmp_path,
        [
            _row(GP="0"),  # below 1..82
            _row(PLAYER_ID="900002", PLAYER="Fixture Player B", GP="99"),  # above 1..82
        ],
    )

    result = import_stats_csv(db, csv_path)

    assert result["imported"] == 0
    assert result["rejected"] == 2
    assert db.scalars(select(PlayerSeasonStats)).all() == []
    issues = db.scalars(
        select(DataQualityIssue).where(DataQualityIssue.check_name == "csv_implausible_value")
    ).all()
    assert len(issues) == 2
    assert all("GP" in issue.message for issue in issues)


def test_implausible_percentage_rejected(db: Session, tmp_path: Path) -> None:
    team = make_team(db, 1, "AAA")
    make_player(db, 900001, "Fixture Player A", team)
    csv_path = _write_csv(tmp_path, [_row(FG_PCT="1.5")])

    result = import_stats_csv(db, csv_path)

    assert result["rejected"] == 1
    assert result["imported"] == 0
    assert db.scalars(select(PlayerSeasonStats)).all() == []


def test_missing_column_raises_value_error(db: Session, tmp_path: Path) -> None:
    columns = [c for c in COLUMNS if c not in ("PTS", "GP")]
    header = ",".join(columns)
    row = ",".join(BASE_ROW[c] for c in columns)
    csv_path = _write_csv(tmp_path, [row], header=header)

    with pytest.raises(ValueError, match="GP.*PTS|PTS.*GP"):
        import_stats_csv(db, csv_path)


def test_idempotent_rerun_updates_in_place(db: Session, tmp_path: Path) -> None:
    team = make_team(db, 1, "AAA")
    player = make_player(db, 900001, "Fixture Player A", team)
    first_csv = _write_csv(tmp_path, [_row()])
    import_stats_csv(db, first_csv)
    original = db.scalar(select(PlayerSeasonStats).where(PlayerSeasonStats.player_id == player.id))
    assert original is not None
    original_id = original.id

    updated_csv = _write_csv(tmp_path, [_row(GP="5", PTS="60", MIN="120")])
    result = import_stats_csv(db, updated_csv)

    assert result["imported"] == 1
    rows = db.scalars(select(PlayerSeasonStats)).all()
    assert len(rows) == 1
    assert rows[0].id == original_id
    assert rows[0].games_played == 5
    assert rows[0].minutes == 120.0
    assert rows[0].stats["PTS"] == 60
    assert rows[0].stats["per_game"]["PTS"] == 12.0


# ------------------------------------------------------------------ QA-11 pin (R0-1)


def test_eff_is_scale_dependent_and_belongs_with_totals(db: Session, tmp_path: Path) -> None:
    """QA-11, fixed in R7. `EFF` is a season *total*: 60 over 4 games is 15.0 per game.

    It sat in `_RATE_FIELDS`, so it was copied into `stats["rates"]` and rendered beside
    FG% and 3P% — where every other value is scale-independent — and the per-game view
    showed the season total unchanged.

    Per C12 the move needed a third field category rather than a move into
    `_TOTAL_FIELDS`: those are parsed with `_required_float`, so a blank `EFF` would have
    started rejecting the whole row, which `_RATE_FIELDS`'s `_optional_float` tolerated.
    """
    make_team(db, 1, "AAA")
    make_player(db, 900001, "Fixture Player A")
    path = _write_csv(tmp_path, [_row()])
    import_stats_csv(db, path, season="2025-26")
    stat = db.scalar(select(PlayerSeasonStats).where(PlayerSeasonStats.stat_type == "totals"))
    assert stat is not None
    assert "EFF" not in stat.stats["rates"], "EFF is not scale-independent"
    assert stat.stats["EFF"] == 60, "the season total is kept where the other totals are"
    assert stat.stats["per_game"]["EFF"] == 15.0


def test_a_blank_eff_does_not_reject_the_row(db: Session, tmp_path: Path) -> None:
    """The reason the third category exists. `EFF` is optional in the source, and a stat
    the source may omit must not become a reason to drop a player's whole season."""
    make_team(db, 1, "AAA")
    make_player(db, 900001, "Fixture Player A")
    path = _write_csv(tmp_path, [_row(EFF="")])
    result = import_stats_csv(db, path, season="2025-26")

    assert result == {**result, "imported": 1, "rejected": 0}
    stat = db.scalar(select(PlayerSeasonStats).where(PlayerSeasonStats.stat_type == "totals"))
    assert stat is not None
    assert stat.stats["PTS"] == 50, "the rest of the row imported"
    # Absent in the source, absent here — in neither bag, and never zero.
    assert "EFF" not in stat.stats
    assert "EFF" not in stat.stats["per_game"]
    assert "EFF" not in stat.stats["rates"]


def test_the_three_field_categories_do_not_overlap() -> None:
    """Each column is classified exactly once. An `EFF` in two categories is how it came
    to be a rate and a total at the same time."""
    from app.ingestion.stats_csv import (
        _OPTIONAL_TOTAL_FIELDS,
        _RATE_FIELDS,
        _TOTAL_FIELDS,
    )

    assert set(_TOTAL_FIELDS) & set(_RATE_FIELDS) == set()
    assert set(_TOTAL_FIELDS) & set(_OPTIONAL_TOTAL_FIELDS) == set()
    assert set(_RATE_FIELDS) & set(_OPTIONAL_TOTAL_FIELDS) == set()
