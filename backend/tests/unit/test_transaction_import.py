"""The transaction importer resolves what it can and reports what it cannot.

The properties pinned here are the ones that make the corpus safe to reason over: a
franchise this database spells differently still lands on the right team, a name that
matches two players is not resolved by picking one, and a re-import of the same snapshot
produces the same rows rather than duplicating them.
"""

import shutil
from datetime import UTC, datetime
from pathlib import Path

import pytest
from sqlalchemy import select

from app.db.models import (
    DataQualityIssue,
    HistoricalTrade,
    HistoricalTradeAsset,
    PlayerSeasonStats,
)
from app.ingestion.transactions.importer import (
    UNRESOLVED_PLAYER_CHECK,
    _canonical_abbr,
    _resolve_exception_city,
    coverage_summary,
    import_transactions,
)
from tests.conftest import make_player, make_team

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "bbref_transactions_sample.html"


@pytest.fixture()
def snapshot_dir(tmp_path: Path) -> Path:
    target = tmp_path / "transactions"
    target.mkdir()
    shutil.copy(FIXTURE, target / "NBA_2026_transactions.html")
    return target


@pytest.fixture()
def league(db):
    """The nine franchises the fixture names, spelled the way this database spells them."""
    teams = {}
    for index, (abbr, city) in enumerate(
        (
            ("GSW", "Golden State"),
            ("MEM", "Memphis"),
            ("ATL", "Atlanta"),
            ("MIN", "Minnesota"),
            ("HOU", "Houston"),
            ("WAS", "Washington"),
            ("PHX", "Phoenix"),
            ("CHA", "Charlotte"),
            ("DAL", "Dallas"),
            ("BKN", "Brooklyn"),
        )
    ):
        team = make_team(db, 100 + index, abbr, f"{city} Fixtures")
        team.city = city
        teams[abbr] = team
    db.commit()
    return teams


def test_brooklyn_charlotte_and_phoenix_are_aliased_not_guessed():
    assert _canonical_abbr("BRK") == "BKN"
    assert _canonical_abbr("CHO") == "CHA"
    assert _canonical_abbr("PHO") == "PHX"
    # Anything else passes through unchanged rather than being prefix-matched.
    assert _canonical_abbr("XYZ") == "XYZ"


def test_import_writes_directed_asset_legs(db, league, snapshot_dir):
    summary = import_transactions(db, str(snapshot_dir))
    assert summary["trades_imported"] == 4
    assert summary["multi_team_trades"] == 1
    trades = db.scalars(select(HistoricalTrade)).all()
    assert len(trades) == 4

    multi = next(t for t in trades if t.n_teams == 3)
    legs = {(a.from_abbreviation, a.to_abbreviation) for a in multi.assets}
    assert legs == {("HOU", "WAS"), ("WAS", "PHX"), ("PHX", "HOU")}
    assert all(a.from_team_id and a.to_team_id for a in multi.assets)


def test_an_unresolvable_name_is_recorded_as_unresolved_and_filed(db, league, snapshot_dir):
    summary = import_transactions(db, str(snapshot_dir))
    # No fixture player exists in this database, so nothing resolves — and nothing is
    # guessed at either.
    assert summary["player_legs"] > 0
    assert summary["player_legs_resolved"] == 0
    assert summary["resolution_methods"] == {"none": summary["player_legs"]}
    legs = db.scalars(
        select(HistoricalTradeAsset).where(HistoricalTradeAsset.asset_type == "player")
    ).all()
    assert all(a.player_id is None and a.player_name and a.resolution_method == "none" for a in legs)
    issues = db.scalars(
        select(DataQualityIssue).where(DataQualityIssue.check_name == UNRESOLVED_PLAYER_CHECK)
    ).all()
    assert len(issues) == summary["player_legs_unresolved"]


def test_a_name_present_in_this_database_resolves_and_records_the_method(db, league, snapshot_dir):
    make_player(db, 9001, "Fixture Charlie", league["MEM"])
    summary = import_transactions(db, str(snapshot_dir))
    leg = db.scalar(
        select(HistoricalTradeAsset).where(HistoricalTradeAsset.player_name == "Fixture Charlie")
    )
    assert leg.player_id is not None
    assert leg.resolution_method == "exact_name"
    assert summary["player_legs_resolved"] == 1


