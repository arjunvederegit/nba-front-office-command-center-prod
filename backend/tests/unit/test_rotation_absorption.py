"""R5.5. Who absorbs a departure's minutes, and what that forces to be true.

R5 shipped an allocator that answered the post-trade question by calling
`allocate_rotation` independently on both rosters. Because the level model shares 240
minutes in proportion to baseline minutes, a departure's minutes were re-shared across
everyone who stayed, at the quality of everyone who stayed. Analytically that makes

    d_teamTEI(remove j)  =  (w_j / W) * ( ebar_-j - e_j )

so a removal is scored as an improvement exactly when the player sits below his own
team's minutes-weighted mean. Measured on the 30 ingested rosters, that rule predicted
the sign on **487 of 487** leave-one-out removals, and **191 of the 370 above-replacement
players (51.6 %)** came out as addition by subtraction — 152 of them rotation players at
15 or more minutes a game. Herbert Jones at 29.7 mpg scored +2.13 wins to remove.

The fix passes the before-allocation in as an `anchor`, so the freed minutes are not
re-shared at all: they are replacement minutes, which is what `REPLACEMENT_TEI` already
means ("mean TEI of player-seasons outside their team's top 10 by minutes") and what
`ROTATION_DEPTH = 10` already asserts. The evidence for each half of that choice is in
`projection.ABSORPTION_RULE`; these tests pin what it forces to be true.
"""

import numpy as np
import pytest

from app.analytics.projection import (
    DEFAULT_MAX_MINUTES,
    REPLACEMENT_TEI,
    TEAM_MINUTES,
    RotationPlayer,
    allocate_rotation,
    team_tei_to_net_rating_delta,
)

BASELINES = [34.0, 32.0, 30.0, 28.0, 26.0, 24.0, 20.0, 18.0, 15.0, 12.0, 9.0, 6.0]
TEIS = [3.2, 1.8, 1.1, 0.6, 0.2, -0.1, -0.5, -0.9, -1.2, -1.6, -2.0, -2.4]


def _roster(n: int = 12, availability: float = 1.0) -> list[RotationPlayer]:
    return [
        RotationPlayer(
            player_id=f"p{i}",
            name=f"P{i}",
            tei=TEIS[i],
            baseline_minutes=BASELINES[i],
            availability=availability,
        )
        for i in range(n)
    ]


def _effective(p: RotationPlayer) -> float:
    return p.availability * p.tei + (1 - p.availability) * REPLACEMENT_TEI


def _without(roster, *ids):
    return [p for p in roster if p.player_id not in set(ids)]


class TestMonotonicity:
    """The property the release exists to establish."""

    @pytest.mark.parametrize("victim", range(12))
    def test_removing_an_above_replacement_player_never_helps(self, victim):
        roster = _roster()
        before = allocate_rotation(roster)
        target = roster[victim]
        after = allocate_rotation(_without(roster, target.player_id), anchor=before.minutes)
        delta = after.team_tei_per_minute - before.team_tei_per_minute
        if _effective(target) > REPLACEMENT_TEI:
            assert delta <= 1e-12, (
                f"{target.player_id} has effective TEI {_effective(target):+.3f} against "
                f"a replacement level of {REPLACEMENT_TEI:+.3f}, and removing him for "
                f"nothing scored {delta:+.6f}"
            )
        else:
            assert delta >= -1e-12

    def test_removing_a_below_replacement_player_never_hurts(self):
        """The other direction. Salary dumps are supposed to be able to help."""
        roster = _roster()
        roster.append(RotationPlayer("scrub", "Scrub", tei=-4.0, baseline_minutes=14.0))
        before = allocate_rotation(roster)
        after = allocate_rotation(_without(roster, "scrub"), anchor=before.minutes)
        assert after.team_tei_per_minute >= before.team_tei_per_minute - 1e-12

    def test_the_delta_is_exactly_the_players_value_above_replacement(self):
        """Not merely signed correctly — the magnitude is forced too.

        Removing player j for nothing leaves his allocated minutes unfilled, so the whole
        change is his own minutes share times his value above replacement. Any other
        answer means someone absorbed the minutes.
        """
        roster = _roster()
        before = allocate_rotation(roster)
        for p in roster:
            after = allocate_rotation(_without(roster, p.player_id), anchor=before.minutes)
            expected = -(before.minutes[p.player_id] / TEAM_MINUTES) * (
                _effective(p) - REPLACEMENT_TEI
            )
            assert after.team_tei_per_minute - before.team_tei_per_minute == pytest.approx(
                expected, abs=1e-9
            )

    def test_removing_more_players_never_helps_more_than_removing_fewer(self):
        roster = _roster()
        before = allocate_rotation(roster)
        running = before.team_tei_per_minute
        for k in range(1, 6):
            after = allocate_rotation(
                _without(roster, *[f"p{i}" for i in range(k)]), anchor=before.minutes
            )
            assert after.team_tei_per_minute <= running + 1e-12
            running = after.team_tei_per_minute

    def test_stripping_the_best_three_costs_more_than_stripping_any_one_of_them(self):
        roster = _roster()
        before = allocate_rotation(roster)
        three = allocate_rotation(_without(roster, "p0", "p1", "p2"), anchor=before.minutes)
        for pid in ("p0", "p1", "p2"):
            one = allocate_rotation(_without(roster, pid), anchor=before.minutes)
            assert three.team_tei_per_minute < one.team_tei_per_minute


