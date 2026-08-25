"""Analytics unit tests: weights, sensitivity, projection, availability, age curve,
uncertainty, fit, impact primitives."""

import numpy as np
import pandas as pd
import pytest

from app.analytics.age_curve import age_delta, project_tei, timeline_alignment
from app.analytics.availability import availability_from_history
from app.analytics.features import recency_weighted_features, zscore_by_season
from app.analytics.fit import fit_score
from app.analytics.impact import INDEX_WEIGHTS, baseline_index
from app.analytics.projection import (
    RotationPlayer,
    allocate_rotation,
    calibrate_wins_per_net_rating,
    net_rating_delta_to_wins,
)
from app.analytics.sensitivity import (
    component_contributions,
    composite_utility,
    normalize_weights,
    rank_stability,
    tornado,
)
from app.analytics.uncertainty import PlayerDraw, RotationDraw, simulate_delta_wins


class TestWeights:
    def test_normalization_sums_to_one(self):
        weights = normalize_weights({"a": 2, "b": 2, "c": 4})
        assert pytest.approx(sum(weights.values())) == 1.0
        assert weights["c"] == 0.5

    def test_negative_weights_clamped(self):
        weights = normalize_weights({"a": -1, "b": 1})
        assert weights["a"] == 0.0 and weights["b"] == 1.0

    def test_all_zero_stays_zero(self):
        """Replaces `test_all_zero_becomes_uniform` (R1-3).

        The old invariant encoded a defect: zeroing every slider is a deliberate act, and
        substituting a uniform prior silently re-enabled every component the user had
        switched off, then produced a score from them.
        """
        assert normalize_weights({"a": 0, "b": 0}) == {"a": 0.0, "b": 0.0}


class TestCompositeUtility:
    def test_missing_component_excluded_and_renormalized(self):
        weights = {"performance": 0.5, "contract": 0.5}
        # contract unavailable → performance carries full weight
        assert composite_utility({"performance": 80, "contract": None}, weights) == 80
        # both available → average
        assert composite_utility({"performance": 80, "contract": 40}, weights) == 60

    def test_nothing_scorable_returns_none_not_zero(self):
        """Replaces `test_empty_components_scores_zero` (R1-3).

        On a 0..100 scale, 0.0 reads as a catastrophic verdict — the opposite of "we
        cannot say" — and contradicted the module's own docstring.
        """
        assert composite_utility({"a": None}, {"a": 1.0}) is None

    def test_all_weight_removed_returns_none(self):
        """Every scorable component weighted to zero leaves nothing to average."""
        assert composite_utility({"a": 80, "b": 40}, {"a": 0.0, "b": 0.0}) is None

    def test_contributions_reconcile_with_the_composite(self):
        """The property the driver panel exists to satisfy, including the excluded case."""
        weights = {"performance": 0.5, "contract": 0.3, "risk": 0.2}
        components = {"performance": 80.0, "contract": None, "risk": 30.0}
        utility = composite_utility(components, weights)
        assert utility is not None
        summed = sum(float(r["contribution"]) for r in component_contributions(components, weights))
        assert summed == pytest.approx(utility - 50.0, abs=0.02)


class TestSensitivity:
    def test_rank_stability_is_deterministic(self):
        alts = {"t1": {"performance": 70, "risk": 60}, "t2": {"performance": 50, "risk": 55}}
        weights = {"performance": 0.5, "risk": 0.5}
        a = rank_stability(alts, weights)
        b = rank_stability(alts, weights)
        assert a == b
        assert a["first_place_share"]["t1"] > 0.9

    def test_tornado_sorted_by_swing(self):
        bars = tornado({"performance": 90, "risk": 45}, {"performance": 0.6, "risk": 0.4})
        swings = [abs(b["utility_high"] - b["utility_low"]) for b in bars]
        assert swings == sorted(swings, reverse=True)


