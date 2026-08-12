"""R5-1a. The component scale contract.

Every component reports on 0..100 with 50 neutral. Components built from an unbounded
quantity go through `bounded_score`, which is strictly monotone — so no two deals ever
receive the same component score merely because both ran past a truncation boundary.

The measurement that motivated this, on 800 evaluations of the post-R4 engine over the
30 ingested rosters: 24.1 % of fit scores, 9.5 % of contract scores and 4.1 % of timeline
scores sat exactly on 0 or 100 and therefore carried no ordering information.
"""

import math

import pytest

from app.analytics.components import (
    NEUTRAL,
    SATURATION_MARGIN,
    affine_score,
    bounded_score,
)


class TestBoundedScore:
    def test_neutral_is_fixed(self):
        assert bounded_score(50.0) == pytest.approx(50.0)

    def test_first_order_agreement_with_the_affine_map_at_neutral(self):
        """The squash must not silently rescale any component.

        Every component's slope constant — 5 points per projected win, x120 on raw fit,
        x250 on cap-share surplus, 8 per pick — is documented and unchanged by R5. That
        is only true if the transform has unit derivative at 50.
        """
        h = 1e-6
        slope = (bounded_score(50.0 + h) - bounded_score(50.0 - h)) / (2 * h)
        assert slope == pytest.approx(1.0, abs=1e-6)

    def test_it_agrees_with_truncation_to_within_a_point_in_the_bulk(self):
        for linear in (46.0, 48.0, 50.0, 52.0, 55.0, 58.0):
            assert bounded_score(linear) == pytest.approx(linear, abs=1.0)

    def test_it_is_strictly_increasing_everywhere(self):
        xs = [-1000.0, -200.0, -50.0, 0.0, 25.0, 50.0, 75.0, 100.0, 150.0, 400.0, 5000.0]
        scores = [bounded_score(x) for x in xs]
        assert all(b > a for a, b in zip(scores, scores[1:], strict=False))

    def test_it_never_reaches_either_endpoint_on_any_reachable_input(self):
        """The defect truncation created: ties at the boundary.

        Two deals that differ by 5 projected wins used to score 100 and 100.

        The open-interval guarantee is a real-arithmetic one; `float64` `tanh` saturates
        to exactly ±1 beyond about 19 units, i.e. |linear - 50| > 900. That bound is
        asserted separately against what the components can actually produce, so the
        claim here is about inputs the engine can reach — not a promise the arithmetic
        cannot keep.
        """
        for linear in (-850.0, -400.0, -100.0, 0.0, 100.0, 400.0, 850.0):
            assert 0.0 < bounded_score(linear) < 100.0

    def test_the_saturation_bound_is_far_outside_every_component_range(self):
        """No component expression can reach the point where float64 tanh saturates.

        SATURATION_MARGIN is 900 linear points from neutral. Reaching it needs:
          performance   190 projected wins
          fit           a raw fit of -7.5, against a measured range of +/-0.42
          contract      a net cap-share surplus of 3.6, i.e. 3.6x the entire salary cap
          assets        112 net first-round picks, or $4.5bn of payroll
        """
        assert pytest.approx(900.0, rel=0.02) == SATURATION_MARGIN
        assert bounded_score(NEUTRAL + SATURATION_MARGIN * 0.95) < 100.0
        assert bounded_score(NEUTRAL - SATURATION_MARGIN * 0.95) > 0.0
        # The most extreme raw fit the 30 ingested rosters produced was 0.4158.
        assert abs(50.0 + 0.42 * 120.0 - NEUTRAL) < SATURATION_MARGIN
        # 82 projected wins is the whole season.
        assert abs(50.0 + 82 * 5.0 - NEUTRAL) < SATURATION_MARGIN

    def test_extreme_deals_still_separate(self):
        ten_wins = bounded_score(50.0 + 10 * 5.0)
        fifteen_wins = bounded_score(50.0 + 15 * 5.0)
        assert fifteen_wins > ten_wins
        # ...and by a visible margin, not by floating-point dust.
        assert fifteen_wins - ten_wins > 0.5

    def test_it_is_odd_about_neutral(self):
        for delta in (1.0, 12.5, 60.0, 500.0):
            above = bounded_score(NEUTRAL + delta) - NEUTRAL
            below = NEUTRAL - bounded_score(NEUTRAL - delta)
            assert above == pytest.approx(below)

    def test_it_is_finite_for_non_finite_input_magnitudes(self):
        assert bounded_score(float("inf")) == pytest.approx(100.0)
        assert bounded_score(float("-inf")) == pytest.approx(0.0)
        assert math.isnan(bounded_score(float("nan")))


class TestAffineScore:
    def test_a_bounded_quantity_reaches_both_endpoints(self):
        """Availability really does have a maximum, and 100 is the honest report."""
        assert affine_score(1.0, -1.0, 1.0) == pytest.approx(100.0)
        assert affine_score(-1.0, -1.0, 1.0) == pytest.approx(0.0)
        assert affine_score(0.0, -1.0, 1.0) == pytest.approx(50.0)

    def test_out_of_range_values_are_clamped_not_extrapolated(self):
        assert affine_score(2.0, -1.0, 1.0) == pytest.approx(100.0)
        assert affine_score(-2.0, -1.0, 1.0) == pytest.approx(0.0)

    def test_a_degenerate_range_is_a_programming_error(self):
        with pytest.raises(ValueError):
            affine_score(0.0, 1.0, 1.0)
