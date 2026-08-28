"""Roster state: the thing a move changes.

Today's evaluation pipeline has no roster-state object. It works on ad-hoc dicts
(`{"player_id", "from_team_id", "to_team_id"}`) plus a `list[PlayerCard]`, and the only
genuine before/after pair in the system — the rotation allocation — is smuggled through the
evaluation response under a private `_rotations` key and popped by the caller
(`services/evaluation.py`). That works for one shape of question ("what does this trade do?")
and cannot express the others Pivot needs ("what does waiving him do?", "what does their
counter-move do to us?").

`RosterState` is the missing noun. It is a **membership snapshot**, deliberately thin:

    who is on this roster, for this season, with what minutes and what archetype

and nothing else. It carries no needs, no profile, no fit and no projection, because those
are *computed from* a roster state by the intelligence layer and would go stale the moment
the state changed. A state that cached its own diagnosis would be a state that could lie.

The transition is in `domain.moves`. Together they give R13 a place to stand:

    RosterState A  --Move-->  RosterState B

and, because a state names its team and a `LeagueState` holds many, the same structure
expresses the multi-team question without being rebuilt:

    LeagueState A  --Move-->  LeagueState B  --opponent Move-->  LeagueState C

Nothing here simulates anything. This module is data and the two operations that keep it
consistent.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field, replace

from .archetypes import ArchetypeMembership


@dataclass(frozen=True, slots=True)
class RosterSlot:
    """One player's place on a roster.

    `minutes` is the allocated rotation minutes the projection produced, not a season
    average — `None` where no allocation has been made. `tei` is likewise `None` rather
    than 0.0 for a player with no impact estimate: the repository's standing rule is that
    a missing estimate is an absence, never a zero, and a slot is where that rule is
    easiest to break.
    """

    player_id: str
    player_name: str = ""
    minutes: float | None = None
    tei: float | None = None
    archetypes: tuple[ArchetypeMembership, ...] = ()
    #: True while the player counts against roster limits but is not expected to play.
    two_way: bool = False

    @property
    def primary_archetype(self) -> str | None:
        for a in self.archetypes:
            if a.primary:
                return a.key
        return self.archetypes[0].key if self.archetypes else None

    @property
    def has_impact_estimate(self) -> bool:
        return self.tei is not None


@dataclass(frozen=True, slots=True)
class RosterState:
    """Who is on one team's roster at one point in a scenario.

    Immutable. Every transition returns a new state, so a before/after pair is two objects
    that can both be inspected rather than one object and a memory of what it used to be.
    """

    team_id: str
    season: str
    slots: tuple[RosterSlot, ...] = ()
    #: Free-text label for how this state came about ("current", "after Pivot trade #3").
    label: str = "current"

    # ------------------------------------------------------------------ queries

    def __len__(self) -> int:
        return len(self.slots)

    def __iter__(self):
        return iter(self.slots)

    @property
    def player_ids(self) -> frozenset[str]:
        return frozenset(s.player_id for s in self.slots)

    def get(self, player_id: str) -> RosterSlot | None:
        for s in self.slots:
            if s.player_id == player_id:
                return s
        return None

    def contains(self, player_id: str) -> bool:
        return any(s.player_id == player_id for s in self.slots)

    @property
    def players_without_impact_estimate(self) -> tuple[RosterSlot, ...]:
        """Named, not dropped and not filled with a league-average stand-in.

        These players are left out of a projection and still counted against roster
        limits — the treatment the adversarial battery asserts.
        """
        return tuple(s for s in self.slots if not s.has_impact_estimate)

    def archetype_counts(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for slot in self.slots:
            key = slot.primary_archetype
            if key:
                counts[key] = counts.get(key, 0) + 1
        return counts

    # --------------------------------------------------------------- transitions
    # Membership only. Nothing here reallocates minutes or re-derives an archetype —
    # that is the intelligence layer's job, and doing it here would bury a basketball
    # model inside a data structure.

    def with_added(self, slot: RosterSlot) -> RosterState:
        if self.contains(slot.player_id):
            raise ValueError(f"{slot.player_id} is already on roster {self.team_id}")
        return replace(self, slots=(*self.slots, slot))

    def with_removed(self, player_id: str) -> RosterState:
        if not self.contains(player_id):
            raise ValueError(f"{player_id} is not on roster {self.team_id}")
        return replace(self, slots=tuple(s for s in self.slots if s.player_id != player_id))

    def relabelled(self, label: str) -> RosterState:
        return replace(self, label=label)


@dataclass(frozen=True, slots=True)
class LeagueState:
    """Several rosters at one point in a scenario.

    This exists so multi-team reasoning is not precluded later by a shape chosen now. A
    single-team question is a `LeagueState` with one entry, and the trade evaluator's
    two- and three-team deals are already the multi-entry case — so the generalisation
    costs nothing today and is the only thing that makes §11's "what does this force the
    other organisation to do?" expressible at all.

    It does **not** hold all thirty rosters. Building a league-wide state is an expensive
    query and no current caller needs one; a scenario holds only the teams its moves touch.
    """

    season: str
    rosters: dict[str, RosterState] = field(default_factory=dict)
    label: str = "current"

    def team(self, team_id: str) -> RosterState | None:
        return self.rosters.get(team_id)

    @property
    def team_ids(self) -> tuple[str, ...]:
        return tuple(sorted(self.rosters))

    def with_roster(self, state: RosterState) -> LeagueState:
        merged = dict(self.rosters)
        merged[state.team_id] = state
        return replace(self, rosters=merged)

    @classmethod
    def of(cls, season: str, states: Iterable[RosterState], label: str = "current") -> LeagueState:
        return cls(season=season, rosters={s.team_id: s for s in states}, label=label)


__all__ = ["LeagueState", "RosterSlot", "RosterState"]
