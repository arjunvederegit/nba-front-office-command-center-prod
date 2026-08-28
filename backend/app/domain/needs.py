"""The roster-need vocabulary: what a team can be short of, and whether Pivot can name a
player skill that fixes it.

Eleven need keys are measured today — nine from league percentile rules over team
statistics, two from roster composition. `NEED_TO_SKILL` maps a need to the single player
skill that addresses it, and it is deliberately **not total**: `point_of_attack_defense` has
no entry, because R4-2 built a player-side composite for it, measured it against its own
pre-registered class, found it worse than the proxy it replaced, and withdrew the claim
rather than tuning until it passed.

That absence is the most important thing in this module. A team that cannot contain a ball
handler is still told so; it is simply not handed a player who supposedly fixes it. Pivot
would rather name a weakness it cannot solve than solve it with a number it does not
believe.

The canonical definitions live here; `analytics.needs` re-exports `NEED_TO_SKILL` so every
existing consumer keeps its import, and the percentile rules that produce severities stay
in `analytics.needs` where the data is.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class NeedSource(StrEnum):
    """Where the shortfall is measured."""

    #: A league percentile over a team statistic.
    TEAM_STATISTIC = "team_statistic"
    #: A property of who is on the roster, not of how they have played.
    ROSTER_COMPOSITION = "roster_composition"


@dataclass(frozen=True, slots=True)
class NeedDefinition:
    key: str
    label: str
    source: NeedSource
    definition: str
    #: The player skill that addresses it, or None where Pivot declines to claim one.
    addressed_by: str | None
    #: Why no skill addresses it. Non-empty exactly when `addressed_by` is None.
    unaddressable_reason: str = ""
    #: Stated where the underlying statistic only partially captures the concept.
    proxy_note: str = ""

    def __post_init__(self) -> None:
        if self.addressed_by is None and not self.unaddressable_reason:
            raise ValueError(f"{self.key}: an unaddressable need must state why")


# The reason a user reads when they ask who fixes this need. Kept **verbatim** from R4-2:
# it is quoted into the acquisition panel, the team-outlook need row and the decision memo,
# and `test_acquisition_targets.py::test_a_need_no_skill_addresses_is_an_answer_not_a_failure`
# pins the substring. The claim behind it was built, measured against its own
# pre-registered class, found worse than the proxy it replaced, and withdrawn.
_POA_REASON = (
    "no player skill claims to address this: on-ball defence cannot be measured from "
    "box-score data, and a steals-based proxy rates ball-dominant guards above the "
    "defenders who actually guard them"
)

_N = NeedDefinition
CATALOG: tuple[NeedDefinition, ...] = (
    _N("three_point_volume", "Three-point volume", NeedSource.TEAM_STATISTIC,
       "The team does not shoot enough threes to bend a defense.",
       "shooting_volume"),
    _N("shooting_efficiency", "Shooting efficiency", NeedSource.TEAM_STATISTIC,
       "The team does not convert the shots it takes.",
       "shooting_accuracy"),
    _N("offense_overall", "Offense", NeedSource.TEAM_STATISTIC,
       "Points produced per possession trail the league.",
       "scoring"),
    _N("defense_overall", "Defense", NeedSource.TEAM_STATISTIC,
       "Points conceded per possession trail the league.",
       "team_defense"),
    _N("defensive_rebounding", "Defensive rebounding", NeedSource.TEAM_STATISTIC,
       "The team concedes second chances.",
       "rebounding"),
    _N("playmaking", "Playmaking", NeedSource.TEAM_STATISTIC,
       "Few baskets are created by a pass.",
       "creation"),
    _N("ball_security", "Ball security", NeedSource.TEAM_STATISTIC,
       "The team gives possessions away.",
       "turnover_avoidance"),
    _N("rim_protection", "Rim protection", NeedSource.TEAM_STATISTIC,
       "The basket is not defended.",
       "rim_protection",
       proxy_note="Blocks are a partial proxy for rim protection."),
    _N("point_of_attack_defense", "Point-of-attack defense", NeedSource.TEAM_STATISTIC,
       "The team cannot contain a ball handler on the perimeter.",
       None,
       unaddressable_reason=_POA_REASON,
       proxy_note="Steals are a partial proxy for point-of-attack pressure."),
    _N("lineup_size", "Lineup size", NeedSource.ROSTER_COMPOSITION,
       "Average roster height sits below what the league typically fields.",
       "size"),
    _N("secondary_creation", "Secondary creation", NeedSource.ROSTER_COMPOSITION,
       "The roster carries too few players who can create for others.",
       "creation"),
)

BY_KEY: dict[str, NeedDefinition] = {n.key: n for n in CATALOG}

NEED_KEYS: tuple[str, ...] = tuple(n.key for n in CATALOG)

#: Canonical need -> skill map. `analytics.needs` re-exports this.
#: Needs with no player-side answer are absent by design, not by omission.
NEED_TO_SKILL: dict[str, str] = {
    n.key: n.addressed_by for n in CATALOG if n.addressed_by is not None
}

#: Needs Pivot measures on the team side but declines to claim any player skill addresses,
#: with the reason shown wherever the need is. `analytics.archetypes` re-exports this.
UNADDRESSABLE_NEEDS: dict[str, str] = {
    n.key: n.unaddressable_reason for n in CATALOG if n.addressed_by is None
}


# ------------------------------------------------------------------ classification
# The severity and percentile at which a need row becomes a headline WEAKNESS, and the
# percentile at which it becomes a STRENGTH.
#
# These thresholds were previously constants in the browser (`frontend/lib/needs.ts`),
# which made a basketball judgement — "is this team bad at this?" — a presentation-layer
# decision that no backend test could reach. They live here now, and the team-profile
# service applies them, so one answer is served to every client.
#
# The two sets are disjoint by construction: a strength requires severity exactly 0, a
# weakness requires severity at or above the threshold. Atlanta once appeared under both
# headings for defensive rebounding (QA-9), which is what a shared threshold buys you.
NEED_SEVERITY_THRESHOLD = 0.35
STRENGTH_PERCENTILE_THRESHOLD = 65.0
#: How many rows each list shows. A presentation cap, applied server-side so every client
#: agrees on which rows made the cut.
HEADLINE_ROWS = 4


def describe(key: str) -> NeedDefinition | None:
    return BY_KEY.get(key)


def addressable(key: str) -> bool:
    return key in NEED_TO_SKILL


def _check_skills_exist() -> None:
    """Every need must point at a skill the product actually declares."""
    from .skills import SKILL_KEYS

    unknown = sorted(set(NEED_TO_SKILL.values()) - set(SKILL_KEYS))
    if unknown:
        raise RuntimeError(f"needs point at undeclared skills: {unknown}")


_check_skills_exist()


__all__ = [
    "BY_KEY",
    "CATALOG",
    "HEADLINE_ROWS",
    "NEED_KEYS",
    "NEED_SEVERITY_THRESHOLD",
    "NEED_TO_SKILL",
    "STRENGTH_PERCENTILE_THRESHOLD",
    "UNADDRESSABLE_NEEDS",
    "NeedDefinition",
    "NeedSource",
    "addressable",
    "describe",
]
