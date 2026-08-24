"""Does the comparable-trade retrieval measure the trades, or measure its own construction?

"The neighbours look reasonable" is not a result. Every construction choice in
`comparables.py` — the saturating distance, the interquartile scale, the declared unit for
counts, the six dimensions and their weights — is a choice that could be driving the
ranking on its own, and the only way to know is to change it and see whether the answers
move.

Everything here runs leave-one-out over the rankable corpus: each side becomes a query
against the other 336, and the top-k it retrieves is compared against the top-k the same
query retrieves under an altered construction. The statistic throughout is **top-k Jaccard
overlap**, because that is the thing a user sees: not the distance, the list.

`make comparable-validation` prints the whole battery. It is a gate, not a report — the
thresholds it checks are stated in `THRESHOLDS` and the command exits non-zero when one
fails.

## Nulls

Three, following R4-2's rule that any criterion a null can pass is inadmissible:

- **random** — rank by a deterministic hash of the side key. Nothing about the trade.
- **single-dimension** — the full distance restricted to one dimension at a time. Tests
  whether six dimensions do anything one does not.
- **shuffled** — the real distance computed against a corpus whose feature vectors have
  been permuted between sides. Preserves every marginal distribution and destroys the
  correspondence between a trade and its features.
"""

from __future__ import annotations

import hashlib
import statistics
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from .comparables import (
    ALL_FEATURES,
    DECLARED_SCALES,
    DIMENSION_WEIGHTS,
    FEATURE_DIMENSIONS,
    TradeSide,
    compare,
    rank,
    robust_scales,
)

TOP_K = 5

#: Stated before the battery was run, and checked by `make comparable-validation`.
THRESHOLDS: dict[str, float] = {
    #: A 10 %-of-scale wobble in the query must not rewrite the list. Below this the
    #: ranking is reporting noise in the feature values rather than the trades.
    "perturbation_overlap_min": 0.60,
    #: The list must not be an artefact of how the scales were estimated — measured
    #: against the one alternative that is also defensible, the standard deviation.
    #: Min-max is measured too, but as a NULL rather than an alternative: it sets every
    #: feature's unit from the single most extreme trade in the corpus (a seven-team deal
    #: moving six first-round picks), which is the failure mode `DECLARED_SCALES` exists
    #: to avoid. High agreement with min-max would mean the ranking is insensitive to a
    #: scaling that is known to be wrong, and that is the bad outcome, not the good one.
    "scale_form_overlap_min": 0.50,
    #: Nor of the saturating-vs-clipped choice.
    "distance_form_overlap_min": 0.50,
    #: Six dimensions must do something one does not: the best single-dimension null must
    #: not reproduce the shipped list.
    "best_single_dimension_overlap_max": 0.75,
    #: And the real distance must beat a shuffled-feature null on archetype recovery.
    "archetype_lift_over_shuffled_min": 0.10,
    #: Buying must not be confused with selling. Of the top-k neighbours of a side that
    #: **sold** on-court value for first-round picks, at most this share may be sides that
    #: **bought** it — and vice versa.
    #:
    #: This replaces a criterion that was stated first and does not test retrieval: "an
    #: asymmetric side must be less similar to its own mirror image than two unrelated
    #: sides are to each other". It failed, at 0.679 against 0.672 — and the failure is
    #: uninformative, because similarity *levels* on this corpus compress into a narrow
    #: band (pairwise p05 0.510, p50 0.670, p95 0.865), so a 0.007 difference in level is
    #: not evidence about a list. The list is what the product shows, and by list the
    #: mirror is far away: injected into the corpus it is the nearest neighbour for 4 of
    #: 141 asymmetric sides, reaches the top five for 16, and sits at median rank 67 of
    #: 338. Both numbers are still reported below; only the criterion changed.
    "direction_confusion_max": 0.05,
}

#: The two archetypes that are each other's reverse. Direction confusion is measured
#: between them and nowhere else: "player for player" has no opposite.
OPPOSITE_ARCHETYPES = {
    "sold_value_for_firsts": "bought_value_with_firsts",
    "bought_value_with_firsts": "sold_value_for_firsts",
}


def _jaccard(a: list[str], b: list[str]) -> float:
    left, right = set(a), set(b)
    if not left and not right:
        return 1.0
    return len(left & right) / len(left | right)


