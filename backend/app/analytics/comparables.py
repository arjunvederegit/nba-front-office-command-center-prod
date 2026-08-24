"""Retrieving the completed trades most like a proposed one.

## The unit of retrieval is a SIDE, not a trade

"Boston traded Marcus Smart for Kristaps Porziņģis" and "Washington traded Kristaps
Porziņģis for Marcus Smart" are the same transaction and two different decisions. A front
office asks "what happened to teams that did what I am about to do", so the retrieval unit
is one team's view of one trade — what it sent, what it received, where it stood — and a
three-team trade contributes three of them.

## The distance

An interpretable, grouped distance. Fifteen features in six dimensions; each dimension's
distance is the mean over the features **both sides state**, and the total is the
weighted mean over the dimensions that survive:

    d(a, b) = SUM_g w_g * d_g(a, b) / SUM_g w_g          over dimensions g with data
    d_g     = mean over features f in g of |a_f - b_f| / (|a_f - b_f| + scale_f)

Three properties of that form are deliberate.

**Nothing is truncated.** `|Δ| / (|Δ| + s)` is bounded in [0, 1), monotone in |Δ| and
scale-free, so two very different trades stay ordered rather than both landing on a
ceiling. This is R5-1a's finding applied again: clipping at one scale unit put 41 % of
corpus pairs on the cap in this dimension set, and the ordering above that cap is the
ordering a user is asking about.

**`scale_f` is the corpus's own interquartile range**, not the query's and not a standard
deviation. Half these features are counts with hard floors at zero and long right tails —
`firsts_out` is 0 for 71 % of sides and 4 for one of them — and an sd-based scale is set
by the tail rather than by the body.

**A feature only enters when both sides state it.** A side that receives no players has no
`best_in_tei`; the fact that it received nobody is already carried by `players_in = 0`, and
comparing an absent maximum against a present one would be inventing a value for it. Where
a whole dimension is unstated on either side the dimension is dropped and its weight
redistributed, and the response names it.

## What the distance deliberately does not contain

**Salary.** No source in this repository carries a historical contract, so a package's
money is unavailable for every side in the corpus. Scoring it on the query alone would
compare a number against nothing.

**Cash and trade exceptions.** The corpus states both — 209 cash legs and 207 trades whose
notes report a trade exception — and a *proposed* trade in this product states neither. A
feature the query can only ever answer "no" to does not measure similarity; it penalizes
every historical trade that happened to include one, which is 37 % of them. Both are
reported as attributes of the neighbour and excluded from the distance.

**Outcome.** Nothing here reads what happened next. A comparable is evidence about
precedent, not about consequence: these trades resembled yours, and that is the whole
claim. Similarity is not causality, and a historical trade that worked is not an argument
that yours will.

## Weights

Chosen by construct, and reported with the result:

| dimension | w | why |
| --- | --- | --- |
| `player_value` | 0.30 | the on-court value actually exchanged |
| `draft_capital` | 0.25 | the currency it is paid in |
| `structure` | 0.20 | how many bodies and how many teams — what kind of transaction |
| `age_profile` | 0.10 | win-now or later |
| `team_context` | 0.10 | who the team was when it did this |
| `timing` | 0.05 | deadline or offseason |

They are not fitted, because there is no target to fit them against: nothing in this
repository labels two trades as "similar". What *is* measured is whether the choice matters
— `neighbour_stability` re-ranks under uniform weights and under each single-dimension
weighting and reports the overlap, and `docs/methodology.md` carries the numbers.
"""

from __future__ import annotations

import math
import statistics
from dataclasses import dataclass, field
from datetime import date

from .projection import REPLACEMENT_TEI, TEAM_MINUTES

CONDITIONAL_CONVEYANCES = frozenset({"protected", "swap", "conditional"})

FEATURE_DIMENSIONS: dict[str, tuple[str, ...]] = {
    "player_value": ("value_in", "value_out", "best_in_tei", "best_out_tei"),
    "draft_capital": (
        "firsts_net",
        "seconds_net",
        "picks_in",
        "picks_out",
        "conditional_pick_share",
    ),
    "structure": ("players_in", "players_out", "n_teams"),
    "age_profile": ("age_in", "age_out"),
    "team_context": ("win_pct", "win_pct_gap"),
    "timing": ("is_in_season",),
}

