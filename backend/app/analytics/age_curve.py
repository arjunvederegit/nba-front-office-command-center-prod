"""Conservative piecewise age curve (documented, not a precise long-range claim).

Expected year-over-year TEI drift by age, in TEI index points. The shape follows the
well-established empirical pattern (improvement through early 20s, plateau, gradual
decline from ~30) with deliberately modest magnitudes; docs/methodology.md states the
limitations."""


def age_delta(age: float) -> float:
    """Expected one-season TEI change for a player of this age."""
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


def project_tei(tei: float, age: float, years_ahead: int) -> float:
    """Apply the age curve cumulatively; uncertainty widens with horizon elsewhere."""
    projected = tei
    for year in range(years_ahead):
        projected += age_delta(age + year)
    return projected


def timeline_alignment(age: float, strategy: str) -> float:
    """0..1 score for how a player's age fits a strategic timeline."""
    contend_scores = [(25, 0.75), (29, 1.0), (33, 0.8), (99, 0.55)]
    rebuild_scores = [(22, 1.0), (25, 0.85), (28, 0.5), (99, 0.2)]
    retool_scores = [(24, 0.85), (28, 1.0), (31, 0.7), (99, 0.45)]
    table = {
        "contend": contend_scores,
        "improve": retool_scores,
        "retool": retool_scores,
        "rebuild": rebuild_scores,
        "youth": rebuild_scores,
        "cap_relief": retool_scores,
        "custom": retool_scores,
    }.get(strategy, retool_scores)
    for max_age, score in table:
        if age < max_age:
            return score
    return 0.5