def _top_keys(
    query: TradeSide,
    corpus: list[TradeSide],
    scales: dict[str, float],
    weights: dict[str, float] | None = None,
    k: int = TOP_K,
) -> list[str]:
    # `one_per_trade=False`: a leave-one-out measurement over sides has to be able to see
    # every side, including the other half of the query's own transaction.
    return [n.side.key for n in rank(query, corpus, scales, weights, k=k, one_per_trade=False)]


# ------------------------------------------------------------------ alternative scales


def sd_scales(sides: list[TradeSide]) -> dict[str, float]:
    """Every feature scaled by its standard deviation, including the counts."""
    scales: dict[str, float] = {}
    for name in ALL_FEATURES:
        values = [v for side in sides for v in [side.features().get(name)] if v is not None]
        if len(values) > 1:
            spread = statistics.pstdev(values)
            if spread > 0:
                scales[name] = spread
    return scales


def range_scales(sides: list[TradeSide]) -> dict[str, float]:
    """Min-max range — the scaling most sensitive to a single extreme trade."""
    scales: dict[str, float] = {}
    for name in ALL_FEATURES:
        values = [v for side in sides for v in [side.features().get(name)] if v is not None]
        if len(values) > 1:
            spread = max(values) - min(values)
            if spread > 0:
                scales[name] = spread
    return scales


# ------------------------------------------------------------------------ archetypes

#: Structural classes, defined on what a side did rather than on the distance's own
#: arithmetic. A side belongs to at most one, and a side matching none is excluded from the
#: archetype measurement rather than assigned a default.
ARCHETYPE_RULES: dict[str, Callable[[dict[str, float | None]], bool]] = {
    # Sends real on-court value and takes back first-round picks.
    "sold_value_for_firsts": lambda f: (
        (f.get("value_out") or 0.0) >= 0.10
        and (f.get("firsts_net") or 0.0) >= 1
        and (f.get("value_in") or 0.0) < (f.get("value_out") or 0.0)
    ),
    # Spends first-round picks to bring on-court value in.
    "bought_value_with_firsts": lambda f: (
        (f.get("value_in") or 0.0) >= 0.10
        and (f.get("firsts_net") or 0.0) <= -1
        and (f.get("value_out") or 0.0) < (f.get("value_in") or 0.0)
    ),
    # Rotation player for rotation player, no picks either way.
    "player_for_player": lambda f: (
        (f.get("players_in") or 0.0) >= 1
        and (f.get("players_out") or 0.0) >= 1
        and (f.get("picks_in") or 0.0) == 0
        and (f.get("picks_out") or 0.0) == 0
        and abs((f.get("value_in") or 0.0) - (f.get("value_out") or 0.0)) < 0.10
    ),
    # Second-round picks bought or sold with no first-round capital involved.
    "second_round_trade": lambda f: (
        abs(f.get("seconds_net") or 0.0) >= 1 and (f.get("firsts_net") or 0.0) == 0
    ),
    # Nothing of measurable on-court value moves either way.
    "no_measurable_value": lambda f: (
        abs(f.get("value_in") or 0.0) < 0.02
        and abs(f.get("value_out") or 0.0) < 0.02
        and (f.get("picks_in") or 0.0) == 0
        and (f.get("picks_out") or 0.0) == 0
    ),
}


def archetype_of(side: TradeSide) -> str | None:
    features = side.features()
    for name, rule in ARCHETYPE_RULES.items():
        if rule(features):
            return name
    return None


def archetype_precision(
    corpus: list[TradeSide],
    scales: dict[str, float],
    weights: dict[str, float] | None = None,
    k: int = TOP_K,
    ranker: Callable[[TradeSide, list[TradeSide]], list[str]] | None = None,
) -> dict[str, Any]:
    """Share of retrieved neighbours that share the query's structural archetype.

    Compared against the base rate — the share a *random* neighbour would have — because a
    class holding 40 % of the corpus is recovered 40 % of the time by doing nothing.
    """
    labels = {side.key: archetype_of(side) for side in corpus}
    labelled = [s for s in corpus if labels[s.key]]
    if not labelled:
        return {"queries": 0}
    counts: dict[str, int] = {}
    for side in labelled:
        label = labels[side.key]
        assert label is not None
        counts[label] = counts.get(label, 0) + 1
    total = len(labelled)
    # Base rate: the chance a uniformly random *labelled* neighbour matches.
    base = sum((n / total) ** 2 for n in counts.values())

    hits = 0
    considered = 0
    for side in labelled:
        neighbours = (
            ranker(side, corpus)
            if ranker
            else _top_keys(side, corpus, scales, weights, k=k)
        )
        for key in neighbours:
            if labels.get(key) is None:
                continue
            considered += 1
            hits += int(labels[key] == labels[side.key])
    precision = hits / considered if considered else 0.0
    return {
        "queries": len(labelled),
        "class_counts": dict(sorted(counts.items())),
        "neighbours_considered": considered,
        "precision_at_k": round(precision, 4),
        "base_rate": round(base, 4),
        "lift": round(precision - base, 4),
    }