DIMENSION_WEIGHTS: dict[str, float] = {
    "player_value": 0.30,
    "draft_capital": 0.25,
    "structure": 0.20,
    "age_profile": 0.10,
    "team_context": 0.10,
    "timing": 0.05,
}

FEATURE_LABELS: dict[str, str] = {
    "value_in": "value acquired",
    "value_out": "value sent",
    "best_in_tei": "best player acquired",
    "best_out_tei": "best player sent",
    "firsts_net": "net first-round picks",
    "seconds_net": "net second-round picks",
    "picks_in": "picks acquired",
    "picks_out": "picks sent",
    "conditional_pick_share": "share of picks with conditions",
    "players_in": "players acquired",
    "players_out": "players sent",
    "n_teams": "teams involved",
    "age_in": "age acquired",
    "age_out": "age sent",
    "win_pct": "team win percentage",
    "win_pct_gap": "win-percentage gap to the other side",
    "is_in_season": "made during the season",
}

DIMENSION_LABELS: dict[str, str] = {
    "player_value": "on-court value exchanged",
    "draft_capital": "draft capital",
    "structure": "deal structure",
    "age_profile": "age profile",
    "team_context": "team situation",
    "timing": "timing",
}


@dataclass(frozen=True)
class PlayerLeg:
    """A player moving one way, with the season-scored impact the corpus is built on.

    `tei` is a **single-season** index, not the recency-weighted window estimate the
    product serves elsewhere. It has to be: a 2024-25 trade cannot be described by a window
    that ends in 2026. Both the query side and every corpus side are built by the same
    function so the two are always on the same scale, and
    `test_comparable_trades.py::test_query_and_corpus_sides_are_built_by_one_function`
    keeps them there.
    """

    name: str
    player_id: str | None = None
    tei: float | None = None
    #: Minutes per game in the feature season.
    minutes: float | None = None
    age: float | None = None
    #: True when the player had recorded no NBA season **before** this trade — a draft
    #: right, or a rookie moved on draft night. He contributes zero on-court value because
    #: zero is what he had produced, which is a measurement and not an imputation.
    no_prior_nba_season: bool = False

    @property
    def value(self) -> float | None:
        """Minutes-share above replacement — the quantity the projection consumes."""
        if self.no_prior_nba_season:
            return 0.0
        if self.tei is None or self.minutes is None:
            return None
        return (self.minutes / TEAM_MINUTES) * (self.tei - REPLACEMENT_TEI)


@dataclass(frozen=True)
class PickLeg:
    draft_year: int
    round_number: int
    #: unconditional | protected | swap | conditional, as the source stated it.
    conveyance: str = "unconditional"

    @property
    def is_conditional(self) -> bool:
        return self.conveyance in CONDITIONAL_CONVEYANCES


