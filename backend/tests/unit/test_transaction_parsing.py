"""The transaction parser reads what the source says, and refuses the rest.

Every assertion here is about a shape that actually occurs in the ten-season corpus:
multi-team legs, a pick annotated with who it became, a franchise abbreviation this
database spells differently, an asset phrase with no grammar, and a note that cannot be
bound to one pick.
"""

from datetime import date
from pathlib import Path

import pytest

from app.ingestion.transactions.parse import (
    _split_assets,
    parse_season_page,
    parse_trade_paragraph,
    split_sentence_and_notes,
)

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "bbref_transactions_sample.html"


@pytest.fixture()
def parsed():
    trades, report = parse_season_page(FIXTURE.read_text(encoding="utf-8"), "2025-26")
    return trades, report


def test_only_trade_paragraphs_become_trades(parsed):
    trades, report = parsed
    # Five transactions in the fixture, one of which is a free-agent signing.
    assert report.paragraphs == 5
    assert report.trade_paragraphs == 4
    assert report.trades_parsed == 4
    assert report.trades_unparsed == []
    assert len(trades) == 4


def test_two_team_trade_splits_into_two_directed_legs(parsed):
    trades, _ = parsed
    trade = trades[0]
    assert trade.transaction_date == date(2025, 7, 6)
    assert trade.n_teams == 2
    assert trade.team_abbrs == ("GSW", "MEM")
    out_leg = next(leg for leg in trade.legs if leg.from_abbr == "GSW")
    back_leg = next(leg for leg in trade.legs if leg.from_abbr == "MEM")
    assert [p.name for p in out_leg.players] == ["Fixture Alpha", "Fixture Bravo"]
    assert [(p.draft_year, p.round_number) for p in out_leg.picks] == [(2032, 2)]
    assert [p.name for p in back_leg.players] == ["Fixture Charlie"]
    assert back_leg.picks == ()


def test_cash_is_an_asset_and_not_a_player(parsed):
    trades, _ = parsed
    trade = trades[1]
    atl = next(leg for leg in trade.legs if leg.from_abbr == "ATL")
    assert atl.cash is True
    assert atl.players == ()
    assert [(p.draft_year, p.round_number) for p in atl.picks] == [(2027, 2)]


def test_a_conditional_note_is_read_from_the_source_not_assumed(parsed):
    trades, _ = parsed
    trade = trades[1]
    pick = next(p for leg in trade.legs for p in leg.picks)
    assert pick.conveyance == "conditional"
    assert pick.note_text is not None and "conditional" in pick.note_text
    assert trade.trade_exception_cities == ("Minnesota",)


def test_multi_team_trade_keeps_every_leg_and_its_direction(parsed):
    trades, _ = parsed
    trade = trades[2]
    assert trade.is_multi_team and trade.n_teams == 3
    assert trade.team_abbrs == ("HOU", "PHO", "WAS")
    directions = sorted((leg.from_abbr, leg.to_abbr) for leg in trade.legs)
    assert directions == [("HOU", "WAS"), ("PHO", "HOU"), ("WAS", "PHO")]


def test_a_player_named_inside_a_pick_annotation_is_not_a_traded_player(parsed):
    trades, _ = parsed
    trade = trades[2]
    names = {p.name for leg in trade.legs for p in leg.players}
    assert "Fixture Golf" not in names
    annotated = next(
        p for leg in trade.legs for p in leg.picks if p.draft_year == 2026
    )
    assert annotated.later_selected == "Fixture Golf"


def test_two_picks_of_the_same_year_and_round_flag_the_binding_as_ambiguous(parsed):
    trades, _ = parsed
    trade = trades[3]
    picks = [p for leg in trade.legs for p in leg.picks]
    assert len(picks) == 2
    assert all(p.draft_year == 2028 and p.round_number == 1 for p in picks)
    assert all(p.note_binding_ambiguous for p in picks)
    # Both notes are attached, because neither can be assigned to one pick.
    assert all("protected" in (p.note_text or "") for p in picks)
    assert {p.conveyance for p in picks} == {"protected"}


def test_draft_rights_are_a_player_leg_flagged_as_such(parsed):
    trades, _ = parsed
    trade = trades[3]
    leg = next(leg for leg in trade.legs if leg.from_abbr == "DAL")
    assert [(p.name, p.via_draft_rights) for p in leg.players] == [("Fixture Juliett", True)]


def test_the_source_sentence_is_kept_verbatim(parsed):
    trades, _ = parsed
    assert trades[0].source_text.startswith("The GSW traded Fixture Alpha")
    assert "Fixture Charlie" in trades[0].source_text


# ------------------------------------------------------------------ unit-level shapes


def test_notes_split_survives_a_single_space_which_is_the_pre_2022_format():
    marked = (
        "The «FROM:DAL» traded «P:x:A.J. Griffin» to the «TO:GSW» for a 2020 2nd round "
        "draft pick (Tyrell Terry was later selected). DAL has choice between GSW own"
    )
    body, notes = split_sentence_and_notes(marked)
    assert body.endswith("(Tyrell Terry was later selected).")
    assert notes == "DAL has choice between GSW own"


def test_a_period_inside_a_name_or_an_annotation_does_not_end_the_sentence():
    marked = "The «FROM:AAA» traded «P:x:Vince Williams Jr.» to the «TO:BBB»."
    body, notes = split_sentence_and_notes(marked)
    assert body == marked
    assert notes == ""


def test_asset_splitting_does_not_break_inside_a_parenthesis():
    items = _split_assets(
        "«P:a:One», a 2026 1st round draft pick (Somebody, Jr. was later selected) "
        "and «P:b:Two»"
    )
    assert len(items) == 3
    assert items[1].startswith("a 2026 1st round draft pick (")


def test_a_phrase_the_grammar_cannot_read_is_kept_not_dropped():
    marked = (
        "The «FROM:AAA» traded «P:a:One» and a 2031 draft pick to the «TO:BBB» "
        "for «P:b:Two»."
    )
    trade = parse_trade_paragraph(marked, date(2026, 2, 1), "2025-26")
    assert trade is not None
    assert trade.unparsed_assets == ("a 2031 draft pick",)
    # The rest of the trade still parses; only the unreadable phrase is set aside.
    assert {p.name for leg in trade.legs for p in leg.players} == {"One", "Two"}


def test_a_non_trade_paragraph_returns_none():
    marked = "The «FROM:AAA» signed «P:a:One» as a free agent."
    assert parse_trade_paragraph(marked, date(2026, 2, 1), "2025-26") is None
