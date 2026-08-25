"""R5-2. The empirical pick-value curve, and the precision it refuses to claim.

Two classes of test here, and the second is the point of the file.

The first pins the mechanics: the curve is monotone, the band is never a point, absence is
a measured zero rather than a dropped row.

The second pins the **refusals**. A protected pick has no point estimate. A swapped pick
has no point estimate. An unverified pick has no point estimate. A pick five years out
spans essentially the whole round. Those are the assertions that stop a future change from
quietly turning a range back into a number.
"""

import numpy as np
import pandas as pd
import pytest

from app.analytics.picks import (
    DEFAULT_ESTIMATION_CLASSES,
    LOTTERY_MAX_FALL,
    PICK_CURVE_A,
    PICK_CURVE_B,
    PICK_CURVE_C,
    UNINFORMED_RANK_SD,
    PickTerms,
    build_draft_outcomes,
    expected_rank_from_win_pct,
    fit_pick_value_curve,
    fit_rank_persistence,
    landing_slot_support,
    pick_value,
    protection_range,
    rank_uncertainty,
    relative_pick_value,
    value_band,
)
from app.analytics.projection import REPLACEMENT_TEI


class TestTheCurve:
    def test_it_is_strictly_decreasing_over_both_rounds(self):
        values = [relative_pick_value(k) for k in range(1, 61)]
        assert all(b < a for a, b in zip(values, values[1:], strict=False))

    def test_the_first_pick_is_worth_multiples_of_a_late_first(self):
        assert relative_pick_value(1) / relative_pick_value(30) == pytest.approx(6.6, abs=0.3)

    def test_a_late_second_is_not_worth_zero(self):
        """The asymptote is fitted, not assumed. Second-rounders produce rotation players
        often enough that pricing them at nothing would be its own fabrication."""
        assert relative_pick_value(60) > 0.2

    def test_the_committed_constants_are_the_fitted_ones(self):
        assert (PICK_CURVE_A, PICK_CURVE_B, PICK_CURVE_C) == (3.3855, 0.08388, 0.2525)

    def test_the_band_always_brackets_the_point(self):
        for slot in (1, 5, 14, 15, 30, 31, 45, 60):
            low, high = value_band(slot)
            assert low < relative_pick_value(slot) < high

    def test_the_band_is_never_narrow_enough_to_imply_a_point(self):
        """Measured: 73 % of the value at slot 1, 150 % at slot 60. If a future refit ever
        produced a band tighter than a fifth of the value, the resampling would be
        claiming a precision 8 draft classes cannot support."""
        for slot in (1, 10, 30, 60):
            low, high = value_band(slot)
            assert (high - low) / relative_pick_value(slot) > 0.2


class TestLandingSlot:
    def test_a_terrible_team_picks_near_the_top(self):
        assert expected_rank_from_win_pct(0.150) == pytest.approx(30.0)
        assert expected_rank_from_win_pct(0.850) == pytest.approx(1.0)

    def test_uncertainty_grows_with_years_out_and_then_stops(self):
        one = rank_uncertainty(1, one_year_sd=3.0)
        two = rank_uncertainty(2, one_year_sd=3.0)
        assert two > one
        assert rank_uncertainty(50, one_year_sd=3.0) == pytest.approx(UNINFORMED_RANK_SD)

    def test_this_years_pick_has_no_drift(self):
        support = landing_slot_support(0.300, years_out=0)
        assert support["rank_sd"] == 0.0

    def test_a_lottery_exposed_pick_spans_the_lottery(self):
        """Structural, not probabilistic. The draw can lift any lottery team to first and
        can push it down at most four places; this module does not model the odds and says
        so instead of inventing them."""
        support = landing_slot_support(0.250, years_out=1)
        assert support["lottery_exposed"] is True
        assert support["min_slot"] == 1
        assert "does not model the draw" in support["basis"]

    def test_a_contender_is_not_lottery_exposed_this_year(self):
        """A 0.800 team is the league's third-best record, so its own pick lands near the
        end of the round and the draw cannot touch it. With no years of drift the support
        is one rounding of the central slot wide, which is the only case in this module
        where the answer is nearly a point."""
        support = landing_slot_support(0.800, years_out=0)
        assert support["lottery_exposed"] is False
        assert support["central_slot"] == pytest.approx(27.9, abs=0.2)
        assert (support["min_slot"], support["max_slot"]) == (27, 28)

    def test_no_standings_means_the_whole_round(self):
        support = landing_slot_support(None, years_out=2)
        assert (support["min_slot"], support["max_slot"]) == (1, 30)
        assert support["central_slot"] is None

    def test_second_round_slots_are_offset(self):
        support = landing_slot_support(None, years_out=2, round_number=2)
        assert (support["min_slot"], support["max_slot"]) == (31, 60)

    def test_the_lottery_fall_is_bounded_by_the_number_of_drawn_picks(self):
        assert LOTTERY_MAX_FALL == 4


