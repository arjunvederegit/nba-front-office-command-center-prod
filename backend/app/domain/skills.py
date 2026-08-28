"""The canonical skill vocabulary — what Pivot claims to know about a player, and what
it has declared it does not.

Two lists live here, and keeping them apart is the point.

`SKILL_KEYS` is the **measured** vocabulary: nine dimensions that `analytics.archetypes.
player_skill_vector` actually computes from ingested box-score data, as percentiles of the
scored league population. It is the source of truth for that list — `analytics.archetypes`
re-exports it, so every existing consumer keeps its import. **Its contents and order are
load-bearing**: `skill_schema_fingerprint()` hashes `"|".join(SKILL_KEYS)` to namespace the
six-hour league skill cache, and `player_archetypes.role_id` is a frozen append-only map.
Reordering or renaming silently changes a cache identity and a persisted meaning.

`DECLARED_DIMENSIONS` is the **full** basketball vocabulary Pivot intends to reason in —
the offensive and defensive dimensions a GM actually talks about. Most of them are not
measured today, and each says why in its own words. This is not a TODO list dressed as a
schema: it is the honest half of the product's claim. A dimension that appears here with
`available=False` is one Pivot will render as explicitly unavailable rather than quietly
omit, so a reader learns that Pivot cannot see switchability rather than concluding that
switchability does not matter.

The R9 Player Intelligence engine's job is to move dimensions from `available=False` to
`available=True` by finding data that supports them — not to invent grades for them. Until
it does, `unavailable_reason` is the product's answer.

Nothing here computes a skill. The computation is `analytics.archetypes.
player_skill_vector`, and it stays there.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from .evidence import Confidence, Evidence


class SkillSide(StrEnum):
    OFFENSE = "offense"
    DEFENSE = "defense"
    PHYSICAL = "physical"


@dataclass(frozen=True, slots=True)
class SkillDimension:
    """One basketball capability, and Pivot's honest position on whether it can see it."""

    key: str
    label: str
    side: SkillSide
    #: What the dimension means, in the language a GM would use.
    definition: str
    #: True when `player_skill_vector` produces a value for this key today.
    available: bool
    #: How the value is produced. Empty when unavailable.
    method: str = ""
    #: Why there is no value. Non-empty exactly when `available` is False.
    unavailable_reason: str = ""
    evidence: Evidence = Evidence.DERIVED
    confidence: Confidence = Confidence.MEASURED
    #: What the number cannot support even where it exists.
    limitations: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.available and not self.method:
            raise ValueError(f"{self.key}: an available skill must state its method")
        if not self.available and not self.unavailable_reason:
            raise ValueError(f"{self.key}: an unavailable skill must state why")


# --------------------------------------------------------------------------- measured
# The nine dimensions computed today. **Order is part of a cache identity — append only.**
SKILL_KEYS: list[str] = [
    "shooting_volume",
    "shooting_accuracy",
    "creation",
    "turnover_avoidance",
    "team_defense",
    "rim_protection",
    "rebounding",
    "size",
    "scoring",
]

