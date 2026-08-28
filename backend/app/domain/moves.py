"""Moves: the generic transition Pivot's scenario layer is built on.

The shipped product can answer one question — "what does this trade do?" — and answers it
well, through a pipeline that is trade-shaped end to end. Every other question a front
office asks has the same structure and none of them fit:

    sign a free agent · claim a waiver · draft a player · lose a player in free agency ·
    lose a player to injury · change the rotation

A `Move` is that structure, named once. Each kind states which roster gains and which
loses, and `apply` performs the membership change against a `LeagueState`. That is all it
does, and the restraint is deliberate:

**`apply` changes who is on a roster. It does not recompute what that means.**

Minutes are not reallocated, archetypes are not reassigned, needs are not re-derived, no
projection is run and no legality is checked. Those are the intelligence layer's job, and
folding them in here would put a basketball model inside a data structure and make the
transition impossible to test on its own. The scenario service composes the two:

    state_b = apply(state_a, move)          # this module: membership
    profile_b = team_profile(state_b)       # intelligence layer: meaning

Legality in particular stays where it is. `cba.engine.TradeLegalityEngine` is the authority
on whether a trade may happen, it returns the four-state verdict, and a `TradeMove` that
`apply` accepts may still be `verified_illegal`. Making `apply` refuse illegal moves would
quietly turn a rules question into a data-structure question and lose the distinction
between "cannot" and "did not".

Branching is not built here either, but it is not precluded: `apply` is a pure function
from one state to another, so a branch is a second call on the same input, and
`ScenarioStep` carries the parent pointer that a tree needs.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

from .roster import LeagueState, RosterSlot


class MoveKind(StrEnum):
    TRADE = "trade"
    SIGNING = "signing"
    WAIVER = "waiver"
    DRAFT = "draft"
    DEPARTURE = "departure"
    INJURY = "injury"
    ROTATION = "rotation"


@dataclass(frozen=True, slots=True)
class PlayerMovement:
    """One player changing hands.

    `from_team_id` is None for a player entering the league or signing from outside it;
    `to_team_id` is None for a player leaving it. A trade has both on every leg.
    """

    player_id: str
    from_team_id: str | None
    to_team_id: str | None
    slot: RosterSlot | None = None

    def __post_init__(self) -> None:
        if self.from_team_id is None and self.to_team_id is None:
            raise ValueError(f"{self.player_id}: a movement must have a source or a destination")
        if self.to_team_id is not None and self.slot is None:
            raise ValueError(
                f"{self.player_id}: a movement onto a roster must carry the slot to add"
            )


@dataclass(frozen=True, slots=True)
class Move:
    """A single change to league state.

    One shape covers every kind because every kind is the same operation on membership —
    what differs is the rules that govern it and the consequences that follow, and both of
    those live outside this module. `kind` is carried so the layers that *do* differ
    (legality, cap treatment, explanation copy) can branch on it without re-deriving it
    from the movement pattern.
    """

    kind: MoveKind
    movements: tuple[PlayerMovement, ...] = ()
    #: Teams the move involves even when no player moves between them (a rotation change,
    #: a pick-only trade). Derived from the movements when not given.
    team_ids: tuple[str, ...] = ()
    label: str = ""

    def __post_init__(self) -> None:
        if not self.team_ids:
            teams = {t for m in self.movements for t in (m.from_team_id, m.to_team_id) if t}
            object.__setattr__(self, "team_ids", tuple(sorted(teams)))

    @property
    def multi_team(self) -> bool:
        return len(self.team_ids) > 2

    def describe(self) -> str:
        return self.label or f"{self.kind.value} involving {len(self.team_ids)} team(s)"

    # ---------------------------------------------------------------- constructors

    @classmethod
    def trade(cls, movements: tuple[PlayerMovement, ...], label: str = "") -> Move:
        return cls(kind=MoveKind.TRADE, movements=movements, label=label)

    @classmethod
    def signing(cls, player_id: str, to_team_id: str, slot: RosterSlot, label: str = "") -> Move:
        return cls(
            kind=MoveKind.SIGNING,
            movements=(PlayerMovement(player_id, None, to_team_id, slot),),
            label=label,
        )

    @classmethod
    def departure(cls, player_id: str, from_team_id: str, label: str = "") -> Move:
        """A player leaving the roster with nobody arriving.

        The minutes he leaves behind go **unfilled at replacement level** when the
        projection runs — R5.5 measured that the signal share of served TEI outside a
        team's top ten is 0.000, so promoting the next man up would invent production.
        That treatment belongs to the projection, not to this transition; it is noted here
        because a departure is where the temptation to invent it lives.
        """
        return cls(
            kind=MoveKind.DEPARTURE,
            movements=(PlayerMovement(player_id, from_team_id, None),),
            label=label,
        )

    @classmethod
    def waiver(cls, player_id: str, from_team_id: str, label: str = "") -> Move:
        return cls(
            kind=MoveKind.WAIVER,
            movements=(PlayerMovement(player_id, from_team_id, None),),
            label=label,
        )

    @classmethod
    def draft(cls, player_id: str, to_team_id: str, slot: RosterSlot, label: str = "") -> Move:
        return cls(
            kind=MoveKind.DRAFT,
            movements=(PlayerMovement(player_id, None, to_team_id, slot),),
            label=label,
        )

    @classmethod
    def injury(cls, player_id: str, team_id: str, label: str = "") -> Move:
        """Availability, not membership.

        An injured player stays on the roster and stays counted against roster limits. The
        move exists so a scenario can express "what if he is out" without deleting him,
        and `apply` therefore leaves membership untouched — the availability discount is
        the projection's business.
        """
        return cls(kind=MoveKind.INJURY, movements=(), team_ids=(team_id,), label=label)

    @classmethod
    def rotation(cls, team_id: str, label: str = "") -> Move:
        return cls(kind=MoveKind.ROTATION, movements=(), team_ids=(team_id,), label=label)


def apply(state: LeagueState, move: Move, label: str = "") -> LeagueState:
    """Return the league state that results from `move`. Membership only.

    Pure: `state` is not mutated, and applying the same move to the same state twice gives
    two equal results. That is what makes branching a matter of calling this twice.

    Raises `ValueError` when the move is inconsistent with the state it is applied to — a
    player traded from a roster he is not on, or onto one he is already on. This is a
    consistency check, **not** a legality check: `cba.engine` decides whether a move is
    permitted, and a move that passes here may still be `verified_illegal`.
    """
    rosters = dict(state.rosters)

    # Removals first, so a player moving between two rosters in the same move never has to
    # exist on both at once — which a three-team trade would otherwise require.
    for m in move.movements:
        if m.from_team_id is None:
            continue
        current = rosters.get(m.from_team_id)
        if current is None:
            raise ValueError(
                f"move touches team {m.from_team_id}, which is not in this league state"
            )
        rosters[m.from_team_id] = current.with_removed(m.player_id)

    for m in move.movements:
        if m.to_team_id is None or m.slot is None:
            continue
        current = rosters.get(m.to_team_id)
        if current is None:
            raise ValueError(
                f"move touches team {m.to_team_id}, which is not in this league state"
            )
        rosters[m.to_team_id] = current.with_added(m.slot)

    new_label = label or move.describe()
    return LeagueState(
        season=state.season,
        rosters={tid: r.relabelled(new_label) for tid, r in rosters.items()},
        label=new_label,
    )


@dataclass(frozen=True, slots=True)
class ScenarioStep:
    """One node in a scenario: the move that was made and the state it produced.

    `parent` is the pointer that makes a scenario a tree rather than a list. Nothing
    constructs a branching tree today — the shipped product evaluates one move at a time —
    but a sequence built from these is already a degenerate tree, so the multi-team,
    multi-step reasoning in §11 of the Pivot brief becomes a traversal rather than a
    rewrite.

    Note the vocabulary: Pivot's `Scenario` is a roster-state trajectory. The **stored**
    `scenarios` table is a different thing entirely — a team's strategy mandate (weights,
    horizon, risk tolerance, untouchables). See `domain.mandate`.
    """

    move: Move
    state: LeagueState
    parent: ScenarioStep | None = None
    notes: tuple[str, ...] = field(default_factory=tuple)

    @property
    def depth(self) -> int:
        return 0 if self.parent is None else self.parent.depth + 1

    def lineage(self) -> tuple[ScenarioStep, ...]:
        chain: list[ScenarioStep] = []
        node: ScenarioStep | None = self
        while node is not None:
            chain.append(node)
            node = node.parent
        return tuple(reversed(chain))

    def then(self, move: Move) -> ScenarioStep:
        return ScenarioStep(move=move, state=apply(self.state, move), parent=self)

    def branch(self, move: Move) -> ScenarioStep:
        """An alternative continuation from the same state.

        Identical to `then` — named separately because the intent differs and a reader
        following a scenario tree should be able to see which was meant.
        """
        return self.then(move)


def replay(initial: LeagueState, moves: tuple[Move, ...]) -> ScenarioStep | None:
    """Apply moves in order, returning the final step (or None for an empty sequence)."""
    step: ScenarioStep | None = None
    state = initial
    for move in moves:
        state = apply(state, move)
        step = ScenarioStep(move=move, state=state, parent=step)
    return step


__all__ = [
    "Move",
    "MoveKind",
    "PlayerMovement",
    "ScenarioStep",
    "apply",
    "replay",
]