class TestRotationAllocator:
    def _players(self, n=10, minutes=30.0):
        return [
            RotationPlayer(player_id=f"p{i}", name=f"P{i}", tei=0.0, baseline_minutes=minutes)
            for i in range(n)
        ]

    def test_total_minutes_conserved(self):
        result = allocate_rotation(self._players(10))
        assert pytest.approx(sum(result.minutes.values()), abs=1.0) == 240.0

    def test_max_minutes_respected(self):
        players = self._players(8, minutes=40.0)
        result = allocate_rotation(players)
        assert all(m <= 36.0 + 1e-6 for m in result.minutes.values())

    def test_user_override_honored(self):
        players = self._players(10)
        players[0].user_minutes = 12.0
        result = allocate_rotation(players)
        assert result.minutes["p0"] == 12.0

    def test_availability_discounts_impact(self):
        healthy = allocate_rotation(
            [RotationPlayer("p", "P", tei=5.0, baseline_minutes=240, availability=1.0)]
        )
        fragile = allocate_rotation(
            [RotationPlayer("p", "P", tei=5.0, baseline_minutes=240, availability=0.5)]
        )
        assert fragile.team_tei_per_minute < healthy.team_tei_per_minute


class TestWinsCalibration:
    def test_fallback_flagged_when_insufficient_data(self):
        mapping = calibrate_wins_per_net_rating(pd.DataFrame({"net_rating": [], "wins": []}))
        assert mapping["calibrated"] is False
        assert mapping["slope"] == 2.7

    def test_recovers_known_linear_relationship(self):
        rng = np.random.default_rng(7)
        net = rng.normal(0, 5, 60)
        wins = 41 + 2.5 * net + rng.normal(0, 1, 60)
        mapping = calibrate_wins_per_net_rating(pd.DataFrame({"net_rating": net, "wins": wins}))
        assert mapping["calibrated"] is True
        assert 2.3 < mapping["slope"] < 2.7
        # R3-2: `r2` was renamed to say which one it is. LOO is the honest figure to
        # report for a fit this small, and reporting the in-sample number as if it were
        # out-of-sample was the actual defect here — the model itself is fine.
        assert mapping["r2_in_sample"] > 0.9
        assert mapping["r2_loo"] > 0.9
        assert mapping["r2_loo"] <= mapping["r2_in_sample"]

    def test_the_slope_carries_its_own_standard_error(self):
        """The interval over the conversion needs the SLOPE's SE, not the spread of wins
        about the line. The latter is ~55x larger and made every band that much too wide."""
        rng = np.random.default_rng(11)
        net = rng.normal(0, 5, 60)
        wins = 41 + 2.5 * net + rng.normal(0, 1, 60)
        mapping = calibrate_wins_per_net_rating(pd.DataFrame({"net_rating": net, "wins": wins}))
        assert mapping["slope_se"] < mapping["residual_std"]
        assert mapping["slope_t"] > 5

    def test_delta_scaling_by_games_remaining(self):
        mapping = {"slope": 2.0}
        assert net_rating_delta_to_wins(1.0, mapping) == 2.0
        assert net_rating_delta_to_wins(1.0, mapping, games_remaining=41) == 1.0


class TestAvailability:
    def test_weighted_gp_share(self):
        df = pd.DataFrame(
            [
                {"player_id": "a", "season": "2024-25", "GP": 82},
                {"player_id": "a", "season": "2025-26", "GP": 41},
                {"player_id": "b", "season": "2025-26", "GP": 82},
            ]
        )
        out = availability_from_history(df, ["2024-25", "2025-26"], decay=1.0)
        by_id = out.set_index("player_id")["availability"]
        assert by_id["a"] == pytest.approx(123 / 164)
        # single-season player measured against only their observed seasons
        assert by_id["b"] == pytest.approx(1.0)


