"""Monte Carlo uncertainty for trade outcomes.

Draws over player impact (validation-residual spread), availability (beta), and the
net-rating→wins conversion (calibration residuals). Reports quantiles and the
probability of a positive outcome — small differences are never presented as
certainty."""

from dataclasses import dataclass

import numpy as np

from .features import RANDOM_SEED

N_DRAWS = 2000


@dataclass
class PlayerDraw:
    tei: float
    tei_sigma: float
    availability: float
    minutes_share: float  # share of 240 team minutes
    # Identity, so each player draws from their own stream. Without it the simulation
    # consumed one shared generator in list order, and the same trade produced different
    # numbers depending on the order the players happened to arrive in — which was
    # database order until `_roster_cards` gained an `ORDER BY` (R1-5). See
    # `_player_rng` for why identity, not position, is the right key.
    key: str = ""


def simulate_delta_wins(
    incoming: list[PlayerDraw],
    outgoing: list[PlayerDraw],
    wins_mapping: dict,
    n_draws: int = N_DRAWS,
    seed: int = RANDOM_SEED,
) -> dict:
    if not incoming and not outgoing:
        # Nothing moves, so every draw is exactly zero. `(delta_wins > 0).mean()` on an
        # all-zero array is 0.0, which reads as "certain to hurt" — the opposite of the
        # truth. There is no probability to report about a trade that does nothing.
        return {
            "n_draws": 0,
            "median": 0.0,
            "p10": 0.0,
            "p90": 0.0,
            "prob_positive": None,
            "unavailable": "no players move, so there is no outcome distribution",
            "top_uncertainty_drivers": [],
        }

    rng = np.random.default_rng(seed)
    slope = float(wins_mapping.get("slope", 2.7))
    slope_sigma = abs(slope) * 0.15  # conversion uncertainty
    REPLACEMENT_TEI = -2.0

    def _player_rng(player: PlayerDraw, side: str, index: int) -> np.random.Generator:
        """A stream per player, derived from the run seed and the player's identity.

        Falls back to position only when no identity was supplied, which is the one case
        where order is all there is."""
        label = player.key or f"{side}:{index}"
        return np.random.default_rng([seed, *label.encode()])

    def draw_side(players: list[PlayerDraw], side: str) -> np.ndarray:
        total = np.zeros(n_draws)
        for index, p in enumerate(players):
            player_rng = _player_rng(p, side, index)
            tei_draws = player_rng.normal(p.tei, max(p.tei_sigma, 0.3), n_draws)
            # availability drawn from a beta concentrated at the historical rate
            a = max(p.availability, 0.02) * 40
            b = max(1 - p.availability, 0.02) * 40
            avail_draws = player_rng.beta(a, b, n_draws)
            effective = avail_draws * tei_draws + (1 - avail_draws) * REPLACEMENT_TEI
            minutes_noise = player_rng.normal(1.0, 0.12, n_draws).clip(0.5, 1.5)
            total += p.minutes_share * minutes_noise * effective
        return total

    delta_net = draw_side(incoming, "in") - draw_side(outgoing, "out")
    slope_draws = rng.normal(slope, slope_sigma, n_draws)
    delta_wins = delta_net * slope_draws

    drivers: list[dict] = []
    for label, players in (("incoming", incoming), ("outgoing", outgoing)):
        for p in players:
            spread = p.minutes_share * max(p.tei_sigma, 0.3) * abs(slope)
            drivers.append({"side": label, "spread_wins": round(float(spread), 2)})
    drivers.sort(key=lambda d: float(d["spread_wins"]), reverse=True)

    return {
        "n_draws": n_draws,
        "median": float(np.median(delta_wins)),
        "p10": float(np.percentile(delta_wins, 10)),
        "p90": float(np.percentile(delta_wins, 90)),
        "prob_positive": float((delta_wins > 0).mean()),
        "top_uncertainty_drivers": drivers[:5],
    }
