"""The team mandate: how an organisation has decided to build, expressed as weights.

This module exists to settle a name collision that would otherwise poison the scenario
layer.

The database has a `scenarios` table. It does **not** hold scenarios in the sense Pivot's
roadmap means. It holds a team's *decision mandate*: which strategy the front office is
running (contend, retool, rebuild…), how far out it is looking, how much risk it will take,
whether it will cross the tax or an apron, who is untouchable, and the six component
weights that scoring is done under. It is a settings bag attached to a team, and it never
changes as a result of a move.

Pivot's `Scenario` — the R13 sense — is a roster-state trajectory: state, move, state. That
is `domain.moves.ScenarioStep`.

Two different nouns, one word. The resolution taken here is deliberate and conservative:

- The **stored** entity keeps its table name, its `/scenarios` routes and its API shape.
  Renaming it would mean a migration, a breaking API change and a rewrite of the share
  links and query parameters that seed the trade evaluator — all to relabel a concept
  users already see under a different word anyway. The UI has always called it a
  *strategy*, never a scenario.
- The **domain** vocabulary calls it a `TeamMandate`, and this module is where that
  mapping is written down, so the next person to read `ScenarioStep` and `Scenario` in the
  same file is not left to guess which is which.

`STRATEGY_WEIGHTS` is the canonical weight table; `services.evaluation` re-exports it as
`DEFAULT_WEIGHTS` so every existing consumer keeps its import and every stored evaluation
keeps its meaning.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class Strategy(StrEnum):
    """How a front office has decided to build.

    The vocabulary is fixed because the weight table below is keyed on it and stored
    evaluations reference it. `CUSTOM` is the escape hatch: it carries the neutral weights
    and is what a user's own slider positions are stored against.
    """

    CONTEND = "contend"
    IMPROVE = "improve"
    RETOOL = "retool"
    REBUILD = "rebuild"
    YOUTH = "youth"
    CAP_RELIEF = "cap_relief"
    CUSTOM = "custom"

    @property
    def label(self) -> str:
        return {
            Strategy.CONTEND: "Contend now",
            Strategy.IMPROVE: "Improve the team",
            Strategy.RETOOL: "Retool on the fly",
            Strategy.REBUILD: "Rebuild",
            Strategy.YOUTH: "Build around youth",
            Strategy.CAP_RELIEF: "Create cap relief",
            Strategy.CUSTOM: "Custom priorities",
        }[self]

    @property
    def definition(self) -> str:
        return {
            Strategy.CONTEND: (
                "Win this season. On-court impact and downside risk dominate; future "
                "assets are currency to spend."
            ),
            Strategy.IMPROVE: (
                "Get better without mortgaging anything. The most balanced of the "
                "presets."
            ),
            Strategy.RETOOL: (
                "Stay competitive while shifting the timeline. Contract value and "
                "flexibility carry more weight than they do for a contender."
            ),
            Strategy.REBUILD: (
                "Accumulate. Future assets and timeline alignment dominate; this "
                "season's result is close to irrelevant."
            ),
            Strategy.YOUTH: (
                "Build around a young core. Timeline alignment is the heaviest single "
                "component."
            ),
            Strategy.CAP_RELIEF: (
                "Get out from under money. Contract value dominates, with assets second."
            ),
            Strategy.CUSTOM: "Your own weights, set on the sliders.",
        }[self]


#: The six axes every trade is scored on. Order is presentation order, and is stable
#: because the Strategy Lab charts and the decision memo both read it.
COMPONENT_KEYS: tuple[str, ...] = (
    "performance",
    "fit",
    "contract",
    "timeline",
    "assets",
    "risk",
)

COMPONENT_LABELS: dict[str, str] = {
    "performance": "On-court impact",
    "fit": "Roster fit",
    "contract": "Contract value",
    "timeline": "Competitive window",
    "assets": "Future assets",
    "risk": "Downside risk",
}

#: Canonical strategy weight vectors. `services.evaluation.DEFAULT_WEIGHTS` re-exports
#: this. Every vector sums to 1.0; a component with unavailable data is dropped at scoring
#: time and the remainder renormalized, with the exclusion disclosed.
STRATEGY_WEIGHTS: dict[str, dict[str, float]] = {
    "contend": {
        "performance": 0.32,
        "fit": 0.20,
        "contract": 0.08,
        "timeline": 0.12,
        "assets": 0.08,
        "risk": 0.20,
    },
    "improve": {
        "performance": 0.25,
        "fit": 0.20,
        "contract": 0.12,
        "timeline": 0.13,
        "assets": 0.15,
        "risk": 0.15,
    },
    "retool": {
        "performance": 0.20,
        "fit": 0.18,
        "contract": 0.14,
        "timeline": 0.18,
        "assets": 0.18,
        "risk": 0.12,
    },
    "rebuild": {
        "performance": 0.08,
        "fit": 0.10,
        "contract": 0.17,
        "timeline": 0.25,
        "assets": 0.28,
        "risk": 0.12,
    },
    "youth": {
        "performance": 0.10,
        "fit": 0.14,
        "contract": 0.14,
        "timeline": 0.28,
        "assets": 0.22,
        "risk": 0.12,
    },
    "cap_relief": {
        "performance": 0.10,
        "fit": 0.10,
        "contract": 0.30,
        "timeline": 0.12,
        "assets": 0.26,
        "risk": 0.12,
    },
    "custom": {
        "performance": 0.22,
        "fit": 0.18,
        "contract": 0.14,
        "timeline": 0.16,
        "assets": 0.15,
        "risk": 0.15,
    },
}


@dataclass(frozen=True, slots=True)
class TeamMandate:
    """The domain reading of a stored `Scenario` row.

    Constructed from persistence by the service layer; nothing here reads the database.
    """

    team_id: str
    strategy: Strategy = Strategy.CUSTOM
    horizon_years: int = 1
    risk_tolerance: str = "balanced"
    weights: dict[str, float] | None = None
    untouchable_player_ids: tuple[str, ...] = ()
    willing_to_cross_tax: bool = False
    willing_to_cross_first_apron: bool = False
    willing_to_cross_second_apron: bool = False
    name: str = ""

    @property
    def effective_weights(self) -> dict[str, float]:
        """The weights this mandate scores under — its own if set, else its strategy's."""
        return dict(self.weights or STRATEGY_WEIGHTS[self.strategy.value])


def weights_for(strategy: str) -> dict[str, float]:
    """Weights for a strategy name, falling back to the neutral custom vector.

    The fallback is not a guess: `custom` is defined as the balanced vector, so an
    unrecognised strategy scores neutrally rather than being scored under somebody else's
    priorities.
    """
    return dict(STRATEGY_WEIGHTS.get(strategy, STRATEGY_WEIGHTS["custom"]))


def _check_weights_sum_to_one() -> None:
    for name, vector in STRATEGY_WEIGHTS.items():
        if set(vector) != set(COMPONENT_KEYS):
            raise RuntimeError(f"strategy {name!r} does not cover every component")
        total = sum(vector.values())
        if abs(total - 1.0) > 1e-9:
            raise RuntimeError(f"strategy {name!r} weights sum to {total}, not 1.0")


_check_weights_sum_to_one()


__all__ = [
    "COMPONENT_KEYS",
    "COMPONENT_LABELS",
    "STRATEGY_WEIGHTS",
    "Strategy",
    "TeamMandate",
    "weights_for",
]
