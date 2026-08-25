"""R4-4 — continuity, self-exclusion, and an allocator that respects its own caps.

Four defects, each reproduced before it was fixed:

1. `age_delta` stepped -0.35 TEI/yr at age 30, so a four-year projection moved 0.70 TEI
   between ages 29.99 and 30.01 — 0.59 sd of the TEI distribution for two days of age.
2. `timeline_alignment` stepped up to 0.35, and the 0..1 alignment becomes a 0..100
   component, so one year of age could move a scored component by 35 points of 100.
3. `needs._percentile` counted the team being scored among its own peers, deflating every
   percentile by exactly 29/30.
4. `allocate_rotation`'s clip-and-redistribute loop ended each pass on the redistribution
   with no re-clip, so it returned minutes ABOVE the per-player cap. The plan recorded
   this loop as unreachable; it is not.
"""

import numpy as np
import pandas as pd
import pytest

from app.analytics.age_curve import AGE_KNOTS, age_delta, project_tei, timeline_alignment
from app.analytics.needs import compute_team_needs
from app.analytics.projection import (
    DEFAULT_MAX_MINUTES,
    TEAM_MINUTES,
    RotationPlayer,
    allocate_rotation,
)

OLD_BOUNDARIES = (21, 24, 27, 30, 33, 36)


class TestAgeCurveIsContinuous:
    @pytest.mark.parametrize("boundary", OLD_BOUNDARIES)
    def test_no_step_survives_at_an_old_bucket_edge(self, boundary):
        jump = abs(age_delta(boundary + 1e-6) - age_delta(boundary - 1e-6))
        assert jump < 1e-4, f"age {boundary} still steps by {jump}"

    def test_the_age_30_projection_cliff_is_gone(self):
        """The measured headline: 0.70 TEI for two days of age."""
        before = project_tei(0.0, 29.99, 4)
        after = project_tei(0.0, 30.01, 4)
        assert abs(after - before) < 0.02, (
            f"29.99 -> {before:.4f}, 30.01 -> {after:.4f}; was a 0.70 TEI cliff"
        )

    def test_the_curve_is_monotone_non_increasing(self):
        ages = np.arange(18.0, 42.01, 0.25)
        deltas = [age_delta(a) for a in ages]
        assert all(b <= a + 1e-9 for a, b in zip(deltas, deltas[1:], strict=False))

    def test_area_is_preserved_against_the_step_curve_it_replaces(self):
        """The replacement asserts nothing NEW about magnitude — it only removes steps.
        If the integral moved, a cumulative projection would silently change."""

        def old_age_delta(age: float) -> float:
            if age < 21:
                return 0.8
            if age < 24:
                return 0.5
            if age < 27:
                return 0.2
            if age < 30:
                return 0.0
            if age < 33:
                return -0.35
            if age < 36:
                return -0.7
            return -1.0

        ages = np.arange(18.0, 42.0, 0.01)
        old_area = sum(old_age_delta(a) for a in ages) * 0.01
        new_area = sum(age_delta(a) for a in ages) * 0.01
        assert new_area == pytest.approx(old_area, abs=0.05)

    def test_the_tails_are_flat_rather_than_extrapolated(self):
        assert age_delta(10.0) == pytest.approx(AGE_KNOTS[0][1])
        assert age_delta(99.0) == pytest.approx(AGE_KNOTS[-1][1])


class TestTimelineAlignment:
    STRATEGIES = ["contend", "improve", "retool", "rebuild", "youth", "cap_relief", "custom"]

    @pytest.mark.parametrize("strategy", STRATEGIES)
    def test_one_year_of_age_never_swings_the_score_by_a_third(self, strategy):
        """Measured before the fix: 0.35 at a boundary, which is 35 points of the 0..100
        component built from it."""
        for age in np.arange(19.0, 40.0, 0.5):
            step = abs(
                timeline_alignment(age + 1.0, strategy) - timeline_alignment(age, strategy)
            )
            assert step <= 0.15, f"{strategy} moves {step:.3f} between {age} and {age + 1}"

    @pytest.mark.parametrize("strategy", STRATEGIES)
    def test_alignment_is_continuous(self, strategy):
        for age in np.arange(19.0, 40.0, 0.25):
            jump = abs(
                timeline_alignment(age + 1e-6, strategy)
                - timeline_alignment(age - 1e-6, strategy)
            )
            assert jump < 1e-4

    def test_alignment_takes_many_distinct_values(self):
        """Four reachable values per strategy is what collapsed the component to exactly
        50.0 for a quarter to two fifths of realistic one-for-one trades."""
        values = {round(timeline_alignment(a, "custom"), 6) for a in np.arange(19.0, 40.0, 0.25)}
        assert len(values) > 40

    def test_the_default_strategy_is_the_retool_shape(self):
        """`custom` is the default at every entry point; the audit reported 50.0 for the
        Tatum/Doncic case, which reproduces only under `contend`."""
        for age in (22.0, 27.0, 31.0):
            assert timeline_alignment(age, "custom") == timeline_alignment(age, "retool")

    def test_an_unknown_strategy_falls_back_rather_than_raising(self):
        assert timeline_alignment(27.0, "not-a-strategy") == timeline_alignment(27.0, "retool")

    def test_ordering_still_holds(self):
        assert timeline_alignment(27, "contend") > timeline_alignment(20, "contend")
        assert timeline_alignment(21, "rebuild") > timeline_alignment(31, "rebuild")


