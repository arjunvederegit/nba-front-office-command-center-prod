"""R2b — what must NOT get better when contract data is switched on.

Importing contracts makes four rules speak that were previously silent or vacuous, and
each one had a failure mode that moves in the *permissive* direction: it would have
reported a stronger verdict on data nobody actually held.

The audit's headline for this release was "trades move from Incomplete check to real
verdicts". Measured, that is not what a Basketball-Reference snapshot delivers, because
the page carries no contract type, no signing date and no no-trade column. A post-import
run showing `(pass, high)` on ROSTER_SIZE is a failed acceptance, not a success — so
these tests assert the *absence* of improvement wherever the data does not support it.
"""

from sqlalchemy.orm import Session

from app.cba.builder import build_trade_context
from app.cba.context import CapParams, overall_status
from app.cba.engine import TradeLegalityEngine
from app.cba.rules.restrictions import NoTradeClauseRule, TwoWayExclusionRule
from app.cba.rules.roster import RosterSizeRule
from app.cba.rules.salary import (
    SalaryDataAvailabilityRule,
    SalaryMatchingRule,
    SecondApronAggregationRule,
)
from app.db.models import LeagueCapParameters, Team
from tests.conftest import make_player, make_team

PARAMS = CapParams(
    league_year="2026-27",
    salary_cap=164_961_000,
    luxury_tax=200_428_000,
    first_apron=209_015_000,
    second_apron=221_686_000,
    minimum_team_salary=148_465_000,
)


def _fill(db: Session, team: Team, n: int, offset: int, salary: int | None = 5_000_000) -> None:
    for i in range(n):
        make_player(db, 7000 + offset + i, f"Bench {offset + i:02d}", team, salary=salary)


def _priced_but_untyped_trade(db: Session, out_count: int = 1):
    """Exactly what a BBRef import produces: salaries known, contract types unknown."""
    team_a, team_b = make_team(db, 1, "AAA"), make_team(db, 2, "BBB")
    outgoing = [
        make_player(db, 10 + i, f"A Out {i}", team_a, salary=20_000_000, contract_type=None)
        for i in range(out_count)
    ]
    incoming = make_player(db, 30, "B Out", team_b, salary=21_000_000, contract_type=None)
    _fill(db, team_a, 14, 100, salary=6_000_000)
    _fill(db, team_b, 14, 200, salary=6_000_000)
    moves = [
        {"player_id": p.id, "from_team_id": team_a.id, "to_team_id": team_b.id} for p in outgoing
    ] + [{"player_id": incoming.id, "from_team_id": team_b.id, "to_team_id": team_a.id}]
    return team_a, team_b, build_trade_context(db, [team_a.id, team_b.id], moves)


class TestContractTypeIsNeverAssumed:
    def test_roster_size_stays_warning_and_medium_without_real_types(
        self, db: Session, cap_params: LeagueCapParameters
    ) -> None:
        """C9's acceptance criterion, inverted into an assertion.

        A 16-man post-trade roster is legal only if at least one contract is two-way. With
        types unknown that cannot be established, so the honest answer is a warning at
        medium confidence — not `pass` at high.
        """
        team_a, _, context = self._sixteen_man(db)
        result = {r.team_id: r for r in RosterSizeRule().evaluate(context)}[team_a.id]
        assert result.status == "warning"
        assert result.confidence == "medium"
        assert result.calculation["contract_types_known"] is False

    def _sixteen_man(self, db: Session):
        team_a, team_b = make_team(db, 1, "AAA"), make_team(db, 2, "BBB")
        incoming = make_player(db, 30, "B Out", team_b, salary=21_000_000, contract_type=None)
        _fill(db, team_a, 15, 100, salary=6_000_000)
        _fill(db, team_b, 15, 200, salary=6_000_000)
        moves = [{"player_id": incoming.id, "from_team_id": team_b.id, "to_team_id": team_a.id}]
        return team_a, team_b, build_trade_context(db, [team_a.id, team_b.id], moves)

    def test_a_real_type_promotes_the_same_roster_to_a_verdict(
        self, db: Session, cap_params: LeagueCapParameters
    ) -> None:
        """The counterpart: with genuine types the rule speaks, so the gate is about data
        and not a permanent downgrade."""
        team_a, team_b = make_team(db, 1, "AAA"), make_team(db, 2, "BBB")
        incoming = make_player(
            db, 30, "B Out", team_b, salary=21_000_000, contract_type="standard"
        )
        _fill(db, team_a, 15, 100, salary=6_000_000)
        _fill(db, team_b, 15, 200, salary=6_000_000)
        context = build_trade_context(
            db,
            [team_a.id, team_b.id],
            [{"player_id": incoming.id, "from_team_id": team_b.id, "to_team_id": team_a.id}],
        )
        result = {r.team_id: r for r in RosterSizeRule().evaluate(context)}[team_a.id]
        assert result.confidence == "high"
        assert result.calculation["contract_types_known"] is True


