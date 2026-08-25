"""R3 — impact units and calibration.

The release turns an arbitrary index scale into net-rating points. Four things had to be
true at once, and each is asserted here because any one of them alone produces numbers
that look plausible and are wrong:

1. **One metric.** The ridge is retired; nothing in the serving path can select it.
2. **One scale.** Train and serve z-score against the same reference, so the fitted
   coefficient means the same thing in both. Before the fix the two constructions
   correlated r = 0.387 at team level and the two rescalings that implied disagreed by
   2.6x — proof that no transfer factor existed.
3. **One denominator.** Team impact is normalised by the 240 minutes a team must field,
   not by the minutes this roster happened to fill, and the shortfall is charged to a
   replacement-level player rather than silently redistributed.
4. **One `delta_net`.** The point estimate and the Monte Carlo read the same allocation
   and apply the same coefficient.
"""

import numpy as np
import pandas as pd
import pytest
from sqlalchemy.orm import Session

from app.analytics.impact import (
    SIGMA_INTERCEPT,
    SIGMA_PER_MINUTE,
    TEI_SCALE,
    baseline_index,
    score_players,
    sigma_for_minutes,
    train_impact_models,
)
from app.analytics.projection import (
    REPLACEMENT_TEI,
    TEAM_MINUTES,
    TEI_REGRESSOR_CONSTRUCTION,
    TEI_TO_NET_RATING,
    RotationPlayer,
    RotationResult,
    allocate_rotation,
    calibrate_tei_to_net_rating,
    team_tei_to_net_rating_delta,
)

SEASONS = ["2023-24", "2024-25", "2025-26"]


def _season_frame(n_per_season: int = 60) -> pd.DataFrame:
    rng = np.random.default_rng(5)
    rows = []
    for season in SEASONS:
        for i in range(n_per_season):
            rows.append(
                {
                    "player_id": f"p{i}",
                    "season": season,
                    "total_minutes": float(400 + (i % 20) * 120),
                    "pts_per75": float(rng.normal(16, 5)),
                    "TS_PCT": float(rng.normal(0.55, 0.05)),
                    "AST_PCT": float(rng.normal(0.15, 0.06)),
                    "TM_TOV_PCT": float(rng.normal(0.12, 0.02)),
                    "USG_PCT": float(rng.normal(0.20, 0.05)),
                    "OREB_PCT": float(rng.normal(0.05, 0.02)),
                    "DREB_PCT": float(rng.normal(0.14, 0.04)),
                    "stl_per_min": float(rng.normal(0.03, 0.01)),
                    "blk_per_min": float(rng.normal(0.02, 0.01)),
                    "PIE": float(rng.normal(0.10, 0.03)),
                    "NET_RATING": float(rng.normal(0, 5)),
                    "MIN": float(rng.normal(24, 7)),
                    "fg3a_rate": float(rng.normal(0.35, 0.1)),
                    "fta_rate": float(rng.normal(0.25, 0.08)),
                    "full_name": f"P{i}",
                    "nba_player_id": i,
                    "height_inches": 78,
                    "position": "F",
                    "is_active": True,
                }
            )
    return pd.DataFrame(rows)


# ------------------------------------------------------------------ 1. one metric


class TestTheRidgeIsRetired:
    def test_training_always_chooses_the_transparent_index(self) -> None:
        result = train_impact_models(_season_frame(), SEASONS)
        assert result.chosen_model == "baseline_index"
        assert "index" in result.algorithm

    def test_no_ridge_survives_anywhere_in_the_result(self) -> None:
        result = train_impact_models(_season_frame(), SEASONS)
        assert not hasattr(result, "ridge")
        assert result.coefficients, "the index IS its coefficients; they must be recorded"

    def test_the_serving_path_imports_no_estimator(self) -> None:
        """A structural check: an estimator that cannot be imported cannot be served."""
        from pathlib import Path

        source = (Path(__file__).resolve().parents[2] / "app" / "analytics" / "impact.py").read_text()
        assert "from sklearn.linear_model import Ridge" not in source
        assert "Ridge(" not in source

    def test_the_retirement_is_recorded_with_its_reason(self) -> None:
        validation = train_impact_models(_season_frame(), SEASONS).validation
        assert "0.0039" in validation["retired_ridge_note"]
        assert "0.7505" in validation["retired_ridge_note"]


# -------------------------------------------------------------------- 2. one scale