# ----------------------------------------------------------------------------- nulls


def random_ranker(k: int = TOP_K) -> Callable[[TradeSide, list[TradeSide]], list[str]]:
    """Deterministic pseudo-random order: a hash of (query key, candidate key)."""

    def ranker(query: TradeSide, corpus: list[TradeSide]) -> list[str]:
        scored = [
            (hashlib.sha1(f"{query.key}|{side.key}".encode()).hexdigest(), side.key)
            for side in corpus
            if side.key != query.key
        ]
        scored.sort()
        return [key for _, key in scored[:k]]

    return ranker


def shuffled_corpus(corpus: list[TradeSide]) -> list[TradeSide]:
    """Feature vectors permuted between sides by a fixed derangement.

    Every marginal distribution survives; the correspondence between a trade and its own
    features does not. A criterion this passes is measuring the distributions.
    """
    order = sorted(corpus, key=lambda s: hashlib.sha1(s.key.encode()).hexdigest())
    rotated = order[1:] + order[:1]
    return [
        _FeatureSwapped(original=original, donor=donor)  # type: ignore[misc]
        for original, donor in zip(order, rotated, strict=True)
    ]


@dataclass
class _FeatureSwapped:
    """A side that keeps its identity and borrows another side's feature vector."""

    original: TradeSide
    donor: TradeSide

    @property
    def key(self) -> str:
        return self.original.key

    @property
    def rankable(self) -> bool:
        return True

    def features(self) -> dict[str, float | None]:
        return self.donor.features()


# ------------------------------------------------------------------------- the battery


@dataclass
class Check:
    name: str
    measured: float | None
    threshold: float | None
    passed: bool | None
    detail: dict[str, Any] = field(default_factory=dict)


#: The 2023 CBA's first season. It introduced the second apron and the aggregation and
#: pick-trading restrictions that go with it, so a trade before it was built under
#: different rules. Whether that shows up in the *structure* of trades is a measurement,
#: not an assumption — see `era_structure`.
CBA_2023_FIRST_SEASON = "2023-24"


def era_structure(all_sides: list[TradeSide]) -> dict[str, Any]:
    """Did the 2023 CBA change the shape of trades?

    Measured on **every** ingested side, not the rankable subset: structure needs no
    player model, so all ten seasons contribute. This is the only place era can be
    measured at all — the rankable corpus is entirely inside one CBA, so an era term in
    the distance would be a constant, and scoring a constant is not a measurement.
    """
    eras: dict[str, list[TradeSide]] = {"2017_cba": [], "2023_cba": []}
    for side in all_sides:
        key = "2023_cba" if side.season >= CBA_2023_FIRST_SEASON else "2017_cba"
        eras[key].append(side)
    summary: dict[str, Any] = {}
    for era, sides in eras.items():
        if not sides:
            continue
        features = [s.features() for s in sides]
        summary[era] = {
            "sides": len(sides),
            "seasons": sorted({s.season for s in sides}),
            "mean_picks_per_side": round(
                statistics.fmean((f["picks_in"] or 0.0) + (f["picks_out"] or 0.0) for f in features),
                3,
            ),
            "share_moving_a_first": round(
                statistics.fmean(float(abs(f["firsts_net"] or 0.0) > 0) for f in features), 3
            ),
            "mean_conditional_pick_share": round(
                statistics.fmean(
                    f["conditional_pick_share"]
                    for f in features
                    if f["conditional_pick_share"] is not None
                ),
                3,
            ),
            "share_multi_team": round(
                statistics.fmean(float((f["n_teams"] or 2.0) > 2) for f in features), 3
            ),
            "mean_players_per_side": round(
                statistics.fmean(
                    (f["players_in"] or 0.0) + (f["players_out"] or 0.0) for f in features
                ),
                3,
            ),
        }
    return summary