@dataclass(frozen=True)
class TradeSide:
    """One team's view of one trade, in the terms similarity is defined on."""

    key: str
    team_abbreviation: str
    season: str
    #: The season whose production describes these players at the time of the move: the
    #: season itself for an in-season trade, the season just completed for an offseason
    #: one. Named on every result, because it is the reason a July trade is described by
    #: last season's numbers.
    feature_season: str
    transaction_date: date | None
    is_in_season: bool
    n_teams: int
    team_id: str | None = None
    team_name: str | None = None
    counterparty_abbreviations: tuple[str, ...] = ()
    incoming: tuple[PlayerLeg, ...] = ()
    outgoing: tuple[PlayerLeg, ...] = ()
    picks_in: tuple[PickLeg, ...] = ()
    picks_out: tuple[PickLeg, ...] = ()
    win_pct: float | None = None
    counterparty_win_pct: float | None = None
    #: Attributes of the completed trade that are reported but never scored — see the
    #: module docstring.
    cash_involved: bool = False
    trade_exception_received: bool = False
    source_text: str = ""
    notes_text: str | None = None
    unparsed_assets: tuple[str, ...] = ()

    @property
    def unmodelled_players(self) -> tuple[str, ...]:
        """Players the corpus cannot price for the feature season although they had
        played before it.

        Derived from the legs rather than passed in. It was a field until a test built a
        side by hand with an unpriced leg and got `rankable = True`: two sources of truth
        for one fact, and the one that decides whether a trade is shown was the one a
        caller had to remember to fill in.
        """
        return tuple(
            sorted(
                leg.name
                for leg in (*self.incoming, *self.outgoing)
                if leg.tei is None and not leg.no_prior_nba_season
            )
        )

    @property
    def rankable(self) -> bool:
        return not self.unmodelled_players

    @property
    def no_prior_season_players(self) -> tuple[str, ...]:
        return tuple(
            leg.name for leg in (*self.incoming, *self.outgoing) if leg.no_prior_nba_season
        )

    def _package_value(self, legs: tuple[PlayerLeg, ...]) -> float | None:
        if not legs:
            return 0.0
        values = [leg.value for leg in legs]
        if any(v is None for v in values):
            return None
        return sum(v for v in values if v is not None)

    @staticmethod
    def _best(legs: tuple[PlayerLeg, ...]) -> float | None:
        scored = [leg.tei for leg in legs if leg.tei is not None]
        return max(scored) if scored else None

    @staticmethod
    def _weighted_age(legs: tuple[PlayerLeg, ...]) -> float | None:
        pairs = [(leg.age, leg.minutes) for leg in legs if leg.age is not None]
        if not pairs:
            return None
        weights = [m if m is not None else 0.0 for _, m in pairs]
        total = sum(weights)
        if total <= 0:
            return statistics.fmean(a for a, _ in pairs)
        return sum(a * w for (a, _), w in zip(pairs, weights, strict=True)) / total

    def features(self) -> dict[str, float | None]:
        """The feature vector. `None` means the side does not state the feature."""
        picks = (*self.picks_in, *self.picks_out)
        conditional_share = (
            sum(1 for p in picks if p.is_conditional) / len(picks) if picks else None
        )
        gap = (
            self.win_pct - self.counterparty_win_pct
            if self.win_pct is not None and self.counterparty_win_pct is not None
            else None
        )
        return {
            "value_in": self._package_value(self.incoming),
            "value_out": self._package_value(self.outgoing),
            "best_in_tei": self._best(self.incoming),
            "best_out_tei": self._best(self.outgoing),
            "firsts_net": float(
                sum(1 for p in self.picks_in if p.round_number == 1)
                - sum(1 for p in self.picks_out if p.round_number == 1)
            ),
            "seconds_net": float(
                sum(1 for p in self.picks_in if p.round_number == 2)
                - sum(1 for p in self.picks_out if p.round_number == 2)
            ),
            "picks_in": float(len(self.picks_in)),
            "picks_out": float(len(self.picks_out)),
            "conditional_pick_share": conditional_share,
            "players_in": float(len(self.incoming)),
            "players_out": float(len(self.outgoing)),
            "n_teams": float(self.n_teams),
            "age_in": self._weighted_age(self.incoming),
            "age_out": self._weighted_age(self.outgoing),
            "win_pct": self.win_pct,
            "win_pct_gap": gap,
            "is_in_season": 1.0 if self.is_in_season else 0.0,
        }


ALL_FEATURES: tuple[str, ...] = tuple(f for group in FEATURE_DIMENSIONS.values() for f in group)


#: Features whose unit is defined by the game rather than estimated from the corpus: one
#: pick, one player, one team, and the full 0-1 range of a share.
#:
#: Estimating these was tried first and **degenerates**. 295 of 337 rankable sides receive
#: no first-round pick and 296 send none, so the interquartile range is zero, the median
#: absolute deviation is zero, and the chain falls through to the standard deviation — the
#: tail-driven statistic this module rejects for exactly these columns. A declared unit is
#: both more interpretable and more stable: two sides one pick apart are half a unit apart,
#: and that does not move when a seven-team trade enters the corpus.
DECLARED_SCALES: dict[str, float] = {
    "firsts_net": 1.0,
    "seconds_net": 1.0,
    "picks_in": 1.0,
    "picks_out": 1.0,
    "conditional_pick_share": 0.5,
    "players_in": 1.0,
    "players_out": 1.0,
    "n_teams": 1.0,
    "is_in_season": 1.0,
}


