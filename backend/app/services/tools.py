"""The Copilot tool boundary — what a future Pivot AI would be allowed to call.

**There is no LLM in this module and there is not meant to be one.** The architectural
position it exists to enforce is a single sentence:

    The assistant is not the analytical engine.

    USER LANGUAGE -> COPILOT -> STRUCTURED TOOL CALL -> PIVOT ENGINES
                              -> RESULT + EVIDENCE -> COPILOT EXPLANATION

A language model that answers "is this a good trade?" from its own weights is a different
product from one that calls `simulate_trade`, receives a composite with its components,
its exclusions and its wins band, and then puts that into a sentence. The first invents;
the second explains. This registry is the seam that makes the second the only option a
future implementation has, because the only basketball facts reachable through it are the
ones the engines produced.

Two properties are load-bearing:

**Every tool is read-only.** Nothing here writes, and `ToolSpec.readonly` is asserted, so a
Copilot cannot save a trade, change a mandate or trigger an ingestion by talking about one.
Write actions stay behind the API's explicit endpoints where a person performs them.

**A tool that does not exist says so.** The registry lists the full vocabulary from the
Pivot brief, including the tools that cannot be honestly implemented yet, each with the
reason — the same discipline `domain.skills` applies to unmeasurable dimensions. A Copilot
built against this registry discovers that Pivot cannot simulate a signing; it does not
discover a function that quietly returns something adjacent.

Nothing depends on this module yet. It is a declaration and a test surface, and it is here
so R14 is a wiring job rather than an architecture argument.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.orm import Session

from app.services.intelligence import IntelligenceService


@dataclass(frozen=True, slots=True)
class ToolSpec:
    """One callable a Copilot may invoke, described well enough to be exposed as a tool.

    `parameters` is a JSON Schema object, which is the shape every tool-calling API expects.
    `handler` is None exactly when `available` is False.
    """

    name: str
    summary: str
    parameters: dict[str, Any]
    available: bool
    #: Why the tool cannot be offered. Non-empty exactly when `available` is False.
    unavailable_reason: str = ""
    handler: Callable[..., Any] | None = None
    readonly: bool = True
    #: What a caller must tell the user alongside the result. Not decoration — these are the
    #: disclosures that stop a correct number from being read as a broader claim.
    result_caveats: tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if self.available and self.handler is None:
            raise ValueError(f"{self.name}: an available tool must have a handler")
        if not self.available:
            if self.handler is not None:
                raise ValueError(f"{self.name}: an unavailable tool must not have a handler")
            if not self.unavailable_reason:
                raise ValueError(f"{self.name}: an unavailable tool must state why")
        if not self.readonly:
            raise ValueError(
                f"{self.name}: the Copilot boundary is read-only — a write tool would let a "
                "conversation change state a person never confirmed"
            )

    def as_tool_definition(self) -> dict[str, Any]:
        """The shape a tool-calling API wants. Unavailable tools are not offered."""
        if not self.available:
            raise ValueError(f"{self.name} is not available: {self.unavailable_reason}")
        return {
            "name": self.name,
            "description": self.summary,
            "input_schema": self.parameters,
        }


def _obj(props: dict[str, Any], required: list[str]) -> dict[str, Any]:
    return {
        "type": "object",
        "properties": props,
        "required": required,
        "additionalProperties": False,
    }


_PLAYER = {"type": "string", "description": "Pivot player id."}
_TEAM = {"type": "string", "description": "Pivot team id."}


def build_registry(db: Session) -> dict[str, ToolSpec]:
    """The tools available against one database session.

    Bound to a session rather than global because every handler reads one, and a registry
    that closed over a long-lived session would outlive the request that owns it.
    """
    intel = IntelligenceService(db)

    specs = [
        ToolSpec(
            name="get_vocabulary",
            summary=(
                "List the basketball dimensions, archetypes and roster needs Pivot measures, "
                "and the ones it has declared it cannot measure, each with the reason."
            ),
            parameters=_obj({}, []),
            available=True,
            handler=lambda: IntelligenceService.vocabulary(),
            result_caveats=(
                "Dimensions with available=false are not gaps to fill in conversationally. "
                "Pivot has no value for them and neither does the assistant.",
            ),
        ),
        ToolSpec(
            name="get_player_profile",
            summary=(
                "One player's measured capabilities: skill percentiles, archetype membership "
                "and impact estimate, each with its method, evidence class and limitations."
            ),
            parameters=_obj({"player_id": _PLAYER}, ["player_id"]),
            available=True,
            handler=intel.player_intelligence,
            result_caveats=(
                "Skill values are league percentiles, not ratings out of 100.",
                "A player whose impact is unavailable has no estimate at all — he must not be "
                "described as average.",
            ),
        ),
        ToolSpec(
            name="get_team_profile",
            summary=(
                "One roster's contents: size, skill coverage across the rotation, archetype "
                "distribution, and its needs classified into strengths and weaknesses."
            ),
            parameters=_obj({"team_id": _TEAM}, ["team_id"]),
            available=True,
            handler=intel.team_profile,
            result_caveats=(
                "Strengths and weaknesses are disjoint by construction; a need appearing in "
                "neither list simply did not clear either threshold.",
                "A need with a non-empty unaddressable_reason has no player-side answer, and "
                "the assistant must not propose one.",
            ),
        ),
        ToolSpec(
            name="calculate_fit",
            summary=(
                "How a player would fit a specific roster, scored 0-100 where 50 means the "
                "addition changes nothing on this axis. Requires a team: there is no "
                "team-free fit score."
            ),
            parameters=_obj({"player_id": _PLAYER, "team_id": _TEAM}, ["player_id", "team_id"]),
            available=True,
            handler=intel.player_team_fit,
            result_caveats=(
                "Fit measures the direction of a change, not its size. A player who answers a "
                "need scores well whether he plays eight minutes or thirty-two, so fit must "
                "never be quoted as an overall verdict on a player.",
                "When available=false the fit was withheld for a stated reason. Report the "
                "reason; do not substitute a judgement.",
            ),
        ),
        # ------------------------------------------------------------------ not yet
        ToolSpec(
            name="get_roster",
            summary="The players on a team's roster, with minutes and contract status.",
            parameters=_obj({"team_id": _TEAM}, ["team_id"]),
            available=False,
            unavailable_reason=(
                "The roster read is assembled inline in the teams router "
                "(api/v1/teams.py::get_roster) rather than in a service, so there is no "
                "function to expose. Extracting it is an R8 task."
            ),
        ),
        ToolSpec(
            name="search_players",
            summary="Find players by name, team, archetype or the need they address.",
            parameters=_obj(
                {
                    "query": {"type": "string"},
                    "team_id": _TEAM,
                    "limit": {"type": "integer", "minimum": 1, "maximum": 50},
                },
                [],
            ),
            available=False,
            unavailable_reason=(
                "Player search exists as a router handler (api/v1/players.py::list_players) "
                "with its filtering inline. Searching by archetype or by need — the two a "
                "Copilot would actually want — is not implemented at all."
            ),
        ),
        ToolSpec(
            name="compare_players",
            summary="Compare two to four players across the measured dimensions.",
            parameters=_obj(
                {"player_ids": {"type": "array", "items": _PLAYER, "minItems": 2, "maxItems": 4}},
                ["player_ids"],
            ),
            available=False,
            unavailable_reason=(
                "Player comparison is assembled in the browser from several endpoints "
                "(frontend/app/player-explorer). No server-side comparison exists, so there "
                "is nothing a tool could call that would produce the comparison a user sees."
            ),
        ),
        ToolSpec(
            name="simulate_trade",
            summary="Evaluate a proposed trade for every team involved.",
            parameters=_obj(
                {
                    "teams": {"type": "array", "items": _TEAM, "minItems": 2, "maxItems": 3},
                    "assets": {"type": "array", "items": {"type": "object"}},
                },
                ["teams", "assets"],
            ),
            available=False,
            unavailable_reason=(
                "The evaluation composite has no single service entry point: the sequence "
                "build_trade_context -> TradeLegalityEngine().evaluate -> per-team "
                "evaluate_for_team is duplicated across four API handlers. A tool must call "
                "one function, not reproduce an orchestration. Consolidating it is the "
                "highest-value R8 refactor."
            ),
        ),
        ToolSpec(
            name="simulate_addition",
            summary="What adding a player to a roster would change.",
            parameters=_obj({"player_id": _PLAYER, "team_id": _TEAM}, ["player_id", "team_id"]),
            available=False,
            unavailable_reason=(
                "Pivot can price an addition's FIT (see calculate_fit) but cannot yet run the "
                "full before/after — rotation, projection, roster shape — for a move that is "
                "not a trade. domain.moves defines the transition; no engine consumes it yet. "
                "That is R13."
            ),
        ),
        ToolSpec(
            name="simulate_departure",
            summary="What losing a player would change.",
            parameters=_obj({"player_id": _PLAYER, "team_id": _TEAM}, ["player_id", "team_id"]),
            available=False,
            unavailable_reason=(
                "Same as simulate_addition: the transition exists in domain.moves, the "
                "recomputation does not. Note the modelling constraint it must respect — a "
                "departure's minutes go unfilled at replacement level, never to the next man up."
            ),
        ),
        ToolSpec(
            name="compare_scenarios",
            summary="Rank saved scenarios under a set of priorities.",
            parameters=_obj(
                {"trade_ids": {"type": "array", "items": {"type": "string"}, "minItems": 2}},
                ["trade_ids"],
            ),
            available=False,
            unavailable_reason=(
                "Scenario comparison — the Pareto frontier and rank stability — is computed "
                "partly in the comparisons router and partly in the browser "
                "(frontend/app/strategy-lab). Neither half is callable on its own."
            ),
        ),
    ]

    return {spec.name: spec for spec in specs}


def available_tools(db: Session) -> list[dict[str, Any]]:
    """Tool definitions a Copilot may be offered, in the shape tool-calling APIs expect."""
    return [s.as_tool_definition() for s in build_registry(db).values() if s.available]


def unavailable_tools(db: Session) -> list[dict[str, str]]:
    """The declared-but-unbuilt tools and why, so the gap is legible rather than silent."""
    return [
        {"name": s.name, "summary": s.summary, "reason": s.unavailable_reason}
        for s in build_registry(db).values()
        if not s.available
    ]


__all__ = ["ToolSpec", "available_tools", "build_registry", "unavailable_tools"]