class TestTrainAndServeShareOneScale:
    def test_served_rows_use_the_reference_season_moments(self) -> None:
        frame = _season_frame()
        result = train_impact_models(frame, SEASONS)
        assert result.reference_season == SEASONS[-1]
        assert result.reference_moments, "no reference means serving against the wrong population"

    def test_a_served_player_matches_their_own_season_score(self) -> None:
        """The property the coefficient depends on: a player whose window is exactly one
        season must score the same served as they do in that season."""
        frame = _season_frame()
        result = train_impact_models(frame, SEASONS)

        latest = frame[frame["season"] == SEASONS[-1]].copy()
        from app.analytics.impact import add_zscores

        season_scored = add_zscores(latest.copy())
        season_scored["season_tei"] = baseline_index(season_scored)

        window = latest.copy()
        window["total_minutes_window"] = window["total_minutes"]
        served = score_players(window, result, frame)

        merged = season_scored[["player_id", "season_tei"]].merge(
            served[["player_id", "tei"]], on="player_id"
        )
        assert len(merged) > 20
        assert merged["tei"].to_numpy() == pytest.approx(
            merged["season_tei"].to_numpy(), abs=1e-9
        )


# --------------------------------------------------------------- 3. one denominator


class TestTheDenominatorIsTeamMinutes:
    def test_a_full_rotation_averages_to_its_players(self) -> None:
        players = [RotationPlayer(f"p{i}", f"P{i}", tei=2.0, baseline_minutes=24.0) for i in range(10)]
        assert allocate_rotation(players).team_tei_per_minute == pytest.approx(2.0, abs=1e-9)

    def test_unfilled_minutes_are_charged_to_replacement_not_redistributed(self) -> None:
        players = [RotationPlayer(f"p{i}", f"P{i}", tei=2.0, baseline_minutes=24.0) for i in range(3)]
        result = allocate_rotation(players)
        filled = sum(result.minutes.values())
        assert filled < TEAM_MINUTES
        expected = (filled / TEAM_MINUTES) * 2.0 + ((TEAM_MINUTES - filled) / TEAM_MINUTES) * REPLACEMENT_TEI
        assert result.team_tei_per_minute == pytest.approx(expected, abs=1e-9)

    def test_replacement_level_is_not_the_old_hardcoded_value(self) -> None:
        """-2.0 sat at the 14.1st percentile of player-season TEI: a rotation player, not
        a replacement one. The current value is derived from a stated rule."""
        assert REPLACEMENT_TEI != -2.0
        assert -2.0 < REPLACEMENT_TEI < 0.0

    def test_losing_players_can_never_raise_the_team(self) -> None:
        """The QA-1 mechanism, stated as a property rather than a threshold."""
        full = [RotationPlayer(f"p{i}", f"P{i}", tei=1.5, baseline_minutes=24.0) for i in range(10)]
        for keep in range(1, 10):
            thinner = allocate_rotation(full[:keep]).team_tei_per_minute
            assert thinner <= allocate_rotation(full[: keep + 1]).team_tei_per_minute + 1e-9


# ------------------------------------------------------------- 4. one conversion


class TestTheConversionIsFittedNotAssumed:
    def test_the_coefficient_is_neither_one_nor_five(self) -> None:
        """1.0 was the old implicit assumption ("TEI is already net-rating points"); 5 is
        the players-on-court factor the audit proposed. The fit says neither."""
        assert TEI_TO_NET_RATING > 10
        assert abs(TEI_TO_NET_RATING - 1.0) > 1.0
        assert abs(TEI_TO_NET_RATING - 5.0) > 1.0

    def test_the_delta_helper_applies_it(self) -> None:
        before = RotationResult(minutes={}, team_tei_per_minute=0.10)
        after = RotationResult(minutes={}, team_tei_per_minute=0.30)
        assert team_tei_to_net_rating_delta(before, after) == pytest.approx(
            TEI_TO_NET_RATING * 0.20, abs=1e-9
        )

    def test_no_literal_five_multiplies_team_impact(self) -> None:
        from pathlib import Path

        root = Path(__file__).resolve().parents[2] / "app"
        for path in root.rglob("*.py"):
            source = path.read_text()
            assert "PLAYERS_ON_COURT" not in source, f"{path.name} still carries the ×5 factor"

    def test_the_fit_reports_everything_needed_to_judge_it(self) -> None:
        rng = np.random.default_rng(3)
        d_tei = rng.normal(0, 0.25, 60)
        rows = pd.DataFrame(
            {
                "team_id": [f"t{i % 30}" for i in range(60)],
                "transition": ["a->b"] * 30 + ["b->c"] * 30,
                "d_tei": d_tei,
                "d_net": 15.0 * d_tei + rng.normal(0, 3, 60),
            }
        )
        fit = calibrate_tei_to_net_rating(rows)
        assert fit["calibrated"] is True
        assert fit["slope_t"] > 5, "the R3 gate requires a slope significant at t > 5"
        assert set(fit["per_fold_slopes"]) == {"a->b", "b->c"}
        for fold in fit["leave_one_transition_out"].values():
            assert fold["share_of_predict_zero"] < 0.75, "must beat predicting zero"
        assert fit["regressor_construction"] == TEI_REGRESSOR_CONSTRUCTION

    def test_an_uncalibratable_input_falls_back_and_says_so(self) -> None:
        fit = calibrate_tei_to_net_rating(pd.DataFrame())
        assert fit["calibrated"] is False
        assert fit["coefficient"] == TEI_TO_NET_RATING


