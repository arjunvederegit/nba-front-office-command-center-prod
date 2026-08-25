"""R2c — a partial payroll is disclosed, never imputed, and never verified.

Three properties, and the release is only correct if all three hold at once:

1. **Disclosure.** A team with unpriced players still reports a payroll figure, always
   accompanied by the coverage it was computed from. Before R2c, one missing salary
   removed the whole team: measured against the Basketball-Reference offseason snapshot,
   74 % of rostered players had a 2026-27 salary and **0 of 30** teams had a payroll.
2. **No imputation.** The figure is exactly the sum of the salaries on file. It never
   moves because a player without a contract exists, and no minimum, median or league
   average is substituted for a missing one.
3. **No false verification.** Every salary rule still reports `unavailable`, and
   `overall_status` never reaches `verified_legal`, while coverage is partial. The one
   thing partial data may do is *refute*: a lower bound that already clears a threshold
   proves the team is past it, because the missing salaries can only add.
"""

from datetime import date

from sqlalchemy.orm import Session

from app.cba.builder import build_trade_context
from app.cba.context import CapParams, PayrollCoverage, TeamContext
from app.cba.engine import TradeLegalityEngine
from app.cba.rules.salary import SalaryMatchingRule, SecondApronAggregationRule
from app.db.models import LeagueCapParameters, Team
from app.services.payroll import team_payroll_summary
from tests.conftest import make_player, make_team

PARAMS = CapParams(
    league_year="2026-27",
    salary_cap=164_961_000,
    luxury_tax=200_428_000,
    first_apron=209_015_000,
    second_apron=221_686_000,
    minimum_team_salary=148_465_000,
)


def _roster(db: Session, team: Team, salaries: list[int | None], offset: int = 0) -> list:
    return [
        make_player(db, 5000 + offset + i, f"Roster {offset + i:02d}", team, salary=salary)
        for i, salary in enumerate(salaries)
    ]


# --------------------------------------------------------------------- the coverage type


class TestPayrollCoverage:
    def test_known_is_a_lower_bound_and_verified_is_withheld(self) -> None:
        partial = PayrollCoverage(known=180_000_000, players_known=16, players_total=18)
        assert partial.known == 180_000_000
        assert partial.verified is None  # the only figure a threshold may be compared to
        assert partial.complete is False
        assert partial.players_unknown == 2
        assert partial.as_dict()["is_lower_bound"] is True

    def test_complete_coverage_promotes_the_same_number(self) -> None:
        full = PayrollCoverage(known=180_000_000, players_known=18, players_total=18)
        assert full.verified == 180_000_000
        assert full.complete is True
        assert full.as_dict()["is_lower_bound"] is False

    def test_an_empty_roster_is_not_a_complete_one(self) -> None:
        """`players_known == players_total` is satisfied trivially at zero. A team with no
        roster on file must not report a verified payroll of $0."""
        empty = PayrollCoverage(known=0, players_known=0, players_total=0)
        assert empty.complete is False
        assert empty.verified is None
        assert empty.share is None

    def test_the_disclosure_names_the_counts(self) -> None:
        note = PayrollCoverage(known=1, players_known=16, players_total=18).disclosure()
        assert "16 of 18" in note
        assert "2 unknown" in note
        assert "not estimated" in note


# ------------------------------------------------------------------ no imputation, ever


class TestNoImputation:
    def test_the_figure_is_exactly_the_sum_of_known_salaries(
        self, db: Session, cap_params: LeagueCapParameters
    ) -> None:
        team = make_team(db, 1, "AAA")
        _roster(db, team, [10_000_000, 20_000_000, 30_000_000, None, None])
        summary = team_payroll_summary(db, team)

        assert summary["payroll_known"] == 60_000_000
        assert summary["roster_size"] == 5
        assert summary["players_with_salary"] == 3
        assert summary["players_without_salary"] == 2

    def test_an_unpriced_player_does_not_move_the_number(
        self, db: Session, cap_params: LeagueCapParameters
    ) -> None:
        """The regression that would mean imputation: the payroll rising when a player
        with no contract joins the roster."""
        team = make_team(db, 1, "AAA")
        _roster(db, team, [10_000_000, 20_000_000])
        before = team_payroll_summary(db, team)["payroll_known"]

        make_player(db, 9001, "Unpriced Newcomer", team, salary=None)
        after = team_payroll_summary(db, team)

        assert after["payroll_known"] == before == 30_000_000
        assert after["roster_size"] == 3
        assert after["players_without_salary"] == 1
        assert "Unpriced Newcomer" in after["players_missing_salary"]

    def test_missing_players_are_named_not_counted_away(
        self, db: Session, cap_params: LeagueCapParameters
    ) -> None:
        team = make_team(db, 1, "AAA")
        make_player(db, 9101, "Priced Player", team, salary=5_000_000)
        make_player(db, 9102, "Missing One", team, salary=None)
        make_player(db, 9103, "Missing Two", team, salary=None)

        summary = team_payroll_summary(db, team)
        assert summary["players_missing_salary"] == ["Missing One", "Missing Two"]
        assert summary["payroll_coverage_note"].startswith("Computed from 1 of 3 contracts")


