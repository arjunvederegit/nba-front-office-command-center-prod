"""The R3 calibration gate, re-run under R4's construction.

R4 changed the skill and feature path, so the R3 conversion coefficient could not simply
be assumed to survive. It was re-measured on the post-R4 code path and came back
**identical** — 14.976967 against the recorded 14.977, with every diagnostic reproducing
(SE 1.528, t 9.80, R2 0.6236, per-fold 14.716 / 15.276, LOTO OOS RMSE 2.944 / 3.773 at
56.6 % / 65.0 % of predicting zero).

It is preserved because the new measurement independently supports it, not because it
passed before. The reason it holds is structural and is asserted here: R4 added columns to
`MODEL_FEATURES` and derived new post-collapse quantities, but touched neither
`INDEX_WEIGHTS` nor `Z_SOURCE_COLS`, so the regressor the coefficient was fitted on is
byte-for-byte the same construction.

`test_impact_units.py::test_the_served_coefficient_matches_the_registered_fit` guards the
served constant against a retrain — but it **skips** when the database has no registered
fit, which is every CI run. So the most important assertion in the R3 gate never executed.
These tests do not skip.
"""

import numpy as np
import pandas as pd
import pytest

from app.analytics.features import MODEL_FEATURES
from app.analytics.impact import (
    INDEX_WEIGHTS,
    TEI_SCALE,
    Z_SOURCE_COLS,
    baseline_index,
)
from app.analytics.projection import (
    TEI_REGRESSOR_CONSTRUCTION,
    TEI_TO_NET_RATING,
    calibrate_tei_to_net_rating,
)

# The columns R4 introduced into the feature path.
R4_ADDED_COLUMNS = {
    "pf_per_min",
    "fg3a_per_min",
    "def_diff_raw",
    "def_impact",
    "fg3_pct_shrunk",
    "fg3a_window",
    "fg3m_window",
    "team_defense_score",
}


class TestR4DidNotMoveTheRegressor:
    """The coefficient is valid only for the construction recorded beside it. These are
    the structural reasons the re-measurement had to come back unchanged."""

    def test_no_r4_column_entered_the_index(self):
        """`baseline_index` sums `INDEX_WEIGHTS`. If an R4 column had been given a weight,
        team TEI would be a different quantity and 14.977 would be stale."""
        weighted = {key.removeprefix("z_") for key in INDEX_WEIGHTS}
        leaked = sorted(weighted & R4_ADDED_COLUMNS)
        assert leaked == [], (
            f"{leaked} entered INDEX_WEIGHTS, which redefines team TEI and invalidates "
            "the fitted conversion — refit it and update TEI_TO_NET_RATING"
        )

    def test_no_r4_column_entered_the_z_source_list(self):
        leaked = sorted(set(Z_SOURCE_COLS) & R4_ADDED_COLUMNS)
        assert leaked == []

    def test_the_r4_columns_really_are_in_the_feature_path(self):
        """Guard the guard: if R4's columns were never plumbed, the two tests above would
        pass vacuously and prove nothing."""
        plumbed = R4_ADDED_COLUMNS & set(MODEL_FEATURES)
        assert plumbed, "R4_ADDED_COLUMNS no longer matches the feature path"

    def test_the_index_reads_only_its_declared_weights(self):
        """A column present in the frame but absent from INDEX_WEIGHTS must contribute
        nothing — otherwise plumbing a feature would silently move TEI."""
        frame = pd.DataFrame(
            {key: np.linspace(-1.0, 1.0, 40) for key in INDEX_WEIGHTS}
        )
        before = baseline_index(frame)
        polluted = frame.copy()
        for col in R4_ADDED_COLUMNS:
            polluted[f"z_{col}"] = np.linspace(5.0, 50.0, 40)
        after = baseline_index(polluted)
        assert before.to_numpy() == pytest.approx(after.to_numpy())