def robust_scales(sides: list[TradeSide]) -> dict[str, float]:
    """Per-feature spread: a declared unit where the game defines one, else the corpus's
    interquartile range, then MAD, then sd.

    A feature with no spread at all is omitted from the returned mapping, and
    `compare` drops any feature it cannot scale — a constant column contributes a
    zero distance to every pair, which silently reweights every dimension it sits in.
    """
    scales: dict[str, float] = dict(DECLARED_SCALES)
    for name in ALL_FEATURES:
        if name in scales:
            continue
        values = sorted(
            v for side in sides for v in [side.features().get(name)] if v is not None
        )
        if len(values) < 4:
            continue
        q1 = _quantile(values, 0.25)
        q3 = _quantile(values, 0.75)
        scale = q3 - q1
        if scale <= 0:
            deviations = sorted(abs(v - statistics.median(values)) for v in values)
            scale = 1.4826 * statistics.median(deviations)
        if scale <= 0 and len(values) > 1:
            scale = statistics.pstdev(values)
        if scale > 0:
            scales[name] = scale
    return scales


def _quantile(ordered: list[float], q: float) -> float:
    if len(ordered) == 1:
        return ordered[0]
    position = (len(ordered) - 1) * q
    low = math.floor(position)
    high = math.ceil(position)
    if low == high:
        return ordered[int(position)]
    return ordered[low] + (ordered[high] - ordered[low]) * (position - low)


def feature_distance(a: float, b: float, scale: float) -> float:
    """Bounded, monotone, scale-free. 0.5 at one scale unit apart; never exactly 1."""
    delta = abs(a - b)
    return delta / (delta + scale)


@dataclass
class DimensionResult:
    name: str
    weight: float
    distance: float
    features: dict[str, dict[str, float | None]] = field(default_factory=dict)

    @property
    def similarity(self) -> float:
        return 1.0 - self.distance


@dataclass
class Comparison:
    distance: float
    dimensions: list[DimensionResult]
    dimensions_unavailable: list[str]
    features_unavailable: list[str]

    @property
    def similarity(self) -> float:
        return 1.0 - self.distance

    def contributions(self) -> list[tuple[str, float]]:
        """Each dimension's share of the similarity, largest first.

        This is the ONLY thing an explanation may be built from: the numbers below are
        the terms of the sum that produced `similarity`, so a sentence derived from them
        cannot claim a driver the arithmetic did not have.
        """
        total_weight = sum(d.weight for d in self.dimensions)
        if total_weight <= 0:
            return []
        ranked = [
            (d.name, (d.weight / total_weight) * d.similarity) for d in self.dimensions
        ]
        return sorted(ranked, key=lambda pair: (-pair[1], pair[0]))


def compare(
    query: TradeSide,
    other: TradeSide,
    scales: dict[str, float],
    weights: dict[str, float] | None = None,
) -> Comparison:
    """Distance between two sides, decomposed by dimension and by feature."""
    weights = weights or DIMENSION_WEIGHTS
    query_features = query.features()
    other_features = other.features()

    results: list[DimensionResult] = []
    unavailable_dimensions: list[str] = []
    unavailable_features: list[str] = []
    for dimension, names in FEATURE_DIMENSIONS.items():
        per_feature: dict[str, dict[str, float | None]] = {}
        distances: list[float] = []
        for name in names:
            left = query_features.get(name)
            right = other_features.get(name)
            scale = scales.get(name)
            if left is None or right is None or scale is None:
                unavailable_features.append(name)
                continue
            distance = feature_distance(left, right, scale)
            distances.append(distance)
            per_feature[name] = {"query": left, "comparable": right, "distance": distance}
        if not distances:
            unavailable_dimensions.append(dimension)
            continue
        results.append(
            DimensionResult(
                name=dimension,
                weight=weights.get(dimension, 0.0),
                distance=statistics.fmean(distances),
                features=per_feature,
            )
        )

    total_weight = sum(d.weight for d in results)
    distance = (
        sum(d.weight * d.distance for d in results) / total_weight if total_weight > 0 else 1.0
    )
    return Comparison(
        distance=distance,
        dimensions=results,
        dimensions_unavailable=unavailable_dimensions,
        features_unavailable=sorted(set(unavailable_features)),
    )