class TestPrecisionRefusals:
    BASE = {"draft_year": 2029, "round_number": 1, "original_team_win_pct": 0.600}

    def test_a_clean_verified_pick_gets_a_point_estimate(self):
        value = pick_value(
            PickTerms(**self.BASE, ownership_verified=True), current_year=2028
        )
        assert value.precision == "interval"
        assert value.point is not None
        assert value.low < value.point < value.high

    def test_an_unverified_pick_gets_no_point_estimate(self):
        value = pick_value(PickTerms(**self.BASE), current_year=2028)
        assert value.precision == "unknown"
        assert value.point is None
        assert "ownership is not verified" in value.caveats[0]

    def test_a_protected_pick_gets_no_point_estimate_and_a_zero_floor(self):
        value = pick_value(
            PickTerms(
                **self.BASE,
                ownership_verified=True,
                protections="protected for selections 1-4",
            ),
            current_year=2028,
        )
        assert value.precision == "range"
        assert value.point is None
        assert value.low == 0.0
        assert any("does not convey at all" in c for c in value.caveats)

    def test_an_unparseable_protection_is_conditional_not_unprotected(self):
        """The dangerous failure mode: text this cannot read being treated as no
        protection, which turns a conditional asset into a clean one."""
        value = pick_value(
            PickTerms(
                **self.BASE,
                ownership_verified=True,
                protections="conveys only if Denver has already conveyed to Oklahoma City",
            ),
            current_year=2028,
        )
        assert value.precision == "range"
        assert value.point is None
        assert any("could not be parsed" in c for c in value.caveats)

    def test_a_swap_gets_no_point_estimate(self):
        value = pick_value(
            PickTerms(**self.BASE, ownership_verified=True, is_conditional=True),
            current_year=2028,
        )
        assert value.precision == "range"
        assert value.point is None
        assert any("second team's finish" in c for c in value.caveats)

    def test_a_distant_pick_spans_almost_the_whole_round(self):
        value = pick_value(
            PickTerms(
                draft_year=2033, round_number=1, original_team_win_pct=0.600,
                ownership_verified=True,
            ),
            current_year=2028,
        )
        assert value.slot_support["min_slot"] == 1
        assert value.slot_support["max_slot"] >= 25
        assert any("no-information ceiling" in c for c in value.caveats)

    def test_the_interval_widens_as_the_pick_moves_further_out(self):
        widths = []
        for year in (2028, 2029, 2031, 2033):
            v = pick_value(
                PickTerms(
                    draft_year=year, round_number=1, original_team_win_pct=0.600,
                    ownership_verified=True,
                ),
                current_year=2028,
            )
            widths.append(v.high - v.low)
        assert all(b >= a for a, b in zip(widths, widths[1:], strict=False))
        assert widths[-1] > widths[0]


class TestProtectionParsing:
    @pytest.mark.parametrize(
        ("text", "expected"),
        [
            ("protected for selections 1-4", (1, 4)),
            ("protected for selections 31-55", (31, 55)),
            ("top-10 protected", (1, 10)),
            ("top 3 protected", (1, 3)),
            (None, None),
            ("", None),
            ("unprotected", None),
            ("conveys under conditions the source does not state", None),
        ],
    )
    def test_it_parses_only_what_it_can_read(self, text, expected):
        assert protection_range(text) == expected


class TestEstimationSet:
    def _frame(self):
        rows = []
        for season in ("2023-24", "2024-25", "2025-26"):
            for i in range(40):
                rows.append(
                    {
                        "player_id": f"p{i}",
                        "season": season,
                        "total_minutes": 1500.0 - 30.0 * i,
                    }
                )
        return pd.DataFrame(rows)

    def test_a_drafted_player_who_never_played_is_a_zero_not_a_gap(self):
        """The survivorship correction. Averaging only over players you can see is what
        makes a 55th pick look like a useful asset."""
        frame = self._frame()
        tei = pd.Series(np.full(len(frame), REPLACEMENT_TEI + 1.0))
        drafted = pd.DataFrame(
            [{"player_id": "p0", "draft_year": 2020, "draft_number": 1}]
            + [
                {"player_id": f"ghost{i}", "draft_year": 2020, "draft_number": i + 2}
                for i in range(29)
            ]
        )
        outcomes = build_draft_outcomes(frame, tei, drafted, classes=(2020,))
        assert len(outcomes) == 30, "the players who never played must still be rows"
        assert int(outcomes["observed"].sum()) == 1
        assert (outcomes[outcomes["player_id"] != "p0"]["value"] == 0.0).all()

    def test_value_is_floored_at_zero(self):
        frame = self._frame()
        tei = pd.Series(np.full(len(frame), REPLACEMENT_TEI - 5.0))
        drafted = pd.DataFrame(
            [{"player_id": f"p{i}", "draft_year": 2020, "draft_number": i + 1} for i in range(40)]
        )
        outcomes = build_draft_outcomes(frame, tei, drafted, classes=(2020,))
        assert (outcomes["value_raw"] < 0).all()
        assert (outcomes["value"] == 0.0).all()

    def test_within_class_normalisation_removes_the_class_effect(self):
        """Two classes with identical slot ordering but a 10x level difference must
        produce identical relative values — that is what makes the 2016 class (seen in
        years 7-9) comparable with the 2023 class (seen in years 0-2)."""
        rows, drafted = [], []
        for scale, year in ((1.0, 2020), (10.0, 2021)):
            for i in range(30):
                pid = f"{year}-{i}"
                rows.append(
                    {
                        "player_id": pid,
                        "season": "2024-25",
                        "total_minutes": scale * (1000.0 - 30.0 * i),
                    }
                )
                drafted.append(
                    {"player_id": pid, "draft_year": year, "draft_number": i + 1}
                )
        frame = pd.DataFrame(rows)
        tei = pd.Series(np.full(len(frame), REPLACEMENT_TEI + 1.0))
        outcomes = build_draft_outcomes(frame, tei, pd.DataFrame(drafted), classes=(2020, 2021))
        a = outcomes[outcomes["draft_year"] == 2020].set_index("slot")["rel"]
        b = outcomes[outcomes["draft_year"] == 2021].set_index("slot")["rel"]
        assert np.allclose(a.to_numpy(), b.to_numpy())


