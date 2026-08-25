"""Unit tests for every salary-related CBA rule (fixture contract data)."""

from app.cba.builder import build_trade_context
from app.cba.context import CapParams, overall_status
from app.cba.rules.salary import (
    MinimumTeamSalaryRule,
    SalaryMatchingRule,
    SecondApronAggregationRule,
    max_incoming_at_or_above_first_apron,
    max_incoming_below_first_apron,
)
from tests.conftest import make_player, make_team

PARAMS = CapParams(
    league_year="2026-27",
    salary_cap=164_961_000,
    luxury_tax=200_428_000,
    first_apron=209_015_000,
    second_apron=221_686_000,
    minimum_team_salary=148_465_000,
)


class TestMatchingBands:
    def test_small_salary_doubles_plus_allowance(self):
        # $5M outgoing, below band-1 max → 200% + the cap-scaled allowance
        assert max_incoming_below_first_apron(5_000_000, PARAMS) == (
            5_000_000 + 5_000_000 + PARAMS.scaled_allowance
        )

    def test_mid_band_adds_fixed_amount(self):
        # $20M outgoing (scaled band 2): out + band2_add wins over 125%+allowance
        expected = 20_000_000 + PARAMS.tpe_band2_add
        assert max_incoming_below_first_apron(20_000_000, PARAMS) == expected

    def test_large_salary_uses_125_percent(self):
        out = 60_000_000
        assert max_incoming_below_first_apron(out, PARAMS) == 1.25 * out + PARAMS.scaled_allowance

    def test_bands_scale_with_cap(self):
        # 2026-27 cap is ~6.67% above 2025-26 → thresholds scale by the same ratio
        assert PARAMS.tpe_band1_max > 8_846_000
        assert abs(PARAMS.tpe_band1_max / 8_846_000 - PARAMS.salary_cap / 154_647_000) < 1e-9

    def test_the_allowance_scales_with_the_cap_too(self):
        """C13. Every dollar term in the band formulas must scale together, or the
        formulas stop meeting at the edges they are defined to meet at."""
        assert PARAMS.scaled_allowance == PARAMS.allowance * PARAMS.cap_ratio
        assert PARAMS.scaled_allowance > PARAMS.allowance  # 2026-27 cap is above 2025-26

    def test_no_discontinuity_at_band_edges(self):
        """Both edges, to the dollar. With a fixed $250K against scaled edges the 2026-27
        boundaries jump by ±$16,673 — this is the assertion that would have caught it."""
        for edge in (PARAMS.tpe_band1_max, PARAMS.tpe_band2_max):
            below = max_incoming_below_first_apron(edge - 1, PARAMS)
            above = max_incoming_below_first_apron(edge + 1, PARAMS)
            assert abs(above - below) < 10, f"discontinuity of {above - below:,.0f} at {edge:,.0f}"

    def test_the_maximum_is_monotone_in_outgoing_salary(self):
        """Sending out more salary may never lower the maximum you can take back. Band 2
        was non-monotonic with the unscaled allowance."""
        values = [
            max_incoming_below_first_apron(out, PARAMS)
            for out in range(1_000_000, 60_000_000, 250_000)
        ]
        assert all(b >= a for a, b in zip(values, values[1:], strict=False))

    def test_apron_team_limited_to_100_percent(self):
        assert max_incoming_at_or_above_first_apron(30_000_000, PARAMS) == (
            30_000_000 + PARAMS.scaled_allowance
        )


def _context(db, cap_params, salaries_a, salaries_b, payroll_filler_a=0, payroll_filler_b=0):
    """Two teams trading players with given salaries; optional filler payroll."""
    team_a = make_team(db, 1, "AAA")
    team_b = make_team(db, 2, "BBB")
    moves = []
    for i, salary in enumerate(salaries_a):
        p = make_player(db, 100 + i, f"A Player{i}", team_a, salary=salary)
        moves.append({"player_id": p.id, "from_team_id": team_a.id, "to_team_id": team_b.id})
    for i, salary in enumerate(salaries_b):
        p = make_player(db, 200 + i, f"B Player{i}", team_b, salary=salary)
        moves.append({"player_id": p.id, "from_team_id": team_b.id, "to_team_id": team_a.id})
    if payroll_filler_a:
        make_player(db, 300, "A Filler", team_a, salary=payroll_filler_a)
    if payroll_filler_b:
        make_player(db, 301, "B Filler", team_b, salary=payroll_filler_b)
    return build_trade_context(db, [team_a.id, team_b.id], moves, league_year="2026-27")