class TestIncumbentsAndArrivals:
    def test_an_incumbent_keeps_the_minutes_he_already_had(self):
        roster = _roster()
        before = allocate_rotation(roster)
        after = allocate_rotation(_without(roster, "p0"), anchor=before.minutes)
        for pid, minutes in after.minutes.items():
            assert minutes == pytest.approx(before.minutes[pid], abs=1e-9)

    def test_a_departure_leaves_its_minutes_unfilled(self):
        roster = _roster()
        before = allocate_rotation(roster)
        after = allocate_rotation(_without(roster, "p3"), anchor=before.minutes)
        assert after.unfilled_minutes == pytest.approx(before.minutes["p3"], abs=1e-9)
        assert sum(after.minutes.values()) == pytest.approx(
            TEAM_MINUTES - before.minutes["p3"], abs=1e-9
        )

    def test_a_like_for_like_swap_is_close_to_neutral_in_minutes(self):
        """An arrival is priced on the ANCHOR's scale, not in raw minutes per game.

        Without that conversion an arrival's uncompressed mpg would be compared against
        incumbents' compressed minutes and every acquisition would look like an upgrade
        purely from the change of units.
        """
        roster = _roster()
        before = allocate_rotation(roster)
        swap = _without(roster, "p4") + [
            RotationPlayer("new", "New", tei=TEIS[4], baseline_minutes=BASELINES[4])
        ]
        after = allocate_rotation(swap, anchor=before.minutes)
        assert after.minutes["new"] == pytest.approx(before.minutes["p4"], abs=1e-6)
        assert after.team_tei_per_minute == pytest.approx(before.team_tei_per_minute, abs=1e-9)

    def test_acquiring_a_better_player_for_the_same_role_helps(self):
        roster = _roster()
        before = allocate_rotation(roster)
        swap = _without(roster, "p8") + [
            RotationPlayer("star", "Star", tei=2.5, baseline_minutes=BASELINES[8])
        ]
        after = allocate_rotation(swap, anchor=before.minutes)
        assert after.team_tei_per_minute > before.team_tei_per_minute

    def test_an_empty_trade_changes_nothing_at_all(self):
        roster = _roster()
        before = allocate_rotation(roster)
        after = allocate_rotation(roster, anchor=before.minutes)
        assert after.minutes == pytest.approx(before.minutes)
        assert after.team_tei_per_minute == pytest.approx(before.team_tei_per_minute)
        assert team_tei_to_net_rating_delta(before, after) == pytest.approx(0.0, abs=1e-12)

    def test_a_roster_of_entirely_new_players_falls_back_to_the_level_model(self):
        """With no incumbent there is no counterfactual to price, only a level."""
        roster = _roster()
        before = allocate_rotation(roster)
        fresh = [
            RotationPlayer(f"n{i}", f"N{i}", tei=TEIS[i], baseline_minutes=BASELINES[i])
            for i in range(12)
        ]
        anchored = allocate_rotation(fresh, anchor=before.minutes)
        level = allocate_rotation(fresh)
        assert anchored.minutes == pytest.approx(level.minutes)


