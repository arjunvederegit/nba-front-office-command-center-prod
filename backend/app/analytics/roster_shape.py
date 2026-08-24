"""What a trade does to the *shape* of a rotation — and what it deliberately does not say.

## This is roster composition, not lineup data

R6's third objective was a lineup-aware fit. It is **deferred**, on measurement, and this
module is the part that survives the measurement: how the 240 minutes are distributed
across player roles before and after a trade, from two systems that are already validated
— R4-3's deterministic size-first roles and R5.5's rotation allocator.

That is a real and useful thing to know. A team acquiring its fourth stretch big learns
something from "after this trade, 71 of your 240 minutes belong to stretch bigs, against a
league median of 34 and a 90th percentile of 58". It is **not** a statement about lineups.
Nothing here knows who is on the floor together, and no claim about on-court synergy is
made or implied.

## Why the lineup model is not here, measured

`nba_api`'s `LeagueDashLineups` is reachable and returns real data. Measured on 2024-25,
`Totals`, the top 2,000 groups by minutes:

| group size | median minutes | share ≥ 200 min | implied sd of net rating |
| --- | --- | --- | --- |
| 2 | 376.9 | 88.4 % | **3.7** per 100 |
| 3 | 249.4 | 66.6 % | **4.6** per 100 |
| 5 | **20.2** | **1.6 %** | **16.1** per 100 |

The implied standard deviation is `100 · 1.05 / sqrt(possessions)` at the median group,
taking possessions as 2.1 per minute. **At five-man level the estimate is noise**: 16
points per 100 against a league-wide team net-rating spread of roughly ±10, and that is
the *median of the top 2,000 groups*, not of the population.

Two- and three-man groups do have usable samples. They still do not give a trade-fit model,
for a reason no sample size fixes: a trade prices pairs that have **never played
together**, so observed pairs can only support a synergy model, and this repository holds
no held-out target to validate one against. Any target built from on-court net rating is
also the circularity R4-2 already established and withdrew a claim over.

`make lineup-availability` re-runs the measurement above, so the deferral stays falsifiable
rather than becoming folklore.

## The congestion threshold is measured, not chosen

A role is congested when its post-trade minutes exceed the **90th percentile of the same
role across the 30 ingested teams**, computed from each team's own allocated rotation. It
is a statement about this league in this season, and it moves when the league does.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass

#: The percentile above which a role's minutes are called congested. Reported alongside
#: the median so a reader can see how far above typical the team actually is.
CONGESTION_PERCENTILE = 90

#: A role holding fewer than this many of the 240 minutes is not "held" in any useful
#: sense — one 4-minute reserve is not a rotation role. Used only to decide whether a
#: role counts as *lost* by a trade.
ROLE_PRESENT_MINUTES = 8.0

UNCLASSIFIED_PREFIX = "unclassified"


@dataclass(frozen=True)
class RoleShare:
    role: str
    minutes_before: float
    minutes_after: float
    league_median: float | None
    league_threshold: float | None

    @property
    def delta(self) -> float:
        return self.minutes_after - self.minutes_before

    @property
    def congested(self) -> bool:
        return (
            self.league_threshold is not None
            and self.minutes_after > self.league_threshold
            and self.minutes_after > self.minutes_before
        )

    @property
    def lost(self) -> bool:
        return (
            self.minutes_before >= ROLE_PRESENT_MINUTES
            and self.minutes_after < ROLE_PRESENT_MINUTES
        )


def role_minutes(
    minutes: dict[str, float], roles: dict[str, str]
) -> dict[str, float]:
    """Minutes by role. A player with no assigned role is counted under `unassigned`,
    never distributed across the roles that are known."""
    totals: dict[str, float] = {}
    for player_id, played in minutes.items():
        role = roles.get(player_id) or "unassigned"
        totals[role] = totals.get(role, 0.0) + float(played)
    return totals


def percentile(values: list[float], share: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    position = (len(ordered) - 1) * (share / 100.0)
    low = int(position)
    high = min(low + 1, len(ordered) - 1)
    return ordered[low] + (ordered[high] - ordered[low]) * (position - low)


def league_role_reference(per_team: list[dict[str, float]]) -> dict[str, dict[str, float]]:
    """Median and congestion threshold per role, over the teams supplied.

    Every team contributes a value for every role, including zero. Omitting the zeros
    would compute the threshold over only the teams that *have* the role, which makes a
    rare role's threshold high precisely because it is rare.
    """
    roles = {role for team in per_team for role in team}
    reference: dict[str, dict[str, float]] = {}
    for role in sorted(roles):
        values = [team.get(role, 0.0) for team in per_team]
        median = statistics.median(values)
        threshold = percentile(values, CONGESTION_PERCENTILE)
        if threshold is None:
            continue
        reference[role] = {"median": round(median, 1), "threshold": round(threshold, 1)}
    return reference


def shape_report(
    before: dict[str, float],
    after: dict[str, float],
    roles: dict[str, str],
    reference: dict[str, dict[str, float]],
    incoming_ids: set[str],
) -> dict:
    """Role minutes before and after, with the league's own distribution beside them."""
    before_minutes = role_minutes(before, roles)
    after_minutes = role_minutes(after, roles)
    shares = [
        RoleShare(
            role=role,
            minutes_before=round(before_minutes.get(role, 0.0), 1),
            minutes_after=round(after_minutes.get(role, 0.0), 1),
            league_median=(reference.get(role) or {}).get("median"),
            league_threshold=(reference.get(role) or {}).get("threshold"),
        )
        for role in sorted(set(before_minutes) | set(after_minutes) | set(reference))
    ]
    arriving_roles = sorted({roles[pid] for pid in incoming_ids if pid in roles})
    congested = [s for s in shares if s.congested]
    lost = [s for s in shares if s.lost]
    return {
        "roles": [
            {
                "role": s.role,
                "minutes_before": s.minutes_before,
                "minutes_after": s.minutes_after,
                "delta": round(s.delta, 1),
                "league_median": s.league_median,
                "league_threshold": s.league_threshold,
                "congested": s.congested,
                "lost": s.lost,
            }
            for s in shares
            if s.minutes_before > 0 or s.minutes_after > 0
        ],
        "arriving_roles": arriving_roles,
        "congested_roles": [s.role for s in congested],
        "roles_lost": [s.role for s in lost],
        "congestion_percentile": CONGESTION_PERCENTILE,
        "unassigned_minutes_after": round(after_minutes.get("unassigned", 0.0), 1),
        "basis": (
            "Roster composition, from R4-3's deterministic roles and R5.5's rotation "
            "allocator. It is not lineup data: nothing here knows who is on the floor "
            "together, and no claim about on-court synergy is made."
        ),
        "lineup_fit": {
            "available": False,
            "reason": (
                "five-man lineup samples are too small to estimate a lineup effect — the "
                "median group among the top 2,000 by minutes played 20.2 minutes in "
                "2024-25, which carries a standard error of about 16 net-rating points "
                "per 100 possessions against a league team spread of roughly ±10"
            ),
            "also": (
                "two- and three-man groups do have usable samples, but a trade prices "
                "combinations that have never played together, and this repository holds "
                "no held-out target against which a synergy model could be validated"
            ),
            "recheck": "make lineup-availability",
        },
    }