# ------------------------------------------------------- disclosure without verification


class TestDisclosedButNotVerified:
    def test_partial_coverage_shows_a_payroll_and_withholds_the_verdict(
        self, db: Session, cap_params: LeagueCapParameters
    ) -> None:
        """The R2c acceptance criterion, stated exactly: a team with one unknown salary
        shows a payroll and its coverage, and the payroll stays unavailable as a verdict."""
        team = make_team(db, 1, "AAA")
        _roster(db, team, [12_000_000] * 17 + [None])

        summary = team_payroll_summary(db, team)
        assert summary["payroll_known"] == 204_000_000
        assert summary["payroll_coverage"]["players_known"] == 17
        assert summary["payroll_coverage"]["players_total"] == 18
        assert summary["payroll_coverage"]["is_lower_bound"] is True
        # Unchanged by R2c: the verified figure and its cap context stay withheld.
        assert summary["payroll"] is None
        assert summary["payroll_available"] is False
        assert "cap_context" not in summary
        assert summary["unavailable_reason"]

    def test_complete_coverage_still_verifies(
        self, db: Session, cap_params: LeagueCapParameters
    ) -> None:
        team = make_team(db, 1, "AAA")
        _roster(db, team, [12_000_000] * 18)

        summary = team_payroll_summary(db, team)
        assert summary["payroll"] == summary["payroll_known"] == 216_000_000
        assert summary["payroll_available"] is True
        assert summary["payroll_is_lower_bound"] is False
        assert summary["cap_context"]["room_below_tax"] == 200_428_000 - 216_000_000
        assert "cap_context_partial" not in summary

    def test_partial_cap_context_states_only_thresholds_already_cleared(
        self, db: Session, cap_params: LeagueCapParameters
    ) -> None:
        """Room below the tax needs the unknown salaries; "already above the tax" does not."""
        team = make_team(db, 1, "AAA")
        _roster(db, team, [12_000_000] * 17 + [None])  # $204M known, tax line $200.4M

        partial = team_payroll_summary(db, team)["cap_context_partial"]
        assert partial["thresholds_already_cleared"] == ["salary_cap", "luxury_tax"]
        assert "room_below_tax" not in partial

    def test_nothing_is_claimed_when_the_lower_bound_clears_nothing(
        self, db: Session, cap_params: LeagueCapParameters
    ) -> None:
        team = make_team(db, 1, "AAA")
        _roster(db, team, [1_000_000] * 5 + [None])

        partial = team_payroll_summary(db, team)["cap_context_partial"]
        assert partial["thresholds_already_cleared"] == []


# ------------------------------------------------------------- the rules stay unavailable


