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
    composite_utility,
    normalize_weights,
    rank_stability,
    tornado,
)
from app.analytics.uncertainty import PlayerDraw, simulate_delta_wins


class TestWeights:
    def test_normalization_sums_to_one(self):
        weights = normalize_weights({"a": 2, "b": 2, "c": 4})
        assert pytest.approx(sum(weights.values())) == 1.0
        assert weights["c"] == 0.5

    def test_negative_weights_clamped(self):
        weights = normalize_weights({"a": -1, "b": 1})
        assert weights["a"] == 0.0 and weights["b"] == 1.0

    def test_all_zero_becomes_uniform(self):
        weights = normalize_weights({"a": 0, "b": 0})
        assert weights == {"a": 0.5, "b": 0.5}


class TestCompositeUtility:
    def test_missing_component_excluded_and_renormalized(self):
        weights = {"performance": 0.5, "contract": 0.5}
        # contract unavailable → performance carries full weight
        assert composite_utility({"performance": 80, "contract": None}, weights) == 80
        # both available → average
        assert composite_utility({"performance": 80, "contract": 40}, weights) == 60

    def test_empty_components_scores_zero(self):
        assert composite_utility({"a": None}, {"a": 1.0}) == 0.0


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
        assert mapping["r2"] > 0.9

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
        assert age_delta(28) == 0.0
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
    def test_deterministic_with_seed(self):
        incoming = [PlayerDraw(tei=2.0, tei_sigma=1.0, availability=0.8, minutes_share=0.12)]
        outgoing = [PlayerDraw(tei=0.0, tei_sigma=1.0, availability=0.9, minutes_share=0.12)]
        a = simulate_delta_wins(incoming, outgoing, {"slope": 2.2})
        b = simulate_delta_wins(incoming, outgoing, {"slope": 2.2})
        assert a == b

    def test_better_player_in_gives_positive_median(self):
        result = simulate_delta_wins(
            [PlayerDraw(4.0, 0.5, 0.95, 0.15)],
            [PlayerDraw(-1.0, 0.5, 0.95, 0.15)],
            {"slope": 2.2},
        )
        assert result["median"] > 0
        assert result["prob_positive"] > 0.9
        assert result["p10"] < result["median"] < result["p90"]


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