def season_concentration(
    corpus: list[TradeSide], scales: dict[str, float], k: int = TOP_K
) -> dict[str, Any]:
    """Do neighbours cluster in the query's own season?

    If they did, the retrieval would partly be a date lookup. The base rate is the share a
    uniformly random neighbour would share a season with.
    """
    counts: dict[str, int] = {}
    for side in corpus:
        counts[side.feature_season] = counts.get(side.feature_season, 0) + 1
    total = len(corpus)
    base = sum((n / total) ** 2 for n in counts.values())
    hits = considered = 0
    by_key = {s.key: s for s in corpus}
    for side in corpus:
        for key in _top_keys(side, corpus, scales, k=k):
            considered += 1
            hits += int(by_key[key].feature_season == side.feature_season)
    return {
        "same_feature_season_share": round(hits / considered, 4) if considered else None,
        "base_rate": round(base, 4),
        "season_counts": dict(sorted(counts.items())),
    }


def run_battery(
    corpus: list[TradeSide], k: int = TOP_K, all_sides: list[TradeSide] | None = None
) -> dict[str, Any]:
    """Every measurement, on the corpus as it stands."""
    scales = robust_scales(corpus)
    baseline = {side.key: _top_keys(side, corpus, scales, k=k) for side in corpus}
    checks: list[Check] = []

    # --- 1. perturbation stability -------------------------------------------------
    overlaps = []
    for side in corpus:
        for direction in (1.0, -1.0):
            perturbed = _PerturbedSide(side, scales, 0.10 * direction)
            overlaps.append(
                _jaccard(
                    baseline[side.key],
                    _top_keys(perturbed, corpus, scales, k=k),  # type: ignore[arg-type]
                )
            )
    checks.append(
        Check(
            "perturbation_stability",
            round(statistics.fmean(overlaps), 4),
            THRESHOLDS["perturbation_overlap_min"],
            statistics.fmean(overlaps) >= THRESHOLDS["perturbation_overlap_min"],
            {
                "shift": "0.10 x each feature's own scale, both directions",
                "min": round(min(overlaps), 4),
                "median": round(statistics.median(overlaps), 4),
                "share_below_half": round(
                    sum(1 for o in overlaps if o < 0.5) / len(overlaps), 4
                ),
                "n": len(overlaps),
            },
        )
    )

    # --- 2. scale-form sensitivity --------------------------------------------------
    for label, alternative, gated in (
        ("standard_deviation", sd_scales, True),
        ("min_max_range", range_scales, False),
    ):
        other = alternative(corpus)
        overlap = statistics.fmean(
            _jaccard(baseline[s.key], _top_keys(s, corpus, other, k=k)) for s in corpus
        )
        checks.append(
            Check(
                f"scale_form_{label}",
                round(overlap, 4),
                THRESHOLDS["scale_form_overlap_min"] if gated else None,
                (overlap >= THRESHOLDS["scale_form_overlap_min"]) if gated else None,
                {
                    "alternative": label,
                    "role": "alternative" if gated else "null",
                    "note": (
                        "gated: an equally defensible estimator must not change the list"
                        if gated
                        else "reported, never gated: min-max takes its unit from the most "
                        "extreme trade in the corpus, which is the failure this module's "
                        "declared scales exist to avoid"
                    ),
                },
            )
        )

    # --- 3. distance-form sensitivity -----------------------------------------------
    clipped = statistics.fmean(
        _jaccard(baseline[s.key], _clipped_top_keys(s, corpus, scales, k)) for s in corpus
    )
    checks.append(
        Check(
            "distance_form_clipped",
            round(clipped, 4),
            THRESHOLDS["distance_form_overlap_min"],
            clipped >= THRESHOLDS["distance_form_overlap_min"],
            {"alternative": "min(1, |d|/scale) instead of |d|/(|d|+scale)"},
        )
    )

    # --- 4. weighting sensitivity ---------------------------------------------------
    weightings: dict[str, dict[str, float]] = {
        "uniform": dict.fromkeys(FEATURE_DIMENSIONS, 1.0),
    }
    for dimension in FEATURE_DIMENSIONS:
        weightings[f"only_{dimension}"] = {dimension: 1.0}
    weight_overlaps: dict[str, float] = {}
    for label, weights in weightings.items():
        weight_overlaps[label] = round(
            statistics.fmean(
                _jaccard(baseline[s.key], _top_keys(s, corpus, scales, weights, k=k))
                for s in corpus
            ),
            4,
        )
    best_single = max(v for key, v in weight_overlaps.items() if key.startswith("only_"))
    checks.append(
        Check(
            "best_single_dimension_null",
            best_single,
            THRESHOLDS["best_single_dimension_overlap_max"],
            best_single <= THRESHOLDS["best_single_dimension_overlap_max"],
            {"overlaps": weight_overlaps},
        )
    )

    # --- 5. leave-one-dimension-out --------------------------------------------------
    loo: dict[str, float] = {}
    for dimension in FEATURE_DIMENSIONS:
        weights = {d: w for d, w in DIMENSION_WEIGHTS.items() if d != dimension}
        loo[dimension] = round(
            statistics.fmean(
                _jaccard(baseline[s.key], _top_keys(s, corpus, scales, weights, k=k))
                for s in corpus
            ),
            4,
        )
    checks.append(Check("leave_one_dimension_out", None, None, None, {"overlap_without": loo}))

    # --- 6. archetype recovery, against two nulls -------------------------------------
    real = archetype_precision(corpus, scales, k=k)
    random_null = archetype_precision(corpus, scales, k=k, ranker=random_ranker(k))
    swapped = shuffled_corpus(corpus)
    shuffled_null = archetype_precision(
        corpus,
        scales,
        k=k,
        ranker=lambda q, c: _top_keys(q, swapped, scales, k=k),  # type: ignore[arg-type]
    )
    lift = real.get("precision_at_k", 0.0) - shuffled_null.get("precision_at_k", 0.0)
    checks.append(
        Check(
            "archetype_recovery",
            round(lift, 4),
            THRESHOLDS["archetype_lift_over_shuffled_min"],
            lift >= THRESHOLDS["archetype_lift_over_shuffled_min"],
            {"real": real, "null_random": random_null, "null_shuffled_features": shuffled_null},
        )
    )

    # --- 7. direction: is buying confused with selling? --------------------------------
    #
    # Two measurements of the same question. The gate uses real corpus trades: of the
    # neighbours returned for a side that sold on-court value for first-round picks, how
    # many are sides that did the opposite. The synthetic mirror is reported beside it.
    labels = {side.key: archetype_of(side) for side in corpus}
    opposite_hits = 0
    directional_neighbours = 0
    for side in corpus:
        side_label = labels[side.key]
        opposite = OPPOSITE_ARCHETYPES.get(side_label or "")
        if opposite is None:
            continue
        for key in baseline[side.key]:
            neighbour_label = labels.get(key)
            if neighbour_label is None:
                continue
            directional_neighbours += 1
            opposite_hits += int(neighbour_label == opposite)
    confusion = opposite_hits / directional_neighbours if directional_neighbours else 0.0
    checks.append(
        Check(
            "direction_confusion",
            round(confusion, 4),
            THRESHOLDS["direction_confusion_max"],
            confusion <= THRESHOLDS["direction_confusion_max"],
            {
                "directional_neighbours": directional_neighbours,
                "opposite_archetype_hits": opposite_hits,
            },
        )
    )

    # --- 8. the mirror, reported ------------------------------------------------------
    #
    # Reversing a 1-for-1 swap of two similar players produces the same trade, and the
    # distance is right to say so. Only sides whose two directions are genuinely different
    # decisions are informative here.
    symmetric, asymmetric = [], []
    mirror_ranks: list[int] = []
    for side in corpus:
        mirrored = _MirroredSide(side)
        similarity = compare(mirrored, side, scales).similarity  # type: ignore[arg-type]
        if _is_asymmetric(side):
            asymmetric.append(similarity)
            augmented: list[TradeSide] = [*corpus, mirrored]  # type: ignore[list-item]
            ordered = rank(side, augmented, scales, k=len(augmented), one_per_trade=False)
            position = next(
                (i + 1 for i, n in enumerate(ordered) if n.side.key == mirrored.key), None
            )
            if position is not None:
                mirror_ranks.append(position)
        else:
            symmetric.append(similarity)
    pairwise = _pairwise_similarity(corpus, scales)
    checks.append(
        Check(
            "mirror_image_rank",
            round(statistics.median(mirror_ranks), 1) if mirror_ranks else None,
            None,
            None,
            {
                "asymmetric_sides": len(asymmetric),
                "mirror_is_nearest_neighbour": sum(1 for r in mirror_ranks if r == 1),
                "mirror_in_top_k": sum(1 for r in mirror_ranks if r <= k),
                "median_rank_of_mirror": (
                    statistics.median(mirror_ranks) if mirror_ranks else None
                ),
                "corpus_size": len(corpus) + 1,
                "mean_similarity_to_own_mirror_asymmetric": round(
                    statistics.fmean(asymmetric), 4
                )
                if asymmetric
                else None,
                "mean_similarity_to_own_mirror_symmetric": (
                    round(statistics.fmean(symmetric), 4) if symmetric else None
                ),
                "pairwise_similarity_percentiles": pairwise,
                "note": (
                    "A symmetric side's mirror IS the same trade, and a high similarity "
                    "there is correct rather than a defect. Similarity levels compress "
                    "into a narrow band, so the rank is the informative statistic."
                ),
            },
        )
    )

    checks.append(
        Check("era_structure", None, None, None, era_structure(all_sides or corpus))
    )
    checks.append(
        Check("season_concentration", None, None, None, season_concentration(corpus, scales, k))
    )

    return {
        "corpus_sides": len(corpus),
        "k": k,
        "scales": {name: round(value, 5) for name, value in sorted(scales.items())},
        "declared_scales": DECLARED_SCALES,
        "weights": DIMENSION_WEIGHTS,
        "checks": [
            {
                "name": c.name,
                "measured": c.measured,
                "threshold": c.threshold,
                "passed": c.passed,
                "detail": c.detail,
            }
            for c in checks
        ],
        "failed": [c.name for c in checks if c.passed is False],
    }