_MEASURED: tuple[SkillDimension, ...] = (
    SkillDimension(
        key="shooting_volume",
        label="Shooting volume",
        side=SkillSide.OFFENSE,
        definition="How much of a player's shot diet is three-point attempts.",
        available=True,
        method="League percentile of three-point attempt rate over the recency-weighted feature window.",
        limitations=("Volume is not accuracy — read it beside shooting accuracy.",),
    ),
    SkillDimension(
        key="shooting_accuracy",
        label="Shooting accuracy",
        side=SkillSide.OFFENSE,
        definition="How well a player converts the shots taken.",
        available=True,
        method=(
            "League percentile of three-point percentage shrunk toward the league mean "
            "with k = 300 attempts, then blended with true shooting."
        ),
        limitations=(
            "Shrinkage means a small sample is pulled toward league average by design; "
            "a hot 40-attempt stretch will not read as elite.",
        ),
    ),
    SkillDimension(
        key="creation",
        label="Shot creation",
        side=SkillSide.OFFENSE,
        definition="How much of the offense a player generates for others.",
        available=True,
        method="League percentile of assist rate over the recency-weighted feature window.",
        limitations=(
            "Assist rate credits the pass that precedes a make, not the advantage that "
            "created it; it under-credits gravity and off-ball creation.",
        ),
    ),
    SkillDimension(
        key="turnover_avoidance",
        label="Ball security",
        side=SkillSide.OFFENSE,
        definition="How reliably a player keeps possession.",
        available=True,
        method="League percentile of inverted turnover rate.",
        limitations=("Low usage flatters this dimension; read it beside creation.",),
    ),
    SkillDimension(
        key="scoring",
        label="Scoring",
        side=SkillSide.OFFENSE,
        definition="Scoring output and the usage it is produced at.",
        available=True,
        method="League percentile of a usage-and-efficiency blend over the feature window.",
    ),
    SkillDimension(
        key="team_defense",
        label="Team defense",
        side=SkillSide.DEFENSE,
        definition="Defensive contribution visible in the box score and on-court results.",
        available=True,
        method=(
            "League percentile of a composite over defensive rebounding, blocks, steals "
            "and on-court defensive rating."
        ),
        confidence=Confidence.HEURISTIC,
        limitations=(
            "Every available defensive target derives from on-court DEF_RATING, so any "
            "validation of it is circular to some degree. Justified by construct, not "
            "validated.",
            "Stability against the steals proxy it replaced is 0.838 vs 0.669 — better, "
            "not proven.",
        ),
    ),
    SkillDimension(
        key="rim_protection",
        label="Rim protection",
        side=SkillSide.DEFENSE,
        definition="Deterrence and shot-blocking at the basket.",
        available=True,
        method="League percentile of blocks per minute, adjusted for size.",
        confidence=Confidence.HEURISTIC,
        limitations=(
            "Blocks are a partial proxy: they count the shots contested loudly, not the "
            "ones never attempted.",
        ),
    ),
    SkillDimension(
        key="rebounding",
        label="Rebounding",
        side=SkillSide.DEFENSE,
        definition="Share of available rebounds secured.",
        available=True,
        method="League percentile of defensive and offensive rebound rate.",
    ),
    SkillDimension(
        key="size",
        label="Positional size",
        side=SkillSide.PHYSICAL,
        definition="Listed height relative to the league.",
        available=True,
        method="League percentile of listed height.",
        evidence=Evidence.OBSERVED,
        limitations=(
            "Listed height only. No wingspan, standing reach or weight is ingested, and "
            "a player with no listed height is omitted rather than filled.",
        ),
    ),
)

# ----------------------------------------------------------------------- not measured
# The dimensions Pivot reasons about but cannot see from box-score data. Each states the
# acquisition that would unlock it. R9's job is to move these across; until then the
# product says so rather than inventing a grade.
_TRACKING = (
    "Needs player-tracking or matchup data. Every source ingested today is box-score "
    "aggregate, which cannot separate this from the possessions around it."
)
_PLAY_TYPE = (
    "Needs play-type or shot-location data. The ingested season totals carry neither "
    "shot coordinates nor play-type splits."
)

