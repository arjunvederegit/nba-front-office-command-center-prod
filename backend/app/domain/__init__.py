"""Pivot's canonical basketball domain.

This package is the vocabulary layer. It sits below the intelligence layer and above the
data layer, and it holds the nouns the whole product reasons in:

    domain/evidence.py    the OBSERVED -> DERIVED -> INFERRED ladder, and the Measurement
                          envelope that keeps a number attached to what produced it
    domain/skills.py      the nine measured skill dimensions, and the dimensions Pivot
                          declares it cannot yet see
    domain/archetypes.py  the fourteen functional archetypes, and the multi-membership
                          shape R10 will grow into
    domain/needs.py       the eleven roster needs, and which of them no player skill claims
                          to address
    domain/roster.py      RosterState / LeagueState — the thing a move changes
    domain/moves.py       Move / apply / ScenarioStep — the transition, membership only
    domain/mandate.py     TeamMandate and the strategy weight table; also where the
                          Scenario name collision is settled

Three rules hold this package together.

**It computes nothing.** No formula, no model, no threshold applied to data. Percentiles,
skill vectors, archetype assignment, need severities and every fitted coefficient stay in
`app.analytics`, which is where the data is. What lives here is what those things *mean*.

**It imports nothing from above it.** No SQLAlchemy, no FastAPI, no pandas, no
`app.analytics`, no `app.services`. The dependency arrow points one way, which is what
makes the vocabulary testable without a database and reusable by the ingestion layer, the
engines and the API alike.

**It is the single source of truth for the vocabulary it owns.** `analytics.archetypes`,
`analytics.needs` and `services.evaluation` re-export `SKILL_KEYS`, `ROLE_ID`,
`NEED_TO_SKILL`, `UNADDRESSABLE_NEEDS` and `DEFAULT_WEIGHTS` from here rather than
declaring their own. Every existing import keeps working, every persisted `role_id` keeps
its meaning, and `skill_schema_fingerprint()` is unchanged because it hashes the contents
of `SKILL_KEYS`, not its address.
"""

from .archetypes import (
    ROLE_ID,
    ArchetypeDefinition,
    ArchetypeFamily,
    ArchetypeMembership,
    single_membership,
)
from .archetypes import (
    ArchetypeMembership as Archetype,
)
from .evidence import Confidence, Evidence, Measurement
from .mandate import (
    COMPONENT_KEYS,
    COMPONENT_LABELS,
    STRATEGY_WEIGHTS,
    Strategy,
    TeamMandate,
    weights_for,
)
from .moves import Move, MoveKind, PlayerMovement, ScenarioStep, apply, replay
from .needs import (
    NEED_KEYS,
    NEED_TO_SKILL,
    UNADDRESSABLE_NEEDS,
    NeedDefinition,
    NeedSource,
)
from .roster import LeagueState, RosterSlot, RosterState
from .skills import (
    DECLARED_DIMENSIONS,
    MEASURED_KEYS,
    SKILL_KEYS,
    UNAVAILABLE_KEYS,
    SkillDimension,
    SkillSide,
)

__all__ = [
    "COMPONENT_KEYS",
    "COMPONENT_LABELS",
    "DECLARED_DIMENSIONS",
    "MEASURED_KEYS",
    "NEED_KEYS",
    "NEED_TO_SKILL",
    "ROLE_ID",
    "SKILL_KEYS",
    "STRATEGY_WEIGHTS",
    "UNADDRESSABLE_NEEDS",
    "UNAVAILABLE_KEYS",
    "Archetype",
    "ArchetypeDefinition",
    "ArchetypeFamily",
    "ArchetypeMembership",
    "Confidence",
    "Evidence",
    "LeagueState",
    "Measurement",
    "Move",
    "MoveKind",
    "NeedDefinition",
    "NeedSource",
    "PlayerMovement",
    "RosterSlot",
    "RosterState",
    "ScenarioStep",
    "SkillDimension",
    "SkillSide",
    "Strategy",
    "TeamMandate",
    "apply",
    "replay",
    "single_membership",
    "weights_for",
]