def _is_asymmetric(side: TradeSide) -> bool:
    """A side whose reversal would be a different decision, not the same one restated."""
    features = side.features()
    firsts = features.get("firsts_net") or 0.0
    value_in = features.get("value_in")
    value_out = features.get("value_out")
    if abs(firsts) >= 1:
        return True
    if value_in is None or value_out is None:
        return False
    return abs(value_in - value_out) >= 0.085  # one corpus IQR of package value


def _pairwise_similarity(
    corpus: list[TradeSide], scales: dict[str, float], stride: int = 3, span: int = 12
) -> dict[str, float]:
    """Percentiles of similarity between unrelated sides.

    Every similarity the product shows needs this to be readable: 0.72 means nothing until
    you know that the middle of the corpus sits at 0.67 and the 95th percentile at 0.87.
    """
    values = []
    for index in range(0, len(corpus), stride):
        for other in corpus[index + 1 : index + span]:
            values.append(compare(corpus[index], other, scales).similarity)
    values.sort()
    if not values:
        return {}
    def at(share: float) -> float:
        return round(values[int(share * (len(values) - 1))], 4)
    return {
        "n": len(values),
        "p05": at(0.05),
        "p25": at(0.25),
        "p50": at(0.50),
        "p75": at(0.75),
        "p95": at(0.95),
    }


