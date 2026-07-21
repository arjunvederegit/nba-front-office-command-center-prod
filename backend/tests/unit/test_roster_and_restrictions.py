"""Roster-size, recently-signed, no-trade and two-way rules."""

from datetime import date

from app.cba.builder import build_trade_context
from app.cba.rules.restrictions import (
    NoTradeClauseRule,
    RecentlySignedRule,
    TwoWayExclusionRule,
)
from app.cba.rules.roster import RosterSizeRule
from tests.conftest import make_player, make_team


def _swap_context(db, team_a, team_b, players_a, players_b, league_year="2026-27"):
    moves = [
        {"player_id": p.id, "from_team_id": team_a.id, "to_team_id": team_b.id} for p in players_a
    ] + [{"player_id": p.id, "from_team_id": team_b.id, "to_team_id": team_a.id} for p in players_b]
    return build_trade_context(db, [team_a.id, team_b.id], moves, league_year=league_year)


class TestRosterSize:
    def test_fail_above_18_even_without_contract_data(self, db, cap_params):
        team_a = make_team(db, 1, "AAA")
        team_b = make_team(db, 2, "BBB")
        for i in range(18):
            make_player(db, 500 + i, f"B Bench{i}", team_b)
        traded = make_player(db, 100, "Traded Guy", team_a)
        context = _swap_context(db, team_a, team_b, [traded], [])
        results = RosterSizeRule().evaluate(context)
        team_b_result = next(r for r in results if r.calculation["roster_after"] == 19)
        assert team_b_result.status == "fail"

    def test_warning_between_16_and_18_when_types_unknown(self, db, cap_params):
        team_a = make_team(db, 1, "AAA")
        team_b = make_team(db, 2, "BBB")
        for i in range(15):
            make_player(db, 500 + i, f"B Bench{i}", team_b)
        traded = make_player(db, 100, "Traded Guy", team_a)
        context = _swap_context(db, team_a, team_b, [traded], [])
        team_b_result = next(
            r for r in RosterSizeRule().evaluate(context) if r.calculation["roster_after"] == 16
        )
        assert team_b_result.status == "warning"
        assert team_b_result.confidence == "medium"

    def test_fail_below_league_minimum(self, db, cap_params):
        team_a = make_team(db, 1, "AAA")
        team_b = make_team(db, 2, "BBB")
        players = [make_player(db, 100 + i, f"A Guy{i}", team_a) for i in range(12)]
        context = _swap_context(db, team_a, team_b, players[:2], [])
        team_a_result = next(
            r for r in RosterSizeRule().evaluate(context) if r.calculation["roster_after"] == 10
        )
        assert team_a_result.status == "fail"


class TestRecentlySigned:
    def test_restricted_inside_window(self, db, cap_params):
        team_a = make_team(db, 1, "AAA")
        team_b = make_team(db, 2, "BBB")
        p = make_player(
            db, 100, "Fresh Signing", team_a, salary=5_000_000, signed_date=date(2026, 7, 10)
        )
        context = _swap_context(db, team_a, team_b, [p], [])
        rule = RecentlySignedRule(today=date(2026, 7, 20))
        results = rule.evaluate(context)
        assert results[0].status == "fail"
        assert "cannot be traded" in results[0].message

    def test_allowed_after_window(self, db, cap_params):
        team_a = make_team(db, 1, "AAA")
        team_b = make_team(db, 2, "BBB")
        p = make_player(
            db, 100, "Old Signing", team_a, salary=5_000_000, signed_date=date(2025, 7, 10)
        )
        context = _swap_context(db, team_a, team_b, [p], [])
        results = RecentlySignedRule(today=date(2026, 7, 20)).evaluate(context)
        assert results[0].status == "pass"


class TestNoTradeClause:
    def test_warning_when_clause_present(self, db, cap_params):
        team_a = make_team(db, 1, "AAA")
        team_b = make_team(db, 2, "BBB")
        p = make_player(db, 100, "Veteran Star", team_a, salary=45_000_000, no_trade_clause=True)
        context = _swap_context(db, team_a, team_b, [p], [])
        results = NoTradeClauseRule().evaluate(context)
        assert results[0].status == "warning"
        assert "no-trade clause" in results[0].message


class TestTwoWayExclusion:
    def test_two_way_salary_excluded_from_matching(self, db, cap_params):
        team_a = make_team(db, 1, "AAA")
        team_b = make_team(db, 2, "BBB")
        standard = make_player(db, 100, "Standard Guy", team_a, salary=10_000_000)
        two_way = make_player(
            db, 101, "Two Way Guy", team_a, salary=600_000, contract_type="two-way"
        )
        context = _swap_context(db, team_a, team_b, [standard, two_way], [])
        team_a_context = context.team(team_a.id)
        assert team_a_context.outgoing_salary == 10_000_000  # two-way excluded
        results = TwoWayExclusionRule().evaluate(context)
        assert any("Two Way Guy" in r.message for r in results)
