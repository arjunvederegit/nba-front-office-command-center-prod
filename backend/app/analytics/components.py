"""The scale contract every evaluation component obeys.

    Each component is reported on 0..100 with **50 = neutral** — the score a deal that
    changes nothing on that axis receives. The composite is a weighted mean of the
    components that could be measured, so the composite is on the same scale and means
    the same thing.

Two kinds of quantity feed that scale, and they are mapped differently on purpose.

**Naturally bounded quantities** map affinely and reach the endpoints. Availability is a
share of games in 0..1, so a package of players who never miss a game really is the top
of the availability scale, and 100 is the honest report.

**Unbounded quantities** — projected wins, cap-share surplus, fit deltas, asset counts —
have no maximum. They used to be truncated with ``max(0, min(100, x))``. Truncation is
not a scale choice, it is an *information* choice: every deal past the boundary receives
the same number, so the component stops ordering them at exactly the point where the
deals are most extreme. Measured on 800 evaluations of the post-R4 engine over the 30
ingested rosters:

    component     n     at 0   at 100   share tied at a boundary
    fit         440       58       48                    24.1 %
    contract    168        8        8                     9.5 %
    timeline    482       12        8                     4.1 %
    performance 482        2        0                     0.4 %

A quarter of all fit scores carried no ordering information. `bounded_score` replaces the
truncation with a strictly monotone squash that agrees with the affine map **to first
order at 50** and approaches 0 and 100 without reaching them.

    bounded_score(x) = 50 + 50 * tanh((x - 50) / 50)

    d/dx at x = 50 is exactly 1

No scale constant anywhere in the engine changes: every component keeps the slope it was
documented with, and only the saturating tail is different. A deal worth +15 projected
wins no longer scores identically to one worth +10.
"""

import math

NEUTRAL = 50.0
HALF_RANGE = 50.0

# Where `float64` `tanh` saturates to exactly +/-1, so the open-interval guarantee below
# becomes a closed one. 18 half-ranges: 1 - tanh(18) is about 5e-16, under one ulp of 1.0.
# Every component would have to be absurd to get here — 190 projected wins, a raw fit of
# -7.5 against a measured range of +/-0.42, 3.6 whole salary caps of surplus — and
# `test_component_scale.py` asserts exactly that against each component's real range.
SATURATION_MARGIN = 18.0 * HALF_RANGE


def bounded_score(linear_score: float) -> float:
    """Squash an unbounded 50-centred linear score into the open interval (0, 100).

    Strictly increasing, so ordering is preserved everywhere — which is the property
    truncation destroys. Agrees with the identity to first order at 50, so every
    component keeps the slope its documentation states.
    """
    return NEUTRAL + HALF_RANGE * math.tanh((linear_score - NEUTRAL) / HALF_RANGE)


def affine_score(value: float, lower: float, upper: float) -> float:
    """Map a value known to lie in [lower, upper] onto 0..100.

    For quantities that really are bounded — shares, probabilities, differences of two
    shares. The endpoints are attainable here because they mean something.
    """
    if upper <= lower:
        raise ValueError("upper must exceed lower")
    share = (value - lower) / (upper - lower)
    return 100.0 * min(max(share, 0.0), 1.0)
