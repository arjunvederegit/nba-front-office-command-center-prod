"""Monte Carlo uncertainty for trade outcomes.

Draws over player impact (per-player σ from playing time), availability (beta), and the
wins-per-net-rating slope (its own fitted SE). Reports quantiles and the probability of a
positive outcome — small differences are never presented as certainty.

**R3-5: one definition of `delta_net`.** The simulation used to sum raw minute shares over
the *traded players only*, while the point estimate reallocated all 240 minutes across the
whole roster. Two different quantities, reported side by side as if they were the same
one, and the gap widened with trade size — a 5-for-5 made it unmissable. The simulation
now draws over exactly the rotation the point estimate allocates: same players, same
minutes, same replacement fill, same conversion. Incumbents appear on both sides and, with
a per-player draw stream, cancel exactly — which is what lets the median reproduce the
point estimate rather than merely resemble it.
"""

from dataclasses import dataclass, field

import numpy as np

from .features import RANDOM_SEED
from .projection import REPLACEMENT_TEI, TEAM_MINUTES, TEI_TO_NET_RATING

N_DRAWS = 2000


@dataclass
class PlayerDraw:
    tei: float
    tei_sigma: float
    availability: float
    minutes_share: float  # share of the 240 team minutes THIS player is allocated
    # Identity, so each player draws from their own stream. Without it the simulation
    # consumed one shared generator in list order, and the same trade produced different
    # numbers depending on the order the players happened to arrive in — which was
    # database order until `_roster_cards` gained an `ORDER BY` (R1-5). Identity also
    # makes an incumbent's draw identical before and after the trade, so their
    # contribution cancels exactly instead of adding spurious noise.
    key: str = ""


@dataclass
class RotationDraw:
    """One side of the comparison: a whole rotation, not a list of moved players."""

    players: list[PlayerDraw] = field(default_factory=list)

    @property
    def allocated_share(self) -> float:
        return sum(p.minutes_share for p in self.players)


def _player_rng(player: PlayerDraw, index: int, seed: int) -> np.random.Generator:
    """A stream per player, derived from the run seed and the player's identity.

    Falls back to position only when no identity was supplied, which is the one case
    where order is all there is."""
    label = player.key or f"anon:{index}"
    return np.random.default_rng([seed, *label.encode()])


def _team_tei_draws(rotation: RotationDraw, n_draws: int, seed: int) -> np.ndarray:
    """Minutes-weighted team TEI per draw, with unfilled minutes at replacement level.

    Mirrors `projection.allocate_rotation` exactly: weights are shares of the full 240
    team minutes, and whatever the roster cannot fill is played by a replacement.
    """
    total = np.zeros(n_draws)
    for index, p in enumerate(rotation.players):
        rng = _player_rng(p, index, seed)
        tei_draws = rng.normal(p.tei, max(p.tei_sigma, 0.05), n_draws)
        # Availability is applied here and nowhere else. Applying it in the caller as
        # well was the double discount behind the point-estimate/simulation gap (C2).
        a = max(p.availability, 0.02) * 40
        b = max(1 - p.availability, 0.02) * 40
        avail_draws = rng.beta(a, b, n_draws)
        effective = avail_draws * tei_draws + (1 - avail_draws) * REPLACEMENT_TEI
        total += p.minutes_share * effective
    unfilled = max(1.0 - rotation.allocated_share, 0.0)
    return total + unfilled * REPLACEMENT_TEI


def _no_distribution(reason: str) -> dict:
    return {
        "n_draws": 0,
        "median": 0.0,
        "p10": 0.0,
        "p90": 0.0,
        "prob_positive": None,
        "unavailable": reason,
        "top_uncertainty_drivers": [],
    }


def simulate_delta_wins(
    before: RotationDraw,
    after: RotationDraw,
    wins_mapping: dict,
    n_draws: int = N_DRAWS,
    seed: int = RANDOM_SEED,
    moved_keys: set[str] | None = None,
) -> dict:
    """Distribution of the change in projected wins between two rotations."""
    if not before.players and not after.players:
        return _no_distribution("no rotation to project, so there is no outcome distribution")

    by_key_before = {p.key: p.minutes_share for p in before.players}
    by_key_after = {p.key: p.minutes_share for p in after.players}
    if by_key_before.keys() == by_key_after.keys() and all(
        abs(by_key_before[k] - by_key_after[k]) < 1e-12 for k in by_key_before
    ):
        # Nothing moves, so every draw is exactly zero, and `(delta_wins > 0).mean()` on
        # an all-zero array is 0.0 — which reads as "certain to hurt".
        return _no_distribution("no players move, so there is no outcome distribution")

    rng = np.random.default_rng(seed)
    slope = float(wins_mapping.get("slope", 2.7))
    # The wins-per-net-rating fit's own parameter SE. `residual_std` is the spread of team
    # wins about the line (2.894) — roughly 55x the slope's SE — and using it would make
    # every interval that much too wide (C12).
    slope_sigma = float(wins_mapping.get("slope_se") or abs(slope) * 0.05)

    delta_net = TEI_TO_NET_RATING * (
        _team_tei_draws(after, n_draws, seed) - _team_tei_draws(before, n_draws, seed)
    )
    delta_wins = delta_net * rng.normal(slope, slope_sigma, n_draws)

    moved = moved_keys or set()
    drivers: list[dict] = []
    seen: set[str] = set()
    for label, rotation in (("after", after), ("before", before)):
        for p in rotation.players:
            if p.key in seen or (moved and p.key not in moved):
                continue
            seen.add(p.key)
            spread = p.minutes_share * max(p.tei_sigma, 0.05) * TEI_TO_NET_RATING * abs(slope)
            drivers.append({"side": label, "spread_wins": round(float(spread), 2)})
    drivers.sort(key=lambda d: float(d["spread_wins"]), reverse=True)

    return {
        "n_draws": n_draws,
        # The mean is the quantity that must equal the point estimate: availability
        # enters both linearly, so E[simulated delta] is the deterministic delta. The
        # median differs from it by the skew of the availability beta, which is a real
        # property of the distribution and not a disagreement between the two paths.
        "mean": float(np.mean(delta_wins)),
        "median": float(np.median(delta_wins)),
        "p10": float(np.percentile(delta_wins, 10)),
        "p90": float(np.percentile(delta_wins, 90)),
        "prob_positive": float((delta_wins > 0).mean()),
        "top_uncertainty_drivers": drivers[:5],
    }


def rotation_draw_from(detail: list[dict], sigma_by_player: dict[str, float]) -> RotationDraw:
    """Build a `RotationDraw` from `allocate_rotation`'s own detail rows.

    Reading the minutes off the allocator rather than recomputing them is what keeps the
    two paths in step: there is one allocation, and both the point estimate and the
    simulation read it.
    """
    return RotationDraw(
        players=[
            PlayerDraw(
                tei=float(row["tei"]),
                tei_sigma=float(sigma_by_player.get(row["player_id"], 0.0)),
                availability=float(row["availability"]),
                minutes_share=float(row["minutes"]) / TEAM_MINUTES,
                key=str(row["player_id"]),
            )
            for row in detail
        ]
    )