class TestNeedsExcludeSelf:
    @staticmethod
    def _league(n: int = 30) -> pd.DataFrame:
        return pd.DataFrame(
            {
                "team_id": [f"t{i}" for i in range(n)],
                "advanced_DEF_RATING": [100.0 + i for i in range(n)],
                "base_FG3A": [30.0 + i for i in range(n)],
            }
        )

    def test_the_league_leader_reaches_the_hundredth_percentile(self):
        """With itself counted, the best team in a category topped out at 96.7."""
        league = self._league()
        needs = compute_team_needs(
            {"base": {"FG3A": 59.0}, "advanced": {"DEF_RATING": 100.0}},
            league,
            team_id="t29",
        )
        by_key = {n.need_key: n for n in needs}
        assert by_key["three_point_volume"].percentile == pytest.approx(100.0)

    def test_excluding_self_raises_every_percentile_by_the_same_factor(self):
        league = self._league()
        stats = {"base": {"FG3A": 45.0}, "advanced": {"DEF_RATING": 115.0}}
        with_self = {n.need_key: n.percentile for n in compute_team_needs(stats, league)}
        without = {
            n.need_key: n.percentile
            for n in compute_team_needs(stats, league, team_id="t15")
        }
        for key, value in with_self.items():
            assert without[key] >= value
            assert value == pytest.approx(without[key] * 29 / 30, abs=0.35)

    def test_an_unknown_team_id_is_harmless(self):
        league = self._league()
        stats = {"base": {"FG3A": 45.0}, "advanced": {"DEF_RATING": 115.0}}
        assert compute_team_needs(stats, league, team_id="nobody") == compute_team_needs(
            stats, league
        )

    def test_a_frame_without_team_id_still_works(self):
        league = self._league().drop(columns=["team_id"])
        stats = {"base": {"FG3A": 45.0}, "advanced": {"DEF_RATING": 115.0}}
        assert compute_team_needs(stats, league, team_id="t3")


def _players(n: int, baseline: float = 30.0, cap: float = DEFAULT_MAX_MINUTES):
    return [
        RotationPlayer(
            player_id=f"p{i}", name=f"P{i}", tei=0.0, baseline_minutes=baseline, max_minutes=cap
        )
        for i in range(n)
    ]


class TestRotationRespectsCaps:
    @pytest.mark.parametrize("n", [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 12, 15, 18])
    def test_no_player_is_ever_allocated_above_his_cap(self, n):
        """The defect, across the whole roster-size range. Measured before the fix: 41.3
        minutes against a 36-minute ceiling on a seven-player roster, up to 204."""
        result = allocate_rotation(_players(n))
        for player in _players(n):
            assert result.minutes[player.player_id] <= player.max_minutes + 1e-6, (
                f"n={n}: {player.player_id} got {result.minutes[player.player_id]:.2f} "
                f"against a cap of {player.max_minutes}"
            )

    @pytest.mark.parametrize("n", [7, 8, 9, 10, 12])
    def test_a_feasible_roster_fills_the_full_240_minutes(self, n):
        result = allocate_rotation(_players(n))
        assert sum(result.minutes.values()) == pytest.approx(TEAM_MINUTES, abs=1e-6)

    def test_an_infeasible_roster_leaves_the_shortfall_unfilled(self):
        """Fewer players than 240 minutes needs: the gap must NOT be forced onto the
        players present. It is charged to a replacement player downstream (R3-3)."""
        result = allocate_rotation(_players(4))
        assert sum(result.minutes.values()) == pytest.approx(4 * DEFAULT_MAX_MINUTES)
        assert sum(result.minutes.values()) < TEAM_MINUTES

    def test_uneven_baselines_still_respect_caps(self):
        players = [
            RotationPlayer(f"p{i}", f"P{i}", 0.0, baseline_minutes=b, max_minutes=36.0)
            for i, b in enumerate([38.0, 34.0, 30.0, 8.0, 6.0, 4.0, 2.0])
        ]
        result = allocate_rotation(players)
        assert all(m <= 36.0 + 1e-6 for m in result.minutes.values())
        assert sum(result.minutes.values()) == pytest.approx(TEAM_MINUTES, abs=1e-6)

    def test_mixed_caps_are_honoured_individually(self):
        players = [
            RotationPlayer("a", "A", 0.0, baseline_minutes=30.0, max_minutes=20.0),
            RotationPlayer("b", "B", 0.0, baseline_minutes=30.0, max_minutes=36.0),
            RotationPlayer("c", "C", 0.0, baseline_minutes=30.0, max_minutes=36.0),
            RotationPlayer("d", "D", 0.0, baseline_minutes=30.0, max_minutes=36.0),
            RotationPlayer("e", "E", 0.0, baseline_minutes=30.0, max_minutes=36.0),
            RotationPlayer("f", "F", 0.0, baseline_minutes=30.0, max_minutes=36.0),
            RotationPlayer("g", "G", 0.0, baseline_minutes=30.0, max_minutes=36.0),
        ]
        result = allocate_rotation(players)
        assert result.minutes["a"] <= 20.0 + 1e-6
        assert all(result.minutes[k] <= 36.0 + 1e-6 for k in "bcdefg")

    def test_user_overrides_are_still_capped(self):
        players = _players(8)
        players[0].user_minutes = 60.0
        result = allocate_rotation(players)
        assert result.minutes["p0"] == pytest.approx(DEFAULT_MAX_MINUTES)

    def test_allocation_is_deterministic(self):
        first = allocate_rotation(_players(9)).minutes
        second = allocate_rotation(_players(9)).minutes
        assert first == second

    def test_an_empty_roster_does_not_raise(self):
        result = allocate_rotation([])
        assert result.minutes == {}
