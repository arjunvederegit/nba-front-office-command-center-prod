"""Weight-sensitivity analysis: is the recommendation robust, or an artifact of one
particular weighting? Samples weight vectors around the user's choice (Dirichlet) and
recomputes rankings; also produces one-at-a-time tornado deltas."""

import numpy as np

from .features import RANDOM_SEED

N_SAMPLES = 500
CONCENTRATION = 50.0  # higher = samples closer to the user's weights


def normalize_weights(weights: dict[str, float]) -> dict[str, float]:
    """Scale non-negative weights to sum to 1.

    When every weight is zero the result is **all zeros**, not a uniform distribution.
    Zeroing every slider is a deliberate statement by the user; substituting a uniform
    prior silently re-enabled the components they had switched off and produced a score
    they never asked for.
    """
    total = sum(max(w, 0.0) for w in weights.values())
    if total <= 0:
        return dict.fromkeys(weights, 0.0)
    return {k: max(w, 0.0) / total for k, w in weights.items()}


def component_contributions(
    components: dict[str, float | None], weights: dict[str, float]
) -> list[dict]:
    """Per-component contribution to `composite_utility - 50`, in composite points.

    Uses the **renormalized** weights, so the contributions always reconcile with the
    composite. Deriving them from the raw weights instead made the two disagree whenever
    a component was excluded (measured: utility − 50 = 7.06 against summed drivers 4.94).
    """
    available = {k: v for k, v in components.items() if v is not None}
    if not available:
        return []
    active = normalize_weights({k: weights.get(k, 0.0) for k in available})
    rows: list[tuple[float, dict]] = [
        (
            abs((value - 50.0) * active[key]),
            {
                "component": key,
                "score": round(value, 1),
                "weight": round(active[key], 4),
                "contribution": round((value - 50.0) * active[key], 2),
            },
        )
        for key, value in available.items()
    ]
    rows.sort(key=lambda pair: pair[0], reverse=True)
    return [row for _, row in rows]


def composite_utility(
    components: dict[str, float | None], weights: dict[str, float]
) -> float | None:
    """Components on 0..100; weights normalized. Missing components are excluded and
    remaining weights renormalized — absent data shrinks scope, it never fakes a score.

    Returns **None**, not 0.0, when nothing can be scored. On a 0..100 scale a zero reads
    as a catastrophic verdict, which is the opposite of "we cannot say"."""
    available = {k: v for k, v in components.items() if v is not None}
    if not available:
        return None
    active = normalize_weights({k: weights.get(k, 0.0) for k in available})
    if sum(active.values()) <= 0:
        return None  # every scorable component was weighted to zero
    return sum(available[k] * active[k] for k in available)


def rank_stability(
    alternatives: dict[str, dict[str, float | None]],
    weights: dict[str, float],
    n_samples: int = N_SAMPLES,
    seed: int = RANDOM_SEED,
) -> dict:
    """alternatives: {trade_id: components}. Returns share of sampled weight vectors
    in which each alternative ranks first, plus rank volatility."""
    if not alternatives:
        return {"first_place_share": {}, "rank_volatility": {}}
    rng = np.random.default_rng(seed)
    weights = normalize_weights(weights)
    keys = sorted({k for comps in alternatives.values() for k in comps})
    alpha = np.array([max(weights.get(k, 0.01), 0.01) * CONCENTRATION for k in keys])

    ids = list(alternatives.keys())
    first_counts = dict.fromkeys(ids, 0)
    rank_history: dict[str, list[int]] = {i: [] for i in ids}

    for _ in range(n_samples):
        sample = rng.dirichlet(alpha)
        sampled_weights = dict(zip(keys, sample, strict=False))
        # An alternative that cannot be scored at all is ranked last rather than
        # dropped, so its presence is visible in the volatility figures instead of
        # quietly shrinking the comparison.
        utilities = {
            trade_id: (
                value if (value := composite_utility(components, sampled_weights)) is not None
                else float("-inf")
            )
            for trade_id, components in alternatives.items()
        }
        ranked = sorted(ids, key=lambda i: utilities[i], reverse=True)
        first_counts[ranked[0]] += 1
        for position, trade_id in enumerate(ranked, start=1):
            rank_history[trade_id].append(position)

    return {
        "n_samples": n_samples,
        "first_place_share": {i: round(c / n_samples, 3) for i, c in first_counts.items()},
        "rank_volatility": {i: round(float(np.std(ranks)), 3) for i, ranks in rank_history.items()},
        "median_rank": {i: float(np.median(ranks)) for i, ranks in rank_history.items()},
    }


def tornado(
    components: dict[str, float | None], weights: dict[str, float], swing: float = 0.5
) -> list[dict]:
    """One-at-a-time weight perturbation (+/- swing fraction) → utility deltas,
    sorted by magnitude for a tornado chart."""
    weights = normalize_weights(weights)
    base = composite_utility(components, weights)
    if base is None:
        return []  # nothing to perturb: there is no score to be sensitive about
    bars: list[dict] = []
    for key in weights:
        if components.get(key) is None:
            continue
        up = dict(weights)
        up[key] = weights[key] * (1 + swing)
        down = dict(weights)
        down[key] = weights[key] * (1 - swing)
        low = composite_utility(components, normalize_weights(down))
        high = composite_utility(components, normalize_weights(up))
        if low is None or high is None:
            continue
        bars.append(
            {
                "component": key,
                "utility_low": round(low, 2),
                "utility_high": round(high, 2),
                "base": round(base, 2),
            }
        )
    bars.sort(key=lambda b: abs(float(b["utility_high"]) - float(b["utility_low"])), reverse=True)
    return bars