class TestAgeCurve:
    def test_young_players_improve_old_players_decline(self):
        assert age_delta(20) > 0
        # The plateau sits at the midpoint of the old 27..30 bucket, not at its left
        # edge: the curve is now the linear interpolant through those midpoints (R4-4).
        assert age_delta(28.5) == pytest.approx(0.0)
        assert age_delta(34) < 0

    def test_projection_accumulates(self):
        assert project_tei(2.0, 34, 2) < 2.0
        assert project_tei(0.0, 20, 2) > 0.5

    def test_timeline_alignment_prefers_matching_ages(self):
        assert timeline_alignment(27, "contend") > timeline_alignment(20, "contend")
        assert timeline_alignment(21, "rebuild") > timeline_alignment(31, "rebuild")


class TestFit:
    def test_addressing_needs_scores_positive(self):
        score, detail = fit_score(
            needs={"three_point_volume": 0.8},
            incoming=[({"shooting": 0.9}, 30.0)],
            outgoing=[({"shooting": 0.2}, 30.0)],
            roster_strengths={"shooting": 0.3},
            need_to_skill={"three_point_volume": "shooting"},
        )
        assert score > 0
        assert detail["needs_addressed"]["three_point_volume"] > 0

    def test_redundancy_penalized(self):
        score_redundant, detail = fit_score(
            needs={},
            incoming=[({"rim_protection": 0.95}, 30.0)],
            outgoing=[({"rim_protection": 0.5}, 30.0)],
            roster_strengths={"rim_protection": 0.95},
            need_to_skill={},
        )
        assert score_redundant < 0
        assert detail["redundancies"]


class TestUncertainty:
    """The simulation compares two whole rotations, not two lists of moved players
    (R3-5) — that is what lets its median reproduce the point estimate."""

    @staticmethod
    def _bench(n: int = 8, share: float = 0.09) -> list[PlayerDraw]:
        return [
            PlayerDraw(tei=0.2 * i, tei_sigma=0.5, availability=0.9, minutes_share=share, key=f"b{i}")
            for i in range(n)
        ]

    def test_deterministic_with_seed(self):
        bench = self._bench()
        before = RotationDraw(bench + [PlayerDraw(0.0, 1.0, 0.9, 0.12, key="x")])
        after = RotationDraw(bench + [PlayerDraw(2.0, 1.0, 0.8, 0.12, key="y")])
        assert simulate_delta_wins(before, after, {"slope": 2.2}) == simulate_delta_wins(
            before, after, {"slope": 2.2}
        )

    def test_better_player_in_gives_positive_median(self):
        bench = self._bench()
        result = simulate_delta_wins(
            RotationDraw(bench + [PlayerDraw(-1.0, 0.5, 0.95, 0.15, key="out")]),
            RotationDraw(bench + [PlayerDraw(4.0, 0.5, 0.95, 0.15, key="in")]),
            {"slope": 2.2},
        )
        assert result["median"] > 0
        assert result["prob_positive"] > 0.9
        assert result["p10"] < result["median"] < result["p90"]

    def test_an_identical_rotation_reports_no_distribution(self):
        rotation = RotationDraw(self._bench())
        result = simulate_delta_wins(rotation, rotation, {"slope": 2.2})
        assert result["prob_positive"] is None
        assert result["n_draws"] == 0

    def test_incumbents_cancel_exactly(self):
        """An incumbent on both sides draws from one stream, so their noise cancels
        rather than widening the interval. Without it the band grows with roster size."""
        swap = [PlayerDraw(-1.0, 0.5, 0.95, 0.15, key="out")], [
            PlayerDraw(4.0, 0.5, 0.95, 0.15, key="in")
        ]
        narrow = simulate_delta_wins(
            RotationDraw(self._bench(2) + swap[0]),
            RotationDraw(self._bench(2) + swap[1]),
            {"slope": 2.2},
        )
        wide = simulate_delta_wins(
            RotationDraw(self._bench(8) + swap[0]),
            RotationDraw(self._bench(8) + swap[1]),
            {"slope": 2.2},
        )
        assert (wide["p90"] - wide["p10"]) == pytest.approx(
            narrow["p90"] - narrow["p10"], rel=1e-9
        )