_DECLARED_ONLY: tuple[SkillDimension, ...] = (
    SkillDimension(
        key="spacing_gravity",
        label="Spacing / gravity",
        side=SkillSide.OFFENSE,
        definition="How far a defense bends to account for a player away from the ball.",
        available=False,
        unavailable_reason=_TRACKING,
    ),
    SkillDimension(
        key="rim_pressure",
        label="Rim pressure",
        side=SkillSide.OFFENSE,
        definition="How often a player forces the defense to defend the basket.",
        available=False,
        unavailable_reason=_PLAY_TYPE,
    ),
    SkillDimension(
        key="finishing",
        label="Finishing",
        side=SkillSide.OFFENSE,
        definition="Conversion once at the rim.",
        available=False,
        unavailable_reason=_PLAY_TYPE,
    ),
    SkillDimension(
        key="secondary_creation",
        label="Secondary creation",
        side=SkillSide.OFFENSE,
        definition="Creation produced without being the primary initiator.",
        available=False,
        unavailable_reason=(
            "Assist rate cannot distinguish a first option from a second. Needs on/off "
            "or play-type splits. Pivot measures this as a ROSTER need, not a player skill "
            "— see domain.needs."
        ),
    ),
    SkillDimension(
        key="off_ball_movement",
        label="Off-ball movement",
        side=SkillSide.OFFENSE,
        definition="Value generated by moving without the ball.",
        available=False,
        unavailable_reason=_TRACKING,
    ),
    SkillDimension(
        key="transition_offense",
        label="Transition offense",
        side=SkillSide.OFFENSE,
        definition="Production in the open floor.",
        available=False,
        unavailable_reason=_PLAY_TYPE,
    ),
    SkillDimension(
        key="offensive_rebounding",
        label="Offensive rebounding",
        side=SkillSide.OFFENSE,
        definition="Share of a team's own misses recovered.",
        available=False,
        unavailable_reason=(
            "Offensive rebound rate is ingested but is currently folded into the single "
            "`rebounding` dimension. Splitting it is an R9 change, not a data gap."
        ),
    ),
    SkillDimension(
        key="point_of_attack_defense",
        label="Point-of-attack defense",
        side=SkillSide.DEFENSE,
        definition="Ability to contain a ball handler on the perimeter.",
        available=False,
        unavailable_reason=(
            "Built and then WITHDRAWN in R4-2. A steals-led composite scored worse than "
            "the steals proxy it replaced on its own pre-registered class (0.630 vs 0.611), "
            "because gambling for steals is what a box score records and staying in front "
            "of a ball handler is not. Pivot measures this as a team need with no player-side "
            "answer attached."
        ),
    ),
    SkillDimension(
        key="screen_navigation",
        label="Screen navigation",
        side=SkillSide.DEFENSE,
        definition="Getting over, under and through screens without conceding an advantage.",
        available=False,
        unavailable_reason=_TRACKING,
    ),
    SkillDimension(
        key="switchability",
        label="Switchability",
        side=SkillSide.DEFENSE,
        definition="How many positional archetypes a player can guard without cost.",
        available=False,
        unavailable_reason=(
            "Needs matchup data. Deriving it from height and steals would rate the same "
            "players the withdrawn point-of-attack composite rated, for the same reason."
        ),
    ),
    SkillDimension(
        key="help_defense",
        label="Help defense",
        side=SkillSide.DEFENSE,
        definition="Rotations and support away from the ball.",
        available=False,
        unavailable_reason=_TRACKING,
    ),
    SkillDimension(
        key="disruption",
        label="Disruption",
        side=SkillSide.DEFENSE,
        definition="Deflections, steals and forced turnovers as an event rate.",
        available=False,
        unavailable_reason=(
            "Steal rate is ingested but is currently folded into `team_defense`. "
            "Surfacing it alone would re-create the proxy R4-2 withdrew unless it is "
            "labelled as an event rate rather than as defensive quality."
        ),
    ),
    SkillDimension(
        key="positional_versatility",
        label="Positional versatility",
        side=SkillSide.DEFENSE,
        definition="Range of positions a player can defend across a season.",
        available=False,
        unavailable_reason="Needs matchup data. No lineup or assignment source is ingested.",
    ),
)

DECLARED_DIMENSIONS: tuple[SkillDimension, ...] = _MEASURED + _DECLARED_ONLY

BY_KEY: dict[str, SkillDimension] = {d.key: d for d in DECLARED_DIMENSIONS}

MEASURED_KEYS: tuple[str, ...] = tuple(d.key for d in _MEASURED)
UNAVAILABLE_KEYS: tuple[str, ...] = tuple(d.key for d in _DECLARED_ONLY)


def describe(key: str) -> SkillDimension | None:
    return BY_KEY.get(key)


def _check_vocabulary_agrees() -> None:
    """`SKILL_KEYS` and the measured dimension records must not drift apart.

    They are two statements of one fact: SKILL_KEYS is what the cache fingerprint and
    every existing consumer read, the records are what the product explains. A dimension
    documented as available but absent from SKILL_KEYS would be described to a user and
    never computed.
    """
    if set(MEASURED_KEYS) != set(SKILL_KEYS):
        missing = sorted(set(SKILL_KEYS) - set(MEASURED_KEYS))
        extra = sorted(set(MEASURED_KEYS) - set(SKILL_KEYS))
        raise RuntimeError(
            f"skill vocabulary drift — undocumented: {missing}, not computed: {extra}"
        )


_check_vocabulary_agrees()


__all__ = [
    "BY_KEY",
    "DECLARED_DIMENSIONS",
    "MEASURED_KEYS",
    "SKILL_KEYS",
    "UNAVAILABLE_KEYS",
    "SkillDimension",
    "SkillSide",
    "describe",
]