def test_a_duplicated_name_is_ambiguous_not_a_coin_flip(db, league, snapshot_dir):
    make_player(db, 9002, "Fixture Charlie", league["MEM"])
    make_player(db, 9003, "Fixture Charlie", None)
    summary = import_transactions(db, str(snapshot_dir))
    leg = db.scalar(
        select(HistoricalTradeAsset).where(HistoricalTradeAsset.player_name == "Fixture Charlie")
    )
    # Neither player recorded a 2025-26 season, so the season tie-break cannot separate
    # them and the leg stays unresolved.
    assert leg.player_id is None
    assert leg.resolution_method == "ambiguous"
    assert summary["player_legs_resolved"] == 0


def test_the_season_tiebreak_prefers_the_player_who_played_that_season(db, league, snapshot_dir):
    played = make_player(db, 9004, "Fixture Charlie", league["MEM"])
    make_player(db, 9005, "Fixture Charlie", None)
    db.add(
        PlayerSeasonStats(
            player_id=played.id,
            season="2025-26",
            stat_type="base",
            games_played=70,
            minutes=30.0,
            stats={},
            source_retrieved_at=datetime.now(UTC),
        )
    )
    db.commit()
    import_transactions(db, str(snapshot_dir))
    leg = db.scalar(
        select(HistoricalTradeAsset).where(HistoricalTradeAsset.player_name == "Fixture Charlie")
    )
    assert leg.player_id == played.id
    assert leg.resolution_method == "exact_name+roster"


def test_reimport_is_idempotent(db, league, snapshot_dir):
    first = import_transactions(db, str(snapshot_dir))
    ids = sorted(t.source_record_id for t in db.scalars(select(HistoricalTrade)).all())
    second = import_transactions(db, str(snapshot_dir))
    assert second["trades_imported"] == first["trades_imported"]
    assert sorted(t.source_record_id for t in db.scalars(select(HistoricalTrade)).all()) == ids
    assert db.scalar(select(HistoricalTradeAsset).where(HistoricalTradeAsset.id.is_(None))) is None
    assert coverage_summary(db)["trades"] == 4


def test_an_unparsed_asset_phrase_is_preserved_on_the_trade(db, league, snapshot_dir):
    (snapshot_dir / "NBA_2026_transactions.html").write_text(
        '<ul><li><span>February 5, 2026</span><p>The '
        '<a data-attr-from="GSW" href="/teams/GSW/2026.html">Golden State</a> traded '
        '<a href="/players/a/a01.html">Someone</a> and a 2031 draft pick to the '
        '<a data-attr-to="MEM" href="/teams/MEM/2026.html">Memphis</a> for cash.</p></li></ul>',
        encoding="utf-8",
    )
    import_transactions(db, str(snapshot_dir))
    trade = db.scalar(select(HistoricalTrade))
    assert trade.unparsed_assets == ["a 2031 draft pick"]
    assert "a 2031 draft pick" in trade.source_text


def test_a_city_naming_two_participants_resolves_to_neither(db, league):
    lakers = make_team(db, 200, "LAL", "Los Angeles Lakers")
    clippers = make_team(db, 201, "LAC", "Los Angeles Clippers")
    lakers.city = clippers.city = "Los Angeles"
    db.commit()
    assert _resolve_exception_city("Los Angeles", [lakers, clippers]) is None
    assert _resolve_exception_city("Los Angeles", [lakers, league["MEM"]]) is lakers
    # A note that ran an abbreviation together with the city still resolves on the city.
    assert _resolve_exception_city("DET Memphis", [league["MEM"], lakers]) is league["MEM"]


def test_missing_snapshots_are_an_error_not_an_empty_success(db, tmp_path):
    summary = import_transactions(db, str(tmp_path / "nothing"))
    assert "error" in summary and summary["imported"] == 0
    assert db.scalar(select(HistoricalTrade)) is None