class TestImpactPrimitives:
    def _frame(self):
        rng = np.random.default_rng(3)
        return pd.DataFrame(
            {
                "player_id": [f"p{i}" for i in range(40)],
                "season": ["2025-26"] * 40,
                "full_name": [f"P{i}" for i in range(40)],
                "nba_player_id": range(40),
                "height_inches": 78,
                "position": "F",
                "is_active": True,
                "GP": 70,
                "MIN": 28.0,
                "total_minutes": 70 * 28.0,
                "pts_per75": rng.normal(20, 5, 40),
                "TS_PCT": rng.normal(0.57, 0.04, 40),
            }
        )

    def test_zscore_centering(self):
        df = zscore_by_season(self._frame(), "pts_per75")
        assert abs(df["z_pts_per75"].mean()) < 0.15

    def test_baseline_index_rewards_scoring(self):
        df = self._frame()
        df = zscore_by_season(df, "pts_per75")
        df = zscore_by_season(df, "TS_PCT")
        index = baseline_index(df)
        top = df.loc[index.idxmax()]
        assert top["pts_per75"] > df["pts_per75"].median()

    def test_index_weights_documented_and_bounded(self):
        assert sum(abs(w) for w in INDEX_WEIGHTS.values()) > 0
        assert all(abs(w) <= 0.25 for w in INDEX_WEIGHTS.values())

    def test_recency_weighting_prefers_recent_seasons(self):
        df = pd.DataFrame(
            [
                {
                    "player_id": "a",
                    "season": "2024-25",
                    "full_name": "A",
                    "nba_player_id": 1,
                    "height_inches": 78,
                    "position": "F",
                    "is_active": True,
                    "GP": 70,
                    "MIN": 30.0,
                    "total_minutes": 2100.0,
                    "PIE": 0.05,
                },
                {
                    "player_id": "a",
                    "season": "2025-26",
                    "full_name": "A",
                    "nba_player_id": 1,
                    "height_inches": 78,
                    "position": "F",
                    "is_active": True,
                    "GP": 70,
                    "MIN": 30.0,
                    "total_minutes": 2100.0,
                    "PIE": 0.15,
                },
            ]
        )
        out = recency_weighted_features(df, ["2024-25", "2025-26"], decay=0.5)
        # recent season (PIE 0.15) weighted 2x older (0.05): (0.15*1 + 0.05*0.5)/1.5
        assert out.iloc[0]["PIE"] == pytest.approx((0.15 + 0.025) / 1.5)


def test_percentile_explanations_use_a_real_ordinal():
    """A team in the third percentile was told it ranked "3th" — in the team-outlook
    panel, in every acquisition explanation and in the decision memo, all of which quote
    this string verbatim."""
    from app.analytics.needs import ordinal

    assert [ordinal(n) for n in (1, 2, 3, 4, 11, 12, 13, 21, 52, 100)] == [
        "1st",
        "2nd",
        "3rd",
        "4th",
        "11th",
        "12th",
        "13th",
        "21st",
        "52nd",
        "100th",
    ]


def test_need_explanations_render_the_ordinal(monkeypatch):
    import pandas as pd

    from app.analytics.needs import compute_team_needs

    league = pd.DataFrame(
        {
            "team_id": [f"t{i}" for i in range(10)],
            "base_FG3A": list(range(30, 40)),
        }
    )
    # 33 sits above three of the nine peers (31, 32, 33 excluded), so the percentile is
    # 33.3 and the string must read "33rd", not "33th".
    results = compute_team_needs({"base": {"FG3A": 34}}, league, team_id="t0")
    explanation = next(r.explanation for r in results if r.need_key == "three_point_volume")
    assert "rd percentile" in explanation
    assert "th percentile" not in explanation