class TestSalaryMatchingRule:
    def test_legal_when_incoming_within_band(self, db, cap_params):
        context = _context(db, cap_params, [10_000_000], [12_000_000])
        results = SalaryMatchingRule().evaluate(context)
        assert all(r.status == "pass" for r in results)

    def test_illegal_when_incoming_exceeds_maximum(self, db, cap_params):
        # $1M out cannot bring back $30M for a team without cap room mechanics
        context = _context(db, cap_params, [1_000_000], [30_000_000], payroll_filler_a=170_000_000)
        results = SalaryMatchingRule().evaluate(context)
        team_a_result = results[0]
        assert team_a_result.status == "fail"
        assert team_a_result.calculation["maximum_incoming"] < 30_000_000

    def test_unavailable_when_salary_missing(self, db, cap_params):
        team_a = make_team(db, 1, "AAA")
        team_b = make_team(db, 2, "BBB")
        p1 = make_player(db, 100, "No Contract", team_a, salary=None)
        p2 = make_player(db, 200, "Has Contract", team_b, salary=5_000_000)
        moves = [
            {"player_id": p1.id, "from_team_id": team_a.id, "to_team_id": team_b.id},
            {"player_id": p2.id, "from_team_id": team_b.id, "to_team_id": team_a.id},
        ]
        context = build_trade_context(db, [team_a.id, team_b.id], moves, league_year="2026-27")
        results = SalaryMatchingRule().evaluate(context)
        assert all(r.status == "unavailable" for r in results)
        # honesty standard: overall can be at best conditionally valid
        assert overall_status(results) == "not_evaluated"

    def test_first_apron_team_gets_standard_tpe_only(self, db, cap_params):
        # Post-trade payroll above first apron → 100% + 250K limit
        context = _context(
            db,
            cap_params,
            [10_000_000],
            [12_000_000],
            payroll_filler_a=200_000_000,  # pushes team A above the first apron
        )
        team_a_result = SalaryMatchingRule().evaluate(context)[0]
        assert team_a_result.status == "fail"  # 12M > 10M + 250K
        assert "standard TPE" in team_a_result.calculation["band"]


class TestSecondApronAggregation:
    def test_aggregation_blocked_above_second_apron(self, db, cap_params):
        context = _context(
            db,
            cap_params,
            [8_000_000, 7_000_000],  # two players aggregated
            [14_000_000],
            payroll_filler_a=215_000_000,  # above second apron even after the swap
        )
        results = SecondApronAggregationRule().evaluate(context)
        team_a_result = next(r for r in results if r.calculation.get("outgoing_players") == 2)
        assert team_a_result.status == "fail"

    def test_aggregation_allowed_below_second_apron(self, db, cap_params):
        context = _context(db, cap_params, [8_000_000, 7_000_000], [14_000_000])
        results = SecondApronAggregationRule().evaluate(context)
        assert all(r.status == "pass" for r in results)


class TestMinimumTeamSalary:
    def test_warns_below_minimum(self, db, cap_params):
        context = _context(db, cap_params, [30_000_000], [1_000_000])
        results = MinimumTeamSalaryRule().evaluate(context)
        team_a_result = results[0]
        assert team_a_result.status == "warning"

    def test_silent_when_payroll_unknown(self, db, cap_params):
        team_a = make_team(db, 1, "AAA")
        team_b = make_team(db, 2, "BBB")
        p1 = make_player(db, 100, "No Contract", team_a, salary=None)
        moves = [{"player_id": p1.id, "from_team_id": team_a.id, "to_team_id": team_b.id}]
        context = build_trade_context(db, [team_a.id, team_b.id], moves, league_year="2026-27")
        assert MinimumTeamSalaryRule().evaluate(context) == []


class TestOverallStatus:
    def test_four_states(self):
        from app.cba.context import RuleResult

        def r(status):
            return RuleResult(rule_code="X", status=status, team_id=None, message="")

        assert overall_status([r("pass"), r("pass")]) == "verified_legal"
        assert overall_status([r("pass"), r("fail")]) == "verified_illegal"
        assert overall_status([r("pass"), r("unavailable")]) == "conditionally_valid"
        assert overall_status([r("unavailable")]) == "not_evaluated"
        # fail wins even when data is also missing
        assert overall_status([r("fail"), r("unavailable")]) == "verified_illegal"
        # warnings alone still count as evaluated
        assert overall_status([r("pass"), r("warning")]) == "verified_legal"