class TestRulesStillRefuseToVerify:
    def _partial_trade(self, db: Session):
        """AAA has one unpriced bench player; both traded players are priced."""
        team_a = make_team(db, 1, "AAA")
        team_b = make_team(db, 2, "BBB")
        star_a = make_player(db, 10, "A Star", team_a, salary=30_000_000)
        star_b = make_player(db, 20, "B Star", team_b, salary=29_000_000)
        _roster(db, team_a, [10_000_000] * 13 + [None], offset=100)
        _roster(db, team_b, [10_000_000] * 14, offset=200)
        moves = [
            {"player_id": star_a.id, "from_team_id": team_a.id, "to_team_id": team_b.id},
            {"player_id": star_b.id, "from_team_id": team_b.id, "to_team_id": team_a.id},
        ]
        return team_a, team_b, build_trade_context(db, [team_a.id, team_b.id], moves)

    def test_salary_matching_is_unavailable_for_the_partial_team_only(
        self, db: Session, cap_params: LeagueCapParameters
    ) -> None:
        team_a, team_b, context = self._partial_trade(db)
        results = {r.team_id: r for r in SalaryMatchingRule().evaluate(context)}

        assert results[team_a.id].status == "unavailable"
        assert "14 of 15" in results[team_a.id].message
        assert results[team_a.id].calculation["payroll_known"] == 160_000_000
        # The fully-covered counterparty is unaffected — disclosure is per team.
        assert results[team_b.id].status in ("pass", "fail")

    def test_overall_status_never_reaches_verified_legal(
        self, db: Session, cap_params: LeagueCapParameters
    ) -> None:
        _, _, context = self._partial_trade(db)
        report = TradeLegalityEngine().evaluate(context)
        assert report["overall_status"] != "verified_legal"

    def test_the_engine_publishes_the_disclosure_next_to_the_number(
        self, db: Session, cap_params: LeagueCapParameters
    ) -> None:
        team_a, _, context = self._partial_trade(db)
        team = TradeLegalityEngine().evaluate(context)["teams"][team_a.id]

        assert team["payroll_before"] is None  # verified figure withheld
        assert team["payroll_known_before"] == 160_000_000  # disclosed figure present
        assert team["payroll_coverage_before"]["players_unknown"] == 1
        assert "14 of 15" in team["payroll_coverage_note"]
        assert team["payroll_known_after"] == 160_000_000 - 30_000_000 + 29_000_000


# ------------------------------------------------------- partial data may refute, not pass


class TestPartialDataRefutesButNeverPasses:
    def test_apron_floor_is_none_until_a_threshold_is_actually_cleared(self) -> None:
        team = TeamContext(
            team_id="t",
            abbreviation="AAA",
            name="Alpha",
            roster_count_before=18,
            coverage_before=PayrollCoverage(
                known=150_000_000, players_known=15, players_total=18
            ),
        )
        # $150M is under the tax line, but three salaries are missing — nothing is proven,
        # and "below_tax" would be a claim the data cannot support.
        assert team.apron_status_at_least(team.coverage_before, PARAMS) is None

    def test_apron_floor_is_asserted_once_the_known_salaries_clear_the_line(self) -> None:
        team = TeamContext(
            team_id="t",
            abbreviation="AAA",
            name="Alpha",
            roster_count_before=18,
            coverage_before=PayrollCoverage(
                known=225_000_000, players_known=15, players_total=18
            ),
        )
        assert team.apron_status_at_least(team.coverage_before, PARAMS) == "above_second_apron"

    def test_complete_coverage_reports_the_ordinary_status_including_below_tax(self) -> None:
        team = TeamContext(
            team_id="t",
            abbreviation="AAA",
            name="Alpha",
            roster_count_before=18,
            coverage_before=PayrollCoverage(
                known=150_000_000, players_known=18, players_total=18
            ),
        )
        assert team.apron_status_at_least(team.coverage_before, PARAMS) == "below_tax"

    def test_aggregation_fails_when_the_lower_bound_alone_clears_the_second_apron(
        self, db: Session, cap_params: LeagueCapParameters
    ) -> None:
        """Partial data proving illegality is sound: the unpriced players can only add."""
        team_a = make_team(db, 1, "AAA")
        team_b = make_team(db, 2, "BBB")
        out_one = make_player(db, 10, "Out One", team_a, salary=20_000_000)
        out_two = make_player(db, 11, "Out Two", team_a, salary=20_000_000)
        _roster(db, team_a, [18_000_000] * 14 + [None], offset=100)  # known $292M
        _roster(db, team_b, [1_000_000] * 14, offset=200)
        moves = [
            {"player_id": p.id, "from_team_id": team_a.id, "to_team_id": team_b.id}
            for p in (out_one, out_two)
        ]
        context = build_trade_context(db, [team_a.id, team_b.id], moves)

        result = {r.team_id: r for r in SecondApronAggregationRule().evaluate(context)}[team_a.id]
        assert result.status == "fail"
        assert result.calculation["post_trade_payroll_is_lower_bound"] is True
        assert result.calculation["post_trade_payroll_known"] > PARAMS.second_apron
        assert "can only raise it" in result.message

    def test_aggregation_stays_unavailable_when_the_lower_bound_proves_nothing(
        self, db: Session, cap_params: LeagueCapParameters
    ) -> None:
        team_a = make_team(db, 1, "AAA")
        team_b = make_team(db, 2, "BBB")
        out_one = make_player(db, 10, "Out One", team_a, salary=5_000_000)
        out_two = make_player(db, 11, "Out Two", team_a, salary=5_000_000)
        _roster(db, team_a, [4_000_000] * 12 + [None], offset=100)
        _roster(db, team_b, [1_000_000] * 14, offset=200)
        moves = [
            {"player_id": p.id, "from_team_id": team_a.id, "to_team_id": team_b.id}
            for p in (out_one, out_two)
        ]
        context = build_trade_context(db, [team_a.id, team_b.id], moves)

        result = {r.team_id: r for r in SecondApronAggregationRule().evaluate(context)}[team_a.id]
        assert result.status == "unavailable"
        assert result.calculation["payroll_known"] == 58_000_000


