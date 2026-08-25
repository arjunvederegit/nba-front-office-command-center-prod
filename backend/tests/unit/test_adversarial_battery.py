"""The adversarial battery has to be able to fail.

Every check in it asserts that the product refuses well, so the battery's own failure mode
is the dangerous one: a check that cannot fail reports a pass and protects nothing. Two
such checks existed in the first version of this file and both are pinned below —
`rules_failed` read a key that does not exist and collected `[None]`, and the directional
scenarios built trades the roster limit refused, so they ran over an empty list.
"""

from sqlalchemy.orm import Session

from app.services.adversarial_validation import NEUTRAL, run_battery
from app.services.evaluation import EvaluationService


def test_the_battery_runs_and_reports_every_check(db: Session, seeded_league: dict) -> None:
    report = run_battery(db)
    assert report["available"] is True
    names = [c["name"] for c in report["checks"]]
    assert len(names) == len(set(names)), "a duplicated check name hides one of them"
    assert {
        "an_empty_trade_scores_exactly_neutral",
        "a_verified_illegal_trade_carries_no_decision_score",
        "giving_away_the_best_three_never_scores_as_a_performance_gain",
        "an_impossible_trade_is_refused_at_construction",
    } <= set(names)


def test_a_database_with_no_league_says_so_rather_than_passing(db: Session) -> None:
    """An empty database must not produce a battery of vacuous passes."""
    report = run_battery(db)
    assert report["available"] is False
    assert report["checks"] == []
    assert "fewer than two teams" in report["reason"]


def test_the_directional_scenarios_actually_built_a_trade(
    db: Session, seeded_league: dict
) -> None:
    """The first version of these scenarios sent players one way onto a full roster, which
    the roster limit refuses on almost every counterparty — so they iterated over nothing
    and failed for having found no cases. The exchange is roster-neutral now, and this
    asserts it produced cases rather than asserting the cases passed."""
    report = run_battery(db)
    by_name = {c["name"]: c for c in report["checks"]}
    giveaway = by_name["giving_away_the_best_three_never_scores_as_a_performance_gain"]
    assert giveaway["detail"]["teams_checked"] > 0
    assert giveaway["detail"]["note"] is None
    directional = by_name["receiving_value_never_scores_below_sending_it"]
    assert directional["detail"]["pairs"], "no directional pair was constructed"


def test_the_rosters_it_builds_from_are_ordered_by_impact(
    db: Session, seeded_league: dict
) -> None:
    """`_roster_cards` orders by `player_id`, not by quality — a deterministic order chosen
    in R1-5 for stable slicing. Slicing it for "the best three" takes three arbitrary
    players, and the first run of this battery did exactly that: it reported the team
    *sending* its two best at 70.9 and the team receiving them at 23.9, which looked like a
    model inversion and was a faulty assumption in the test."""
    from app.services.adversarial_validation import _rosters

    sides = _rosters(db, EvaluationService(db))
    assert sides, "the fixture no longer produces a usable roster"
    for side in sides:
        values = [card.tei for card in side.players]
        assert all(v is not None for v in values), "an unpriced player entered the sample"
        assert values == sorted(values, reverse=True), side.team.abbreviation


def test_an_empty_trade_is_checked_against_the_composites_own_neutral(
    db: Session, seeded_league: dict
) -> None:
    """50 is the composite's definition of "changes nothing", not a tuned threshold. QA-5
    shipped this as 46.36 — a number produced by scoring six components against a package
    that does not exist."""
    assert NEUTRAL == 50.0
    report = run_battery(db)
    check = next(
        c for c in report["checks"] if c["name"] == "an_empty_trade_scores_exactly_neutral"
    )
    assert check["passed"] is True
    assert set(check["detail"]["scores"].values()) == {NEUTRAL}


def test_a_refusal_must_name_a_rule_code_and_a_message(
    db: Session, seeded_league: dict
) -> None:
    """The check that could not fail. It read `rule_results[*]["rule"]`, which is spelled
    `rule_code`, so it collected `[None]` — a non-empty list of nothing — and passed."""
    report = run_battery(db)
    check = next(
        c for c in report["checks"] if c["name"] == "a_refusal_names_the_rule_it_failed"
    )
    if not check["detail"]["sample"]:
        return  # no illegal trade constructible on this fixture; the count check covers it
    for entry in check["detail"]["sample"]:
        assert entry["codes"] and all(isinstance(c, str) and c for c in entry["codes"])
        assert entry["messages"] and all(isinstance(m, str) and m for m in entry["messages"])
