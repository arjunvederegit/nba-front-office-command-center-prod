"""The archetype framework: what kind of basketball player somebody is.

Pivot's position is that a position is not an archetype. "Power forward" describes where a
player once stood; "stretch big" describes what he does to a defense. The product reasons
in the second vocabulary.

**Most of that vocabulary already exists.** R4-3 replaced a k-means clustering with a
deterministic size-first rule chain producing fourteen functional labels, and those labels
are already archetypes in everything but name — `3&D wing`, `movement shooter`,
`stretch big`, `playmaking big`, `connector wing`. What the shipped system does *not* do is
let a player hold more than one, or attach a confidence to the one he holds:
`player_archetypes` carries a unique constraint on (player, season), so membership is
strictly 1:1.

This module is the framework that removes that ceiling without disturbing what works:

- `ROLE_ID` is the canonical frozen id map, moved here so the domain owns the vocabulary.
  `analytics.archetypes` re-exports it, so every existing consumer and every persisted
  `role_id` keeps its meaning. **Append only — never reorder or renumber.**
- `ArchetypeDefinition` describes each label in product language, with the family it
  belongs to.
- `ArchetypeMembership` is the forward-looking shape: a player may hold several, each with
  a weight and a confidence. Nothing computes a multi-membership today; the deterministic
  chain still returns exactly one, and `single_membership` wraps it faithfully rather than
  pretending otherwise.

The honest boundary: a membership produced by the shipped chain is `Evidence.INFERRED` at
`Confidence.MEASURED` — the chain is a total, reproducible function of one player's row
(1.78 % label churn under a 10 % resample, against k-means' 65.7 %), but nothing validates
that its labels are the *right* labels, because no ground-truth archetype set exists.
Saying so is the difference between a taxonomy and a claim.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from .evidence import Confidence, Evidence


class ArchetypeFamily(StrEnum):
    """The size band the chain gates on before any skill is considered.

    Size first is deliberate and measured: a creation-first ordering — the intuitive one,
    and effectively what k-means used — labelled Wembanyama a secondary creator.
    """

    GUARD = "guard"
    WING = "wing"
    BIG = "big"
    UNCLASSIFIED = "unclassified"


UNCLASSIFIED_SIZE = "unclassified (no listed height)"
UNCLASSIFIED_STATS = "unclassified (insufficient stats)"

#: Frozen id map. **Never reorder or renumber**: `player_archetypes.role_id` is persisted
#: per player-season, so renumbering silently rewrites the meaning of every historical row.
#: Append only.
ROLE_ID: dict[str, int] = {
    "lead guard": 0,
    "scoring guard": 1,
    "point-of-attack guard": 2,
    "off-ball guard": 3,
    "primary wing creator": 4,
    "3&D wing": 5,
    "movement shooter": 6,
    "slashing wing": 7,
    "connector wing": 8,
    "stretch big": 9,
    "rim-protecting big": 10,
    "playmaking big": 11,
    "glass-cleaning big": 12,
    "finishing big": 13,
    UNCLASSIFIED_SIZE: 90,
    UNCLASSIFIED_STATS: 91,
}

ROLE_ORDER: list[str] = [r for r, _ in sorted(ROLE_ID.items(), key=lambda kv: kv[1])]
REAL_ROLES: list[str] = [r for r in ROLE_ORDER if not r.startswith("unclassified")]


@dataclass(frozen=True, slots=True)
class ArchetypeDefinition:
    """One functional archetype, in the language a front office would use."""

    key: str
    label: str
    family: ArchetypeFamily
    definition: str
    #: What a roster gains by holding one.
    contributes: tuple[str, ...] = ()

    @property
    def role_id(self) -> int:
        return ROLE_ID[self.key]


_D = ArchetypeDefinition
CATALOG: tuple[ArchetypeDefinition, ...] = (
    _D("lead guard", "Lead guard", ArchetypeFamily.GUARD,
       "Runs the offense with the ball in his hands.",
       ("creation", "playmaking")),
    _D("scoring guard", "Scoring guard", ArchetypeFamily.GUARD,
       "Guard-sized primary scorer who creates his own shot.",
       ("scoring", "shot creation")),
    _D("point-of-attack guard", "Point-of-attack guard", ArchetypeFamily.GUARD,
       "Guard whose value is pressuring the ball rather than holding it.",
       ("perimeter defense",)),
    _D("off-ball guard", "Off-ball guard", ArchetypeFamily.GUARD,
       "Guard who plays off a primary creator and spaces the floor.",
       ("shooting", "spacing")),
    _D("primary wing creator", "Primary wing creator", ArchetypeFamily.WING,
       "Wing-sized initiator — the point forward.",
       ("creation", "size", "scoring")),
    _D("3&D wing", "3&D wing", ArchetypeFamily.WING,
       "Spaces the floor and defends on the perimeter without needing the ball.",
       ("shooting", "perimeter defense")),
    _D("movement shooter", "Movement shooter", ArchetypeFamily.WING,
       "Generates shooting gravity by moving off the ball.",
       ("shooting", "spacing")),
    _D("slashing wing", "Slashing wing", ArchetypeFamily.WING,
       "Attacks downhill and pressures the rim.",
       ("rim pressure", "scoring")),
    _D("connector wing", "Connector wing", ArchetypeFamily.WING,
       "Two-way glue: passes, defends, keeps possessions alive.",
       ("versatility", "ball movement")),
    _D("stretch big", "Stretch big", ArchetypeFamily.BIG,
       "Big who pulls a rim protector away from the basket.",
       ("shooting", "spacing")),
    _D("rim-protecting big", "Interior anchor", ArchetypeFamily.BIG,
       "Anchors the defense at the basket.",
       ("rim protection", "defensive rebounding")),
    _D("playmaking big", "Playmaking big", ArchetypeFamily.BIG,
       "Offensive hub from the elbow or the post.",
       ("creation", "size")),
    _D("glass-cleaning big", "Glass-cleaning big", ArchetypeFamily.BIG,
       "Wins possessions on the boards.",
       ("rebounding",)),
    _D("finishing big", "Rim runner", ArchetypeFamily.BIG,
       "Scores at the rim off rolls, cuts and offensive rebounds.",
       ("finishing", "rim pressure")),
    _D(UNCLASSIFIED_SIZE, "Unclassified — no listed height", ArchetypeFamily.UNCLASSIFIED,
       "No listed height, so the size gate the chain starts from cannot be applied. "
       "Deliberately not filled with a league median."),
    _D(UNCLASSIFIED_STATS, "Unclassified — insufficient stats", ArchetypeFamily.UNCLASSIFIED,
       "Too many discriminating statistics are missing to place this player honestly."),
)

BY_KEY: dict[str, ArchetypeDefinition] = {a.key: a for a in CATALOG}


@dataclass(frozen=True, slots=True)
class ArchetypeMembership:
    """A player's claim on one archetype.

    `weight` is the share of the player's identity this archetype accounts for. The shipped
    deterministic chain returns exactly one label, so today every membership carries
    `weight=1.0` and `primary=True`; the field exists so a future multi-label engine (R10)
    has somewhere to put a second claim without a schema argument.

    A membership is an INFERENCE. The chain is reproducible and stable, which is why the
    confidence is `MEASURED` rather than `HEURISTIC` — but no ground-truth archetype set
    exists to validate the labels against, so it is never `VALIDATED`.
    """

    key: str
    weight: float = 1.0
    primary: bool = True
    evidence: Evidence = Evidence.INFERRED
    confidence: Confidence = Confidence.MEASURED
    method: str = "Deterministic size-first rule chain over league percentile cut points (R4-3)."

    @property
    def definition(self) -> ArchetypeDefinition | None:
        return BY_KEY.get(self.key)

    @property
    def label(self) -> str:
        d = self.definition
        return d.label if d else self.key

    @property
    def unclassified(self) -> bool:
        return self.key.startswith("unclassified")

    def as_dict(self) -> dict:
        d = self.definition
        return {
            "key": self.key,
            "label": self.label,
            "family": d.family.value if d else None,
            "definition": d.definition if d else "",
            "weight": self.weight,
            "primary": self.primary,
            "evidence": self.evidence.value,
            "confidence": self.confidence.value,
            "method": self.method,
        }


def single_membership(role: str) -> list[ArchetypeMembership]:
    """Wrap the one label the shipped chain returns.

    Faithful, not aspirational: it returns a one-element list because the engine produces
    one label, and the list shape exists so callers are already written against the plural
    form when R10 makes it plural.
    """
    if not role:
        return []
    return [ArchetypeMembership(key=role, weight=1.0, primary=True)]


def describe(key: str) -> ArchetypeDefinition | None:
    return BY_KEY.get(key)


def _check_catalog_covers_ids() -> None:
    """Every persisted role id must have a product-language definition."""
    missing = sorted(set(ROLE_ID) - set(BY_KEY))
    if missing:
        raise RuntimeError(f"archetypes with a persisted id but no definition: {missing}")


_check_catalog_covers_ids()


__all__ = [
    "BY_KEY",
    "CATALOG",
    "REAL_ROLES",
    "ROLE_ID",
    "ROLE_ORDER",
    "UNCLASSIFIED_SIZE",
    "UNCLASSIFIED_STATS",
    "ArchetypeDefinition",
    "ArchetypeFamily",
    "ArchetypeMembership",
    "describe",
    "single_membership",
]