# ---------------------------------------------------------------------- coverage arithmetic


class TestCoverageArithmetic:
    def test_after_coverage_tracks_the_moved_players(
        self, db: Session, cap_params: LeagueCapParameters
    ) -> None:
        team_a = make_team(db, 1, "AAA")
        team_b = make_team(db, 2, "BBB")
        out = make_player(db, 10, "Out", team_a, salary=20_000_000)
        in_one = make_player(db, 20, "In One", team_b, salary=9_000_000)
        in_two = make_player(db, 21, "In Two", team_b, salary=8_000_000)
        _roster(db, team_a, [5_000_000] * 13 + [None], offset=100)
        _roster(db, team_b, [5_000_000] * 13, offset=200)
        moves = [
            {"player_id": out.id, "from_team_id": team_a.id, "to_team_id": team_b.id},
            *[
                {"player_id": p.id, "from_team_id": team_b.id, "to_team_id": team_a.id}
                for p in (in_one, in_two)
            ],
        ]
        context = build_trade_context(db, [team_a.id, team_b.id], moves)
        team = context.team(team_a.id)

        assert team.coverage_before.players_total == 15
        assert team.coverage_before.players_known == 14
        after = team.coverage_after
        assert after.players_total == 16  # 15 - 1 + 2
        assert after.players_known == 15  # 14 - 1 + 2
        assert after.players_unknown == 1  # the same unpriced bench player
        assert after.known == team.coverage_before.known - 20_000_000 + 17_000_000

    def test_after_coverage_is_withheld_when_a_traded_salary_is_unknown(
        self, db: Session, cap_params: LeagueCapParameters
    ) -> None:
        """A lower bound built from an unknown subtraction is not a lower bound."""
        team_a = make_team(db, 1, "AAA")
        team_b = make_team(db, 2, "BBB")
        out = make_player(db, 10, "Unpriced Out", team_a, salary=None)
        _roster(db, team_a, [5_000_000] * 14, offset=100)
        _roster(db, team_b, [5_000_000] * 14, offset=200)
        moves = [{"player_id": out.id, "from_team_id": team_a.id, "to_team_id": team_b.id}]
        context = build_trade_context(db, [team_a.id, team_b.id], moves)
        team = context.team(team_a.id)

        assert team.coverage_before.known == 70_000_000  # before is still disclosable
        assert team.coverage_after is None
        assert team.payroll_known_after is None
        assert team.payroll_after is None


# ------------------------------------------------------------------------------- the API


def test_payroll_endpoint_never_renders_a_figure_without_its_coverage(
    db: Session, cap_params: LeagueCapParameters
) -> None:
    team = make_team(db, 1, "AAA")
    _roster(db, team, [11_000_000] * 16 + [None, None])
    summary = team_payroll_summary(db, team)

    assert summary["payroll_known"] is not None
    for key in ("payroll_coverage", "payroll_coverage_note", "payroll_is_lower_bound"):
        assert key in summary, f"the disclosure field {key} is missing"
    assert summary["payroll_coverage"]["players_unknown"] == 2


def test_source_dates_survive_into_the_summary(
    db: Session, cap_params: LeagueCapParameters
) -> None:
    team = make_team(db, 1, "AAA")
    make_player(db, 9200, "Priced", team, salary=5_000_000)
    row = next(p for p in team_payroll_summary(db, team)["players"] if p["salary"] is not None)
    assert row["source_name"] == "test fixture"
    assert row["source_date"] == date(2026, 7, 1).isoformat()
