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


def simulate_delta_wins(
    incoming: list[PlayerDraw],
    outgoing: list[PlayerDraw],
    wins_mapping: dict,
    n_draws: int = N_DRAWS,
    seed: int = RANDOM_SEED,
) -> dict:
    rng = np.random.default_rng(seed)
    slope = float(wins_mapping.get("slope", 2.7))
    slope_sigma = abs(slope) * 0.15  # conversion uncertainty
    REPLACEMENT_TEI = -2.0

    def draw_side(players: list[PlayerDraw]) -> np.ndarray:
        total = np.zeros(n_draws)
        for p in players:
            tei_draws = rng.normal(p.tei, max(p.tei_sigma, 0.3), n_draws)
            # availability drawn from a beta concentrated at the historical rate
            a = max(p.availability, 0.02) * 40
            b = max(1 - p.availability, 0.02) * 40
            avail_draws = rng.beta(a, b, n_draws)
            effective = avail_draws * tei_draws + (1 - avail_draws) * REPLACEMENT_TEI
            minutes_noise = rng.normal(1.0, 0.12, n_draws).clip(0.5, 1.5)
            total += p.minutes_share * minutes_noise * effective
        return total

    delta_net = draw_side(incoming) - draw_side(outgoing)
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
