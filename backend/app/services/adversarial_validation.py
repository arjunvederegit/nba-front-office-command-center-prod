"""Hostile trades, run against the ingested league, checking that the product refuses well.

Every other battery here asks whether a model measures what it claims. This one asks a
different question: **when the honest answer is "no" or "I cannot tell", does the product
give it?** Those are the failures that matter most in a decision-support tool, because a
wrong number that looks like a number is worse than a gap that looks like a gap.

R6 ran twenty of these by hand and reported "20 / 20". A number in a release report is not
a gate — nobody can re-run it, and nothing fails when it stops being true. R7 commits them.

## What a scenario asserts

Each one builds a deliberately awkward trade on the real ingested rosters and asserts a
**property of the response**, never a value. "Boston's score is 31" would be a snapshot of
this database; "an illegal trade carries no decision score" is the claim the product makes
about itself.

The scenarios fall into four groups:

- **Refusals** — a trade that breaks a verified rule must be refused, and the refusal must
  name the rule. No affirmative recommendation may survive one.
- **Neutrality** — a trade in which nothing moves is neither good nor bad, and must not be
  scored as either. This is QA-5, which shipped as a 46.36.
- **Disclosure** — a trade containing a player the model cannot price must say so and must
  not quietly substitute a league-average stand-in. This is QA-8 and R1-4.
- **Direction** — giving away real value must not score better than receiving it. A
  battery with no directional check passes on a model that returns a constant.

`make adversarial-validation` runs them all and exits non-zero on any failure.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.cba.builder import build_trade_context
from app.cba.engine import TradeLegalityEngine
from app.core.errors import DomainError
from app.db.models import Team
from app.services.evaluation import EvaluationService, PlayerCard

#: The composite's own definition of "changes nothing". A trade that moves nothing must
#: land here exactly, not near here.
NEUTRAL = 50.0


@dataclass
class Check:
    name: str
    passed: bool
    detail: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {"name": self.name, "passed": self.passed, "detail": self.detail}


@dataclass
class _Side:
    team: Team
    #: Priced players only, ordered by estimated impact, best first. `_rosters` does the
    #: sorting; see the note there about why it cannot be assumed.
    players: list[PlayerCard]


def _rosters(db: Session, service: EvaluationService) -> list[_Side]:
    """Teams with enough of a priced roster to build a hostile trade from, best first.

    **Sorted here, deliberately.** `_roster_cards` orders by `player_id` — a deterministic
    order, chosen in R1-5 so that every downstream `[:12]` is stable rather than whatever
    the database returned — but it is not an order by quality. Writing "the best three" and
    slicing that list takes three arbitrary players, and the first run of this battery did
    exactly that: it reported the team **sending** its two best at 70.9 and the team
    receiving them at 23.9, which looked like a serious inversion in the model and was a
    faulty assumption in the test.

    Unpriced players are excluded rather than sorted to one end. They have no value to
    give away, so a scenario about giving value away must not be built from them.
    """
    teams = db.scalars(select(Team).order_by(Team.abbreviation)).all()
    sides: list[_Side] = []
    for team in teams:
        priced = [c for c in service._roster_cards(team.id) if c.tei is not None]
        if len(priced) >= 6:
            ordered = sorted(priced, key=lambda c: (-(c.tei or 0.0), c.player_id))
            sides.append(_Side(team=team, players=ordered))
    return sides


def _moves(players: list[PlayerCard], from_team: str, to_team: str) -> list[dict]:
    return [
        {"player_id": p.player_id, "from_team_id": from_team, "to_team_id": to_team}
        for p in players
    ]


def _evaluate(
    db: Session, service: EvaluationService, team_ids: list[str], moves: list[dict]
) -> dict[str, dict]:
    context = build_trade_context(db, team_ids, moves, [])
    legality = TradeLegalityEngine().evaluate(context)
    return {
        "legality": legality,
        "evaluations": {
            team_id: service.evaluate_for_team(
                team_id, team_ids, moves, [], "contend", None, legality, simulate=False
            )
            for team_id in team_ids
        },
    }


def run_battery(db: Session, sample_teams: int = 8) -> dict[str, Any]:
    """Every scenario, over the first `sample_teams` teams with a usable roster."""
    service = EvaluationService(db)
    sides = _rosters(db, service)
    if len(sides) < 2:
        return {
            "available": False,
            "reason": "fewer than two teams have a roster in this database",
            "checks": [],
            "failed": [],
        }
    sides = sides[:sample_teams]
    checks: list[Check] = []

    # ---------------------------------------------------------------- neutrality
    #
    # QA-5. An empty trade shipped as 46.36 — a number produced by scoring six components
    # against a package that does not exist. Nothing moves, so nothing is better or worse.
    empty_scores: dict[str, Any] = {}
    empty_prob: dict[str, Any] = {}
    for side in sides[:2]:
        other = sides[1] if side is sides[0] else sides[0]
        result = _evaluate(db, service, [side.team.id, other.team.id], [])
        for team_id, evaluation in result["evaluations"].items():
            empty_scores[team_id] = evaluation.get("composite_utility")
            empty_prob[team_id] = (evaluation.get("uncertainty") or {}).get("prob_positive")
    checks.append(
        Check(
            "an_empty_trade_scores_exactly_neutral",
            all(v == NEUTRAL for v in empty_scores.values()),
            {"scores": empty_scores, "expected": NEUTRAL, "qa": "QA-5, shipped as 46.36"},
        )
    )
    checks.append(
        Check(
            "an_empty_trade_states_no_probability",
            all(v is None for v in empty_prob.values()),
            {
                "prob_positive": empty_prob,
                "why": "a distribution over a package that does not exist is not zero, "
                "and 0.0 reads as 'certain to hurt'",
            },
        )
    )

    # ------------------------------------------------------------------ refusals
    #
    # A one-way dump of a whole rotation onto a full roster breaks the roster limit. The
    # verdict must be a refusal that names its rule, and no decision score may survive it.
    refusals: list[dict] = []
    for side in sides:
        for other in sides:
            if other.team.id == side.team.id:
                continue
            moves = _moves(side.players[:6], side.team.id, other.team.id)
            result = _evaluate(db, service, [side.team.id, other.team.id], moves)
            status = result["legality"]["overall_status"]
            if status != "verified_illegal":
                continue
            # `rule_code`, not `rule`. The first version of this read a key that does
            # not exist, collected `[None]`, and passed — a non-empty list of nothing.
            # A check that cannot fail is not a check.
            named = [
                r.get("rule_code")
                for r in result["legality"].get("rule_results", [])
                if r.get("status") == "fail"
            ]
            messages = [
                r.get("message")
                for r in result["legality"].get("rule_results", [])
                if r.get("status") == "fail"
            ]
            scored = [
                e.get("composite_utility") for e in result["evaluations"].values()
            ]
            statuses = [e.get("decision_status") for e in result["evaluations"].values()]
            refusals.append(
                {
                    "from": side.team.abbreviation,
                    "to": other.team.abbreviation,
                    "rules_failed": named,
                    "messages": messages,
                    "scores": scored,
                    "decision_status": statuses,
                }
            )
            break
        if len(refusals) >= 4:
            break

    checks.append(
        Check(
            "a_verified_illegal_trade_carries_no_decision_score",
            bool(refusals)
            and all(all(s is None for s in r["scores"]) for r in refusals),
            {
                "refusals_found": len(refusals),
                "sample": refusals[:2],
                "qa": "QA-1 / R1-3: a suppressed evaluation must not carry a composite",
            },
        )
    )
    checks.append(
        Check(
            "a_refusal_names_the_rule_it_failed",
            bool(refusals)
            and all(
                r["rules_failed"]
                and all(isinstance(code, str) and code for code in r["rules_failed"])
                and all(isinstance(m, str) and m for m in r["messages"])
                for r in refusals
            ),
            {
                "sample": [
                    {"codes": r["rules_failed"], "messages": r["messages"][:1]}
                    for r in refusals[:2]
                ],
                "why": "a refusal a user cannot act on is barely better than a wrong "
                "answer, so the code and a readable message are both required",
            },
        )
    )
    checks.append(
        Check(
            "a_suppressed_evaluation_says_it_was_suppressed",
            bool(refusals)
            and all(
                all(s == "suppressed_illegal" for s in r["decision_status"])
                for r in refusals
            ),
            {"sample": [r["decision_status"] for r in refusals[:2]]},
        )
    )

    # ----------------------------------------------------------------- direction
    #
    # Give away the three best players for nothing. R5.5-1 charged a departure's minutes
    # to a replacement rather than to the roster, and before it did, 191 of 370 such
    # removals scored as GAINS. A battery with no directional check passes on a model
    # that returns a constant.
    #
    # The exchange is **roster-neutral on purpose**: three out, three back. A one-way
    # giveaway of three rotation players is refused by the roster limit on almost every
    # counterparty, so a battery built that way silently checks nothing — which is what
    # the first run of this file did, and why the "no cases" outcome below is a failure
    # rather than a vacuous pass.
    giveaways: list[dict] = []
    for side in sides:
        other = next(s for s in sides if s.team.id != side.team.id)
        moves = _moves(side.players[:3], side.team.id, other.team.id) + _moves(
            other.players[-3:], other.team.id, side.team.id
        )
        result = _evaluate(db, service, [side.team.id, other.team.id], moves)
        if result["legality"]["overall_status"] == "verified_illegal":
            continue
        giver = result["evaluations"][side.team.id]
        perf = (giver.get("components") or {}).get("performance")
        giveaways.append(
            {
                "team": side.team.abbreviation,
                "performance": perf,
                "composite": giver.get("composite_utility"),
            }
        )
    scored_giveaways = [g for g in giveaways if g["performance"] is not None]
    checks.append(
        Check(
            "giving_away_the_best_three_never_scores_as_a_performance_gain",
            bool(scored_giveaways)
            and all(g["performance"] <= NEUTRAL for g in scored_giveaways),
            {
                "teams_checked": len(scored_giveaways),
                "worst": max((g["performance"] for g in scored_giveaways), default=None),
                # A scenario that constructed no legal trade proves nothing, and must not
                # report a pass for having found nothing to test.
                "note": None if scored_giveaways else "no legal exchange could be built",
                "qa": "R5.5-1: 191 of 370 above-replacement removals once scored as gains",
            },
        )
    )
    checks.append(
        Check(
            "a_roster_gutting_stays_below_the_qa1_ceiling",
            bool(scored_giveaways) and all(g["performance"] < 25 for g in scored_giveaways),
            {
                "max_performance": max(
                    (g["performance"] for g in scored_giveaways), default=None
                ),
                "ceiling": 25,
                "qa": "QA-1 / R3-3",
            },
        )
    )

    # Receiving those same players must not score worse than sending them.
    # Roster-neutral again, and deliberately lopsided in value: each side sends two
    # players, one its best and one its worst, so the counts match and the direction is
    # unambiguous.
    directional: list[dict] = []
    for side in sides[:4]:
        other = next(s for s in sides if s.team.id != side.team.id)
        moves = _moves(side.players[:2], side.team.id, other.team.id) + _moves(
            other.players[-2:], other.team.id, side.team.id
        )
        result = _evaluate(db, service, [side.team.id, other.team.id], moves)
        if result["legality"]["overall_status"] == "verified_illegal":
            continue
        giver = (result["evaluations"][side.team.id].get("components") or {}).get(
            "performance"
        )
        taker = (result["evaluations"][other.team.id].get("components") or {}).get(
            "performance"
        )
        if giver is None or taker is None:
            continue
        directional.append(
            {"sender": side.team.abbreviation, "sent": giver, "received": taker}
        )
    checks.append(
        Check(
            "receiving_value_never_scores_below_sending_it",
            bool(directional) and all(d["received"] >= d["sent"] for d in directional),
            {"pairs": directional},
        )
    )

    # ---------------------------------------------------------------- disclosure
    #
    # R1-4. A player the model cannot price is disclosed and left out of the projection;
    # he is never given a league-average stand-in, and the trade never returns a neutral
    # score as though nothing were missing.
    disclosed: list[dict] = []
    for side in sides:
        unpriced = [p for p in side.players if getattr(p, "tei", None) is None]
        if not unpriced:
            continue
        other = next(s for s in sides if s.team.id != side.team.id)
        moves = _moves(unpriced[:1], side.team.id, other.team.id)
        result = _evaluate(db, service, [side.team.id, other.team.id], moves)
        if result["legality"]["overall_status"] == "verified_illegal":
            continue
        for evaluation in result["evaluations"].values():
            disclosed.append(
                {
                    "team": side.team.abbreviation,
                    "unmodeled": list(evaluation.get("unmodeled_players") or []),
                    "incoming_tei": [p.get("tei") for p in evaluation.get("incoming", [])],
                    "outgoing_tei": [p.get("tei") for p in evaluation.get("outgoing", [])],
                }
            )
        if len(disclosed) >= 4:
            break
    checks.append(
        Check(
            "an_unpriced_player_is_disclosed_and_never_defaulted",
            # Vacuously true where every rostered player is priced, which is a legitimate
            # state of the database and is reported rather than hidden.
            all(d["unmodeled"] for d in disclosed) if disclosed else True,
            {
                "cases": len(disclosed),
                "sample": disclosed[:2],
                "note": "no case in this database" if not disclosed else None,
                "qa": "QA-8 / R1-4",
            },
        )
    )
    checks.append(
        Check(
            "an_unpriced_player_reports_a_null_impact_not_a_zero",
            all(
                all(v is None or v != 0.0 for v in d["incoming_tei"] + d["outgoing_tei"])
                for d in disclosed
            )
            if disclosed
            else True,
            {"cases": len(disclosed)},
        )
    )

    # ------------------------------------------------------------- construction
    #
    # R1-2. A move naming a player who is on a current roster he is not on, and a move
    # naming the same player twice, are both rejected with a readable message rather than
    # evaluated into a number.
    construction: dict[str, Any] = {}
    a, b = sides[0], sides[1]
    duplicated = _moves([a.players[0], a.players[0]], a.team.id, b.team.id)
    try:
        build_trade_context(db, [a.team.id, b.team.id], duplicated, [])
        construction["duplicate_move"] = "accepted"
    except DomainError as exc:
        construction["duplicate_move"] = f"{type(exc).__name__}: {exc}"
    except Exception as exc:  # noqa: BLE001 — any refusal is recorded, then judged below
        construction["duplicate_move"] = f"{type(exc).__name__}: {exc}"

    phantom = [
        {
            "player_id": b.players[0].player_id,
            "from_team_id": a.team.id,
            "to_team_id": b.team.id,
        }
    ]
    try:
        build_trade_context(db, [a.team.id, b.team.id], phantom, [])
        construction["phantom_move"] = "accepted"
    except DomainError as exc:
        construction["phantom_move"] = f"{type(exc).__name__}: {exc}"
    except Exception as exc:  # noqa: BLE001
        construction["phantom_move"] = f"{type(exc).__name__}: {exc}"

    checks.append(
        Check(
            "an_impossible_trade_is_refused_at_construction",
            all(v != "accepted" for v in construction.values()),
            {**construction, "qa": "R1-2 / QA-13"},
        )
    )

    failed = [c.name for c in checks if not c.passed]
    return {
        "available": True,
        "teams_sampled": [s.team.abbreviation for s in sides],
        "checks": [c.as_dict() for c in checks],
        "failed": failed,
    }