@dataclass
class Neighbour:
    side: TradeSide
    comparison: Comparison

    @property
    def similarity(self) -> float:
        return self.comparison.similarity


def rank(
    query: TradeSide,
    corpus: list[TradeSide],
    scales: dict[str, float],
    weights: dict[str, float] | None = None,
    k: int = 5,
) -> list[Neighbour]:
    """The `k` closest rankable sides, nearest first.

    Ties break on the side key so the same corpus always returns the same order — the
    determinism `generate_candidates` already commits to, for the same reason.
    """
    scored = [
        Neighbour(side=side, comparison=compare(query, side, scales, weights))
        for side in corpus
        if side.rankable and side.key != query.key
    ]
    scored.sort(key=lambda n: (n.comparison.distance, n.side.key))
    return scored[:k]


# ------------------------------------------------------------------- explanation


def explain(query: TradeSide, neighbour: Neighbour, top_n: int = 3) -> list[str]:
    """Why this trade is considered comparable, derived from the distance itself.

    Every sentence is generated from `Comparison.contributions()` and the per-feature
    values that produced it, in that order, so the explanation cannot name a driver the
    arithmetic did not have. `test_comparable_trades.py` asserts the correspondence.
    """
    sentences: list[str] = []
    ranked = neighbour.comparison.contributions()
    by_name = {d.name: d for d in neighbour.comparison.dimensions}
    for name, _ in ranked[:top_n]:
        dimension = by_name[name]
        detail = _closest_features(dimension, query, neighbour.side)
        sentences.append(
            f"{DIMENSION_LABELS.get(name, name)}: "
            f"{dimension.similarity:.0%} similar{(' — ' + detail) if detail else ''}"
        )
    # The least-alike line names the dimension with the lowest SIMILARITY, not the one
    # with the smallest contribution. Those are different quantities — a contribution is
    # weight x similarity — and using the contribution produced the sentence "Least alike
    # on timing (100% similar)", which is both wrong and visibly wrong.
    named = {name for name, _ in ranked[:top_n]}
    remaining = [d for d in neighbour.comparison.dimensions if d.name not in named]
    if remaining:
        weakest = min(remaining, key=lambda d: (d.similarity, d.name))
        if weakest.similarity < 0.9:
            sentences.append(
                f"Least alike on {DIMENSION_LABELS.get(weakest.name, weakest.name)} "
                f"({weakest.similarity:.0%} similar)."
            )
    for dimension_name in neighbour.comparison.dimensions_unavailable:
        sentences.append(
            f"{DIMENSION_LABELS.get(dimension_name, dimension_name).capitalize()} could not "
            "be compared: one of the two sides does not state it."
        )
    return sentences


def _closest_features(
    dimension: DimensionResult, query: TradeSide, other: TradeSide
) -> str:
    """The two features that agree most closely inside a dimension, with their values."""
    ordered = sorted(dimension.features.items(), key=lambda kv: kv[1]["distance"] or 0.0)
    parts = []
    for name, values in ordered[:2]:
        label = FEATURE_LABELS.get(name, name)
        parts.append(f"{label} {_render(name, values['query'])} vs {_render(name, values['comparable'])}")
    return "; ".join(parts)


def _render(name: str, value: float | None) -> str:
    if value is None:
        return "unavailable"
    if name in ("players_in", "players_out", "n_teams", "picks_in", "picks_out"):
        return f"{value:.0f}"
    if name in ("firsts_net", "seconds_net"):
        return f"{value:+.0f}"
    if name in ("win_pct", "conditional_pick_share"):
        return f"{value:.0%}"
    if name == "win_pct_gap":
        return f"{value:+.0%}"
    if name == "is_in_season":
        return "in-season" if value >= 0.5 else "offseason"
    if name in ("age_in", "age_out"):
        return f"{value:.1f}"
    return f"{value:+.2f}"