class TestTwoWaySalariesDoNotInflateMatching:
    def test_matching_is_unavailable_when_a_traded_contract_type_is_unknown(
        self, db: Session, cap_params: LeagueCapParameters
    ) -> None:
        """Salaries alone are not enough. A two-way salary counted as standard inflates
        the outgoing sum, inflates `maximum_incoming`, and approves trades the engine
        should refuse — the error is permissive, so it must not be made silently."""
        team_a, _, context = _priced_but_untyped_trade(db)
        team = context.team(team_a.id)
        assert team.contract_types_known is False
        assert team.outgoing_salary is None  # matching sum withheld
        assert team.outgoing_salary_total == 20_000_000  # payroll sum still available

        result = {r.team_id: r for r in SalaryMatchingRule().evaluate(context)}[team_a.id]
        assert result.status == "unavailable"

    def test_salary_data_available_does_not_pass_on_salaries_alone(
        self, db: Session, cap_params: LeagueCapParameters
    ) -> None:
        team_a, _, context = _priced_but_untyped_trade(db)
        result = {r.team_id: r for r in SalaryDataAvailabilityRule().evaluate(context)}[team_a.id]
        assert result.status == "unavailable"
        assert "contract type is unknown" in result.message

    def test_two_way_exclusion_reports_unavailable_instead_of_staying_silent(
        self, db: Session, cap_params: LeagueCapParameters
    ) -> None:
        team_a, _, context = _priced_but_untyped_trade(db)
        results = {r.team_id: r for r in TwoWayExclusionRule().evaluate(context)}
        assert results[team_a.id].status == "unavailable"

    def test_aggregation_is_unavailable_not_permitted_when_types_are_unknown(
        self, db: Session, cap_params: LeagueCapParameters
    ) -> None:
        """Two-way contracts are not aggregated, so with unknown types "this deal does not
        aggregate" is a guess — and it is the guess that clears the second-apron ban."""
        team_a, _, context = _priced_but_untyped_trade(db, out_count=2)
        assert context.team(team_a.id).aggregates_salaries is None
        result = {r.team_id: r for r in SecondApronAggregationRule().evaluate(context)}[team_a.id]
        assert result.status == "unavailable"
        assert result.calculation["contract_types_known"] is False


class TestPreviouslySilentRulesSpeak:
    def test_no_trade_clause_reports_unknown_rather_than_nothing(
        self, db: Session, cap_params: LeagueCapParameters
    ) -> None:
        """A rule that emits nothing reads as "checked, nothing found". No provider here
        reports no-trade clauses, so absence of a recorded clause is not absence of one."""
        team_a, _, context = _priced_but_untyped_trade(db)
        results = {r.team_id: r for r in NoTradeClauseRule().evaluate(context)}
        assert results[team_a.id].status == "unavailable"
        assert "A Out 0" in results[team_a.id].calculation["players_with_unknown_clause"]

    def test_the_engine_reports_every_rule_rather_than_shrinking_to_five(
        self, db: Session, cap_params: LeagueCapParameters
    ) -> None:
        team_a, _, context = _priced_but_untyped_trade(db, out_count=2)
        report = TradeLegalityEngine().evaluate(context)
        codes = {r["rule_code"] for r in report["rule_results"]}
        assert {
            "SALARY_DATA_AVAILABLE",
            "SALARY_MATCHING",
            "SECOND_APRON_AGGREGATION",
            "ROSTER_SIZE",
            "RECENTLY_SIGNED",
            "NO_TRADE_CLAUSE",
            "TWO_WAY_EXCLUSION",
        } <= codes

    def test_the_verdict_is_never_verified_legal_on_bbref_shaped_data(
        self, db: Session, cap_params: LeagueCapParameters
    ) -> None:
        team_a, _, context = _priced_but_untyped_trade(db)
        report = TradeLegalityEngine().evaluate(context)
        assert report["overall_status"] == "conditionally_valid"


class TestPicksOnlySidesAreNotSalaryVerified:
    def test_a_side_that_moves_no_contracts_does_not_pass_the_salary_data_rule(
        self, db: Session, cap_params: LeagueCapParameters
    ) -> None:
        """`all(... for p in [])` is True, so a picks-only side reported "contract data
        present for all traded players" — a pass on a deal with no salary data at all."""
        team_a, team_b = make_team(db, 1, "AAA"), make_team(db, 2, "BBB")
        _fill(db, team_a, 15, 100)
        _fill(db, team_b, 15, 200)
        context = build_trade_context(
            db,
            [team_a.id, team_b.id],
            [],
            pick_moves=[
                {
                    "from_team_id": team_a.id,
                    "to_team_id": team_b.id,
                    "draft_year": 2031,
                    "round_number": 1,
                    "protections": None,
                    "is_hypothetical": True,
                }
            ],
        )
        results = {r.team_id: r for r in SalaryDataAvailabilityRule().evaluate(context)}
        assert results[team_a.id].status == "unavailable"
        assert results[team_a.id].calculation["players_moved"] == 0
        assert overall_status(list(results.values())) == "not_evaluated"