class TestBudgetAndCaps:
    @pytest.mark.parametrize("n_arrivals", [1, 2, 3, 5, 8])
    def test_the_allocation_never_exceeds_the_240_minute_budget(self, n_arrivals):
        roster = _roster()
        before = allocate_rotation(roster)
        arrivals = [
            RotationPlayer(f"a{i}", f"A{i}", tei=1.0, baseline_minutes=30.0)
            for i in range(n_arrivals)
        ]
        after = allocate_rotation(roster + arrivals, anchor=before.minutes)
        assert sum(after.minutes.values()) <= TEAM_MINUTES + 1e-9

    def test_no_player_exceeds_his_cap_under_the_anchor(self):
        roster = _roster()
        before = allocate_rotation(roster)
        arrivals = [RotationPlayer("big", "Big", tei=3.0, baseline_minutes=48.0, max_minutes=30.0)]
        after = allocate_rotation(roster + arrivals, anchor=before.minutes)
        assert after.minutes["big"] <= 30.0 + 1e-9
        for p in roster:
            assert after.minutes[p.player_id] <= p.max_minutes + 1e-9

    def test_surplus_minutes_are_shed_and_never_go_negative(self):
        roster = _roster()
        before = allocate_rotation(roster)
        flood = [
            RotationPlayer(f"f{i}", f"F{i}", tei=0.5, baseline_minutes=36.0) for i in range(12)
        ]
        after = allocate_rotation(roster + flood, anchor=before.minutes)
        assert all(m >= -1e-12 for m in after.minutes.values())
        assert sum(after.minutes.values()) == pytest.approx(TEAM_MINUTES, abs=1e-6)

    def test_shedding_is_proportional_to_what_a_player_holds(self):
        """The direction the season transitions support: proportional-to-current beat
        uniform (t = -7.49) and bottom-of-the-chart-first (t = -7.99)."""
        roster = _roster()
        before = allocate_rotation(roster)
        after = allocate_rotation(
            roster + [RotationPlayer("x", "X", tei=1.0, baseline_minutes=24.0)],
            anchor=before.minutes,
        )
        ratios = [after.minutes[p.player_id] / before.minutes[p.player_id] for p in roster]
        assert max(ratios) - min(ratios) < 1e-6, "the cut was not proportional"
        assert all(r < 1.0 for r in ratios)

    def test_a_gutted_roster_charges_the_shortfall_to_replacement(self):
        roster = _roster()
        before = allocate_rotation(roster)
        after = allocate_rotation(
            _without(roster, *[f"p{i}" for i in range(10)]), anchor=before.minutes
        )
        assert after.unfilled_minutes > 0.8 * TEAM_MINUTES
        # Nearly the whole game is replacement level, so the team lands near it.
        assert after.team_tei_per_minute == pytest.approx(REPLACEMENT_TEI, abs=0.25)

    def test_an_empty_after_roster_is_exactly_replacement_level(self):
        roster = _roster()
        before = allocate_rotation(roster)
        after = allocate_rotation([], anchor=before.minutes)
        assert after.unfilled_minutes == pytest.approx(TEAM_MINUTES)
        assert after.team_tei_per_minute == pytest.approx(REPLACEMENT_TEI)


class TestAvailability:
    def test_availability_lowers_the_cost_of_losing_a_player(self):
        """A player who is only available half the time was only ever worth half of his
        value above replacement, so losing him costs half as much."""
        durable = _roster(availability=1.0)
        fragile = _roster(availability=0.5)
        b_d, b_f = allocate_rotation(durable), allocate_rotation(fragile)
        a_d = allocate_rotation(_without(durable, "p0"), anchor=b_d.minutes)
        a_f = allocate_rotation(_without(fragile, "p0"), anchor=b_f.minutes)
        loss_d = b_d.team_tei_per_minute - a_d.team_tei_per_minute
        loss_f = b_f.team_tei_per_minute - a_f.team_tei_per_minute
        assert loss_f < loss_d
        assert loss_f == pytest.approx(0.5 * loss_d, rel=1e-6)

    def test_an_unavailable_player_is_worth_replacement_and_costs_nothing(self):
        roster = _roster()
        roster.append(
            RotationPlayer("ghost", "Ghost", tei=5.0, baseline_minutes=20.0, availability=0.0)
        )
        before = allocate_rotation(roster)
        after = allocate_rotation(_without(roster, "ghost"), anchor=before.minutes)
        assert after.team_tei_per_minute == pytest.approx(before.team_tei_per_minute, abs=1e-12)


class TestDeterminismAndScale:
    def test_the_allocation_is_order_independent(self):
        roster = _roster()
        before = allocate_rotation(roster)
        a = allocate_rotation(_without(roster, "p5"), anchor=before.minutes)
        b = allocate_rotation(list(reversed(_without(roster, "p5"))), anchor=before.minutes)
        assert a.minutes == pytest.approx(b.minutes)
        assert a.team_tei_per_minute == pytest.approx(b.team_tei_per_minute)

    def test_user_overrides_still_bind_under_an_anchor(self):
        roster = _roster()
        before = allocate_rotation(roster)
        after_roster = _without(roster, "p0")
        after_roster[0].user_minutes = 40.0
        after = allocate_rotation(after_roster, anchor=before.minutes)
        assert after.minutes["p1"] == pytest.approx(DEFAULT_MAX_MINUTES)

    def test_the_level_model_is_untouched_by_the_release(self):
        """The proportional level model won the out-of-sample bake-off (MAE 5.803 over 60
        team-season transitions, against 8.641 for a depth-chart cascade and 8.148 for an
        equal-minutes null), so it is deliberately NOT changed. This pins that."""
        roster = _roster()
        result = allocate_rotation(roster)
        weights = np.array([max(p.baseline_minutes, 2.0) for p in roster])
        expected = TEAM_MINUTES * weights / weights.sum()
        for p, want in zip(roster, expected, strict=True):
            assert result.minutes[p.player_id] == pytest.approx(want, abs=1e-9)
