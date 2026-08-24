"""Re-measure whether lineup data can support a fit model.

R6 deferred the lineup-aware fit on a measurement rather than on an assumption, and a
measurement that cannot be re-run becomes folklore. `make lineup-availability` fetches the
same three endpoints and prints the same table, so the deferral can be overturned by
evidence the moment the evidence changes.

Network required, and nothing is stored: this reads sample sizes and throws the rows away.
It is not an ingestion path, there is no table behind it, and no NBA.com payload is
retained or redistributed.

The statistic is the standard error a net-rating estimate carries at the median group:

    sd(net rating per 100) = 100 * 1.05 / sqrt(possessions)
    possessions            = minutes * 2.1

1.05 points per possession is the league's own scoring rate; 2.1 possessions per minute
follows from a ~100-possession, ~48-minute game for each team. Both are stated here rather
than fitted, because the conclusion does not turn on their third digit: at five-man level
the error is an order of magnitude above the effect anyone is trying to measure.
"""

from __future__ import annotations

import time
from typing import Any

POINTS_PER_POSSESSION = 1.05
POSSESSIONS_PER_MINUTE = 2.1
GROUP_SIZES = (2, 3, 5)
#: A group needs at least this many minutes before its net rating carries the precision a
#: fit model would need — about ±5 points per 100, which is half the league-wide spread of
#: team net ratings.
USABLE_MINUTES = 200.0


def implied_net_rating_sd(minutes: float) -> float:
    possessions = max(minutes, 1e-9) * POSSESSIONS_PER_MINUTE
    return 100.0 * POINTS_PER_POSSESSION / (possessions**0.5)


def measure(season: str, sizes: tuple[int, ...] = GROUP_SIZES) -> dict[str, Any]:
    """Sample sizes per group size, from NBA.com. Raises if the network is unavailable."""
    import pandas as pd
    from nba_api.stats.endpoints import leaguedashlineups

    from app.integrations.nba_api.headers import build_headers

    headers = build_headers() or None
    rows: list[dict[str, Any]] = []
    for index, size in enumerate(sizes):
        if index:
            time.sleep(1.5)
        frame = leaguedashlineups.LeagueDashLineups(
            season=season,
            group_quantity=size,
            per_mode_detailed="Totals",
            timeout=60,
            headers=headers,
        ).get_data_frames()[0]
        minutes = pd.to_numeric(frame["MIN"], errors="coerce").dropna()
        median = float(minutes.median()) if len(minutes) else 0.0
        rows.append(
            {
                "group_size": size,
                "groups_returned": int(len(frame)),
                "min_minutes": round(float(minutes.min()), 1) if len(minutes) else None,
                "median_minutes": round(median, 1),
                "max_minutes": round(float(minutes.max()), 1) if len(minutes) else None,
                "share_at_least_usable": round(float((minutes >= USABLE_MINUTES).mean()), 4)
                if len(minutes)
                else None,
                "implied_net_rating_sd_at_median": round(implied_net_rating_sd(median), 1),
            }
        )
    five = next((r for r in rows if r["group_size"] == 5), None)
    return {
        "season": season,
        "source": "NBA.com LeagueDashLineups via nba_api (measured, never stored)",
        "usable_minutes_threshold": USABLE_MINUTES,
        "groups": rows,
        "verdict": {
            "five_man_usable": bool(
                five and (five["share_at_least_usable"] or 0.0) >= 0.5
            ),
            "note": (
                "A five-man fit model needs the net rating of a group to be estimable. "
                "At the median group among those returned the standard error is "
                f"{five['implied_net_rating_sd_at_median'] if five else '?'} points per "
                "100 possessions, against a league team spread of roughly ±10. Two- and "
                "three-man groups are estimable, but a trade prices combinations that "
                "have never played together, and nothing in this repository holds a "
                "held-out target to validate a synergy model against."
            ),
        },
    }