class TestFitDiagnostics:
    def _synthetic(self, noise: float, seed: int = 7) -> pd.DataFrame:
        rng = np.random.default_rng(seed)
        rows = []
        for year in DEFAULT_ESTIMATION_CLASSES:
            for slot in range(1, 61):
                true = 3.0 * np.exp(-0.09 * (slot - 1)) + 0.25
                rows.append(
                    {
                        "player_id": f"{year}-{slot}",
                        "draft_year": year,
                        "slot": slot,
                        "value": max(true + rng.normal(0, noise), 0.0),
                        "value_raw": true,
                        "observed": True,
                    }
                )
        frame = pd.DataFrame(rows)
        frame["rel"] = frame["value"] / frame.groupby("draft_year")["value"].transform("mean")
        return frame

    def test_a_real_gradient_is_recovered_and_validated_out_of_class(self):
        metrics = fit_pick_value_curve(self._synthetic(noise=0.5))
        assert metrics["calibrated"] is True
        assert metrics["leave_one_class_out"]["mean"] > 0.3
        assert metrics["leave_one_class_out"]["p"] < 0.01

    def test_pure_noise_does_not_validate(self):
        """The check the diagnostics exist for: a slot column carrying no signal must not
        produce a curve that ranks a held-out class."""
        rng = np.random.default_rng(11)
        rows = []
        for year in DEFAULT_ESTIMATION_CLASSES:
            for slot in range(1, 61):
                rows.append(
                    {
                        "player_id": f"{year}-{slot}",
                        "draft_year": year,
                        "slot": slot,
                        "value": abs(rng.normal(1.0, 1.0)),
                        "value_raw": 0.0,
                        "observed": True,
                    }
                )
        frame = pd.DataFrame(rows)
        frame["rel"] = frame["value"] / frame.groupby("draft_year")["value"].transform("mean")
        metrics = fit_pick_value_curve(frame)
        assert abs(metrics["leave_one_class_out"]["mean"]) < 0.2

    def test_the_round_only_baseline_is_always_reported(self):
        """The diagnostic that does NOT flatter the curve. On the real data the curve's
        advantage over a two-band rule is +0.0405 at p = 0.22, and the model version must
        carry that rather than only the figures that pass."""
        metrics = fit_pick_value_curve(self._synthetic(noise=0.5))
        assert "round_only_baseline" in metrics
        assert "curve_minus_round_only" in metrics
        assert "does not significantly beat" in metrics["not_established"]

    def test_an_empty_estimation_set_is_reported_not_defaulted(self):
        metrics = fit_pick_value_curve(pd.DataFrame())
        assert metrics["calibrated"] is False
        assert "reason" in metrics


class TestRankPersistence:
    def test_it_measures_drift_from_real_transitions(self):
        rng = np.random.default_rng(3)
        rows = []
        for season in ("2023-24", "2024-25", "2025-26"):
            for team in range(30):
                rows.append(
                    {
                        "team_id": f"t{team}",
                        "season": season,
                        "win_pct": 0.5 + 0.01 * team + rng.normal(0, 0.02),
                    }
                )
        result = fit_rank_persistence(pd.DataFrame(rows))
        assert result["calibrated"] is True
        assert result["n"] == 60
        assert 0.0 < result["sd"] < UNINFORMED_RANK_SD

    def test_one_season_cannot_be_differenced(self):
        rows = [{"team_id": f"t{i}", "season": "2025-26", "win_pct": 0.5} for i in range(30)]
        result = fit_rank_persistence(pd.DataFrame(rows))
        assert result["calibrated"] is False

    def test_the_unfitted_fallback_is_the_no_information_ceiling(self):
        """An unfitted drift is not a small drift. The fallback must not imply knowledge
        the pipeline does not have."""
        from app.analytics.picks import RANK_CHANGE_SD_ONE_YEAR

        assert pytest.approx(UNINFORMED_RANK_SD) == RANK_CHANGE_SD_ONE_YEAR