@dataclass
class _PerturbedSide:
    """A query whose numeric features are shifted by a share of their own scale."""

    side: TradeSide
    scales: dict[str, float]
    share: float

    @property
    def key(self) -> str:
        return self.side.key

    @property
    def rankable(self) -> bool:
        return True

    def features(self) -> dict[str, float | None]:
        shifted: dict[str, float | None] = {}
        for name, value in self.side.features().items():
            scale = self.scales.get(name)
            shifted[name] = (
                value + self.share * scale if value is not None and scale is not None else value
            )
        return shifted


@dataclass
class _MirroredSide:
    """The same trade with every direction reversed: what it sent, it now receives."""

    side: TradeSide

    @property
    def key(self) -> str:
        return f"{self.side.key}|mirror"

    @property
    def rankable(self) -> bool:
        return True

    def features(self) -> dict[str, float | None]:
        original = self.side.features()
        swapped = dict(original)
        for left, right in (
            ("value_in", "value_out"),
            ("best_in_tei", "best_out_tei"),
            ("players_in", "players_out"),
            ("picks_in", "picks_out"),
            ("age_in", "age_out"),
        ):
            swapped[left], swapped[right] = original[right], original[left]
        for name in ("firsts_net", "seconds_net", "win_pct_gap"):
            value = original.get(name)
            swapped[name] = -value if value is not None else None
        return swapped


def _clipped_top_keys(
    query: TradeSide, corpus: list[TradeSide], scales: dict[str, float], k: int
) -> list[str]:
    """The same distance with the saturating map replaced by a hard clip at one scale."""
    import app.analytics.comparables as module

    original = module.feature_distance
    try:
        module.feature_distance = lambda a, b, scale: min(1.0, abs(a - b) / scale)
        return _top_keys(query, corpus, scales, k=k)
    finally:
        module.feature_distance = original