# --------------------------------------------------------- 5. per-player intervals


class TestPerPlayerIntervals:
    def test_sigma_falls_with_playing_time(self) -> None:
        values = [sigma_for_minutes(m) for m in (300, 800, 1500, 2500)]
        assert values == sorted(values, reverse=True)

    def test_sigma_matches_the_documented_model(self) -> None:
        assert sigma_for_minutes(1000) == pytest.approx(
            np.sqrt(SIGMA_INTERCEPT + SIGMA_PER_MINUTE / 1000), abs=1e-12
        )

    def test_the_band_narrows_for_rotation_players_and_widens_for_fringe_ones(self) -> None:
        """Two framing hazards, pinned together.

        The old constant (sigma 2.462, from a retired model's residual spread) was
        identical for a 2,800-minute starter and a 300-minute rookie. Replacing it makes
        most bands *narrower*, which reads as overconfidence when it is the opposite —
        and it makes the thinnest-evidence players' bands **wider**, which is the part
        that would be quietly dropped if the release were summarised as "tighter
        intervals". The crossover is around 257 minutes, just above the 200-minute
        modelling floor.
        """
        old_constant_sigma = 2.4620
        for minutes in (600, 1000, 2000, 3000):
            assert sigma_for_minutes(minutes) * TEI_SCALE < old_constant_sigma
        # A player barely over the modelling floor is now told they are less certain.
        assert sigma_for_minutes(200) * TEI_SCALE > old_constant_sigma

    def test_bands_vary_across_a_scored_population(self) -> None:
        frame = _season_frame()
        result = train_impact_models(frame, SEASONS)
        window = frame[frame["season"] == SEASONS[-1]].copy()
        window["total_minutes_window"] = window["total_minutes"]
        served = score_players(window, result, frame)

        widths = (served["tei_high"] - served["tei_low"]).round(6)
        assert widths.nunique() > 1, "a constant band is the defect this replaced"
        rho = served[["total_minutes_window", "tei_sigma"]].corr(method="spearman").iloc[0, 1]
        assert rho < -0.95, f"band width must fall monotonically with minutes (rho={rho})"


# ------------------------------------------------- the fitted value stays the served one


def test_the_served_coefficient_matches_the_registered_fit(db: Session) -> None:
    """A retrain that moves the coefficient must not leave the constant behind.

    The conversion is a module constant so that every caller applies the same number
    without a database round-trip. That is only safe if a divergence is loud, so this
    fails the suite when the registered fit and the served constant disagree.
    """
    import json

    from app.db.models import ModelVersion

    row = db.scalar(
        ModelVersion.__table__.select().where(
            ModelVersion.model_name == "tei_to_net_rating", ModelVersion.is_active
        )
    )
    if row is None:
        pytest.skip("no tei_to_net_rating model registered in this database")
    metrics = row.validation_metrics
    if isinstance(metrics, str):
        metrics = json.loads(metrics)
    if not metrics.get("calibrated"):
        pytest.skip("the registered conversion is an uncalibrated fallback")
    assert metrics["coefficient"] == pytest.approx(TEI_TO_NET_RATING, rel=0.02), (
        "the registered fit and the served constant have diverged; update "
        "projection.TEI_TO_NET_RATING and re-run the R3 gate"
    )