class TestConversionRoundTrips:
    """Runs without a database, so it executes on every CI run."""

    # Calibrated to the real fit's signal-to-noise, so the R3 thresholds are exercised at
    # the difficulty they were set for rather than against easy or impossible data. On the
    # ingested history: 60 transitions, R2 0.6236, sd(d_net) ~ 5.5 — which implies
    # sd(d_tei) ~ 0.29 at a slope of 15 and a residual sd of ~3.4.
    D_TEI_SD = 0.29
    RESIDUAL_SD = 3.4

    @classmethod
    def _transitions(cls, slope: float, n: int = 60, noise: float | None = None) -> pd.DataFrame:
        rng = np.random.default_rng(4)
        d_tei = rng.normal(0.0, cls.D_TEI_SD, n)
        residual = cls.RESIDUAL_SD if noise is None else noise
        return pd.DataFrame(
            {
                "team_id": [f"t{i % 30}" for i in range(n)],
                "transition": ["a->b"] * (n // 2) + ["b->c"] * (n - n // 2),
                "d_tei": d_tei,
                "d_net": slope * d_tei + rng.normal(0.0, residual, n),
            }
        )

    def test_the_fixture_reproduces_the_real_fit_difficulty(self):
        """If the synthetic data were easier than reality, every threshold below would
        pass regardless of whether the machinery works."""
        result = calibrate_tei_to_net_rating(self._transitions(TEI_TO_NET_RATING))
        assert 0.4 < result["r2"] < 0.85, f"R2 {result['r2']:.3f} is not realistic"

    def test_the_fit_recovers_the_slope_it_was_given(self):
        result = calibrate_tei_to_net_rating(self._transitions(TEI_TO_NET_RATING))
        assert result["calibrated"] is True
        assert result["coefficient"] == pytest.approx(TEI_TO_NET_RATING, rel=0.15)

    def test_the_gate_diagnostics_are_all_reported(self):
        """R3 gates on each of these, so a refit that stopped reporting one would pass a
        gate it had not actually met."""
        result = calibrate_tei_to_net_rating(self._transitions(15.0))
        for key in (
            "coefficient",
            "slope_se",
            "slope_t",
            "r2",
            "n",
            "per_fold_slopes",
            "leave_one_transition_out",
            "regressor_construction",
        ):
            assert key in result, f"{key} missing from the calibration record"
        for fold in result["leave_one_transition_out"].values():
            assert {"oos_rmse", "predict_zero_rmse", "share_of_predict_zero"} <= set(fold)

    def test_a_real_signal_produces_a_significant_stable_fit(self):
        """The R3 gate's own thresholds — t > 5, per-fold within 15 %, out-of-sample RMSE
        under 4.5 and under 75 % of predicting zero — are asserted against the REAL
        registered fit in `test_impact_units.py`, and their measured values are in the
        release report. What is asserted here is that the machinery reaches them when the
        signal is genuinely there, at a noise level a third of the real residual.

        Deliberately not run at the real noise level: with 60 rows in two folds, whether a
        single random draw clears a threshold by a hair is seed luck, and choosing the seed
        that clears it is how a gate stops meaning anything.
        """
        result = calibrate_tei_to_net_rating(self._transitions(15.0, noise=1.0))
        assert abs(result["slope_t"]) > 5.0
        pooled = result["coefficient"]
        folds = list(result["per_fold_slopes"].values())
        assert len(folds) >= 2
        for slope in folds:
            assert abs(slope - pooled) / abs(pooled) < 0.15
        for fold in result["leave_one_transition_out"].values():
            assert fold["oos_rmse"] < 4.5
            assert fold["share_of_predict_zero"] < 0.75

    def test_pure_noise_produces_a_fit_the_gate_would_reject(self):
        """The other half of the same claim, and the one that makes it discriminating: if
        the diagnostics looked healthy on noise, passing them would prove nothing."""
        rng = np.random.default_rng(9)
        noise_only = pd.DataFrame(
            {
                "team_id": [f"t{i % 30}" for i in range(60)],
                "transition": ["a->b"] * 30 + ["b->c"] * 30,
                "d_tei": rng.normal(0.0, self.D_TEI_SD, 60),
                "d_net": rng.normal(0.0, 5.5, 60),
            }
        )
        result = calibrate_tei_to_net_rating(noise_only)
        assert abs(result["slope_t"]) < 5.0
        assert result["r2"] < 0.2
        assert any(
            fold["share_of_predict_zero"] >= 0.75
            for fold in result["leave_one_transition_out"].values()
        )

    def test_too_few_transitions_returns_an_uncalibrated_fallback(self):
        """The fallback must be flagged, not passed off as a fit."""
        result = calibrate_tei_to_net_rating(self._transitions(15.0, n=10))
        assert result["calibrated"] is False
        assert result["coefficient"] == pytest.approx(TEI_TO_NET_RATING)

    def test_an_empty_frame_does_not_raise(self):
        result = calibrate_tei_to_net_rating(pd.DataFrame())
        assert result["calibrated"] is False
        assert result["n"] == 0


class TestServedConstant:
    def test_the_coefficient_is_not_the_identity_or_the_naive_five(self):
        """The two values it would take if the index were already in net-rating units.
        R3 exists because it is neither."""
        assert TEI_TO_NET_RATING > 10.0
        assert abs(TEI_TO_NET_RATING - 1.0) > 1.0
        assert abs(TEI_TO_NET_RATING - 5.0) > 1.0

    def test_the_recorded_value_is_the_one_r4_re_measured(self):
        """Re-measured on the post-R4 pipeline against the ingested history: 14.976967.
        If a future change moves the construction, this must be refitted, not nudged."""
        assert pytest.approx(14.977, abs=0.001) == TEI_TO_NET_RATING

    def test_the_construction_is_documented_beside_the_constant(self):
        assert "minutes-weighted" in TEI_REGRESSOR_CONSTRUCTION
        assert "z-scored within season" in TEI_REGRESSOR_CONSTRUCTION

    def test_the_scale_is_unchanged_by_r4(self):
        assert pytest.approx(2.5) == TEI_SCALE
