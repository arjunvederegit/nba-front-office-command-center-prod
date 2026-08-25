"""Conservative age curve (documented, not a precise long-range claim).

Expected year-over-year TEI drift by age, in TEI index points. The shape follows the
well-established empirical pattern (improvement through early 20s, plateau, gradual
decline from ~30) with deliberately modest magnitudes; docs/methodology.md states the
limitations.

**Both curves here are continuous (R4-4).** They were step functions over hard age
boundaries, so a player crossing a boundary on a birthday moved by more than the model's
own precision:

- `age_delta` stepped -0.35 TEI/yr at age 30, so a four-year projection differed by
  **0.70 TEI** between ages 29.99 and 30.01 — 0.59 standard deviations of the whole TEI
  distribution, produced by two days of age.
- `timeline_alignment` stepped as much as 0.35, and the 0..1 alignment becomes a 0..100
  component in `evaluation.py`, so one year of age could move a scored component by
  **35 points of 100**. It also collapsed to exactly 50.0 for a quarter to two fifths of
  one-for-one trades between real roster ages, because only four distinct values were
  ever reachable per strategy.

Neither replacement asserts anything new about magnitude. Each is the **linear
interpolant of the previous piecewise-constant curve through that curve's own bucket
midpoints**, so the trapezoid rule makes it exactly area-preserving over every interior
segment: `age_delta`'s total drift over ages 18-42 is -4.651 against the old -4.660, and
the worst running-cumulative discrepancy anywhere is 0.126 TEI. The steps are removed;
the claim is unchanged.
"""

# Midpoints of the previous buckets, each carrying that bucket's value.
AGE_KNOTS: tuple[tuple[float, float], ...] = (
    (19.5, 0.80),
    (22.5, 0.50),
    (25.5, 0.20),
    (28.5, 0.00),
    (31.5, -0.35),
    (34.5, -0.70),
    (37.5, -1.00),
)


def _interpolate(knots: tuple[tuple[float, float], ...], age: float) -> float:
    """Piecewise-linear through `knots`, flat outside the outermost pair.

    The flat tails are deliberate: they are the previous curve's open-ended first and
    last buckets, and extrapolating a slope past them would be a new claim about ages
    the curve was never fitted on.
    """
    if age <= knots[0][0]:
        return knots[0][1]
    if age >= knots[-1][0]:
        return knots[-1][1]
    for (a0, v0), (a1, v1) in zip(knots, knots[1:], strict=False):
        if age <= a1:
            return v0 + (v1 - v0) * (age - a0) / (a1 - a0)
    return knots[-1][1]


def age_delta(age: float) -> float:
    """Expected one-season TEI change for a player of this age."""
    return _interpolate(AGE_KNOTS, age)


def project_tei(tei: float, age: float, years_ahead: int) -> float:
    """Apply the age curve cumulatively; uncertainty widens with horizon elsewhere.

    The `age + year` sampling is kept rather than moved to mid-season `age + year + 0.5`:
    measured against the step curve it is the closer of the two (max deviation 0.408 TEI
    at a five-year horizon against 0.554), so changing it would introduce drift for no
    stated reason.
    """
    projected = tei
    for year in range(years_ahead):
        projected += age_delta(age + year)
    return projected


# Same construction: midpoints of the previous (max_age, score) buckets.
_ALIGNMENT_KNOTS: dict[str, tuple[tuple[float, float], ...]] = {
    "contend": ((23.0, 0.75), (27.0, 1.00), (31.0, 0.80), (35.0, 0.55)),
    "retool": ((22.0, 0.85), (26.0, 1.00), (29.5, 0.70), (32.5, 0.45)),
    "rebuild": ((20.5, 1.00), (23.5, 0.85), (26.5, 0.50), (29.5, 0.20)),
}

# `custom` is the DEFAULT everywhere — `schemas.py` declares it on ScenarioIn,
# EvaluateRequest and GenerateRequest, and `trades.py`, `evaluation.py` and
# `candidates.py` all fall back to it — and it resolves to the RETOOL shape. That
# mapping used to be buried in a dict literal, and it is why the audit's Tatum/Doncic
# example actually scores 20.0: the 50.0 the audit reported reproduces only under
# `contend`.
_STRATEGY_TO_KNOTS = {
    "contend": "contend",
    "improve": "retool",
    "retool": "retool",
    "rebuild": "rebuild",
    "youth": "rebuild",
    "cap_relief": "retool",
    "custom": "retool",
}


def timeline_alignment(age: float, strategy: str) -> float:
    """0..1 score for how a player's age fits a strategic timeline.

    An unknown strategy resolves to the retool shape, matching the previous
    `.get(strategy, retool_scores)` behaviour.
    """
    return _interpolate(_ALIGNMENT_KNOTS[_STRATEGY_TO_KNOTS.get(strategy, "retool")], age)
