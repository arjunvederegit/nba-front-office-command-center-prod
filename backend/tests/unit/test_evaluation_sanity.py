"""Sanity properties of the evaluation pipeline.

Every property here is a statement the product must be able to defend. Properties that
the code at commit `f16dedc` violates are marked `xfail(strict=True)` so that:

- a green run means "the defect is still present, and we know it";
- a flip to XPASS *fails the suite*, so an accidental early fix is loud rather than
  silent, and "the fix worked" is distinguishable from "the number moved".

Each xfail names the audit finding (QA-N) or plan item (R-N / C-N) it pins. The fix
release removes the marker in the same commit that changes the behaviour.
"""

import pytest
from sqlalchemy.orm import Session

from app.analytics.sensitivity import composite_utility, normalize_weights
from app.cba.builder import build_trade_context
from app.cba.engine import TradeLegalityEngine
from app.services.evaluation import EvaluationService


def _moves(players, from_team, to_team) -> list[dict]:
    return [
        {"player_id": p.id, "from_team_id": from_team.id, "to_team_id": to_team.id}
        for p in players
    ]


def _evaluate(db: Session, league: dict, team, player_moves, pick_moves=None, strategy="contend"):
    return EvaluationService(db).evaluate_for_team(
        team_id=team.id,
        team_ids=[league["team_a"].id, league["team_b"].id],
        player_moves=player_moves,
        pick_moves=pick_moves or [],
        strategy=strategy,
    )


def _legality(db: Session, league: dict, player_moves, pick_moves=None) -> dict:
    context = build_trade_context(
        db, [league["team_a"].id, league["team_b"].id], player_moves, pick_moves or []
    )
    return TradeLegalityEngine().evaluate(context)


# ----------------------------------------------------------- fixture self-checks
# These must pass at every commit; if they break, the fixture stopped exercising the
# modelling path and every property below became vacuous.


def test_fixture_exercises_the_modelling_path(db: Session, seeded_league: dict) -> None:
    service = EvaluationService(db)
    cards = service._roster_cards(seeded_league["team_a"].id)
    assert len(cards) == 15
    modelled = [c for c in cards if c.player_id != seeded_league["unmodeled"].id]
    assert len({round(c.tei, 6) for c in modelled}) > 1, "impact estimates must vary"
    assert any(c.skills for c in cards), "skill vectors must be computed"
    assert service._team_needs(seeded_league["team_a"].id), "team needs must be present"


def test_fixture_roster_giveaway_is_illegal(db: Session, seeded_league: dict) -> None:
    """The 15-for-nothing giveaway must be *detected* as illegal by the CBA engine —
    that is the precondition for the legality-gate property below."""
    legality = _legality(
        db,
        seeded_league,
        _moves(seeded_league["roster_a"], seeded_league["team_a"], seeded_league["team_b"]),
    )
    assert legality["overall_status"] == "verified_illegal"


# --------------------------------------------------------------------- QA-1 / R1-3


def test_verified_illegal_trade_has_no_decision_score(db: Session, seeded_league: dict) -> None:
    result = _evaluate(
        db,
        seeded_league,
        seeded_league["team_a"],
        _moves(seeded_league["roster_a"], seeded_league["team_a"], seeded_league["team_b"]),
    )
    assert result["legality"]["status"] == "verified_illegal"
    assert result["composite_utility"] is None, (
        "an illegal trade must not receive an affirmative decision score"
    )
    assert result["decision_status"] == "suppressed_illegal"
    assert all(v is None for v in result["components"].values())
    assert result["drivers"] == []
    # The refusal must be explained, and must name the rule that caused it.
    failing = result["suppression"]["failing_rules"]
    assert failing and any(r["rule_code"] == "ROSTER_SIZE" for r in failing)
    assert any("12" in r["message"] for r in failing), "the 12-man minimum must be named"


@pytest.mark.xfail(strict=True, reason="QA-1: _performance treats vacated minutes as league average")
def test_gutting_a_roster_does_not_look_like_an_upgrade(db: Session, seeded_league: dict) -> None:
    result = _evaluate(
        db,
        seeded_league,
        seeded_league["team_a"],
        _moves(seeded_league["roster_a"], seeded_league["team_a"], seeded_league["team_b"]),
    )
    performance = result["components"]["performance"]
    assert performance is not None
    assert performance < 25.0, f"performance was {performance} for a roster given away"


# --------------------------------------------------------------------- QA-5 / R1-3


def test_empty_trade_reports_no_probability(db: Session, seeded_league: dict) -> None:
    result = _evaluate(db, seeded_league, seeded_league["team_a"], [])
    assert result["uncertainty"]["prob_positive"] is None


def test_empty_trade_scores_neutral(db: Session, seeded_league: dict) -> None:
    """Nothing happening must read as neutral, not as a negative outcome.

    Before R1-3 this scored 46.36, because `risk` consumed `prob_positive = 0.0` from an
    all-zero draw array.
    """
    result = _evaluate(db, seeded_league, seeded_league["team_a"], [])
    assert result["components"]["performance"] == pytest.approx(50.0, abs=0.01)
    assert result["components"]["risk"] is None
    assert result["composite_utility"] == pytest.approx(50.0, abs=0.01)


# --------------------------------------------------------------------------- QA-6


@pytest.mark.xfail(strict=True, reason="QA-6: detail[:12] slices in roster order, not by minutes")
def test_rotation_detail_is_sorted_by_minutes(db: Session, seeded_league: dict) -> None:
    moving = seeded_league["roster_a"][0]
    result = _evaluate(
        db,
        seeded_league,
        seeded_league["team_a"],
        _moves([moving], seeded_league["team_a"], seeded_league["team_b"]),
    )
    for key in ("rotation_before", "rotation_after"):
        rows = result["detail"]["performance"][key]
        minutes = [r["minutes"] for r in rows]
        assert minutes == sorted(minutes, reverse=True), f"{key} is not minutes-sorted"


@pytest.mark.xfail(strict=True, reason="QA-6: acquired players fall outside the [:12] window")
def test_rotation_detail_always_includes_traded_players(db: Session, seeded_league: dict) -> None:
    incoming = seeded_league["roster_b"][14]  # lowest-minutes BBB player
    outgoing = seeded_league["roster_a"][0]
    moves = _moves([outgoing], seeded_league["team_a"], seeded_league["team_b"]) + _moves(
        [incoming], seeded_league["team_b"], seeded_league["team_a"]
    )
    result = _evaluate(db, seeded_league, seeded_league["team_a"], moves)
    after_ids = {r["player_id"] for r in result["detail"]["performance"]["rotation_after"]}
    assert incoming.id in after_ids, "the acquired player is missing from the post-trade rotation"


# --------------------------------------------------------------------------- QA-8


def test_no_incoming_players_means_no_availability_number(
    db: Session, seeded_league: dict
) -> None:
    result = _evaluate(
        db,
        seeded_league,
        seeded_league["team_a"],
        _moves(seeded_league["roster_a"][:1], seeded_league["team_a"], seeded_league["team_b"]),
    )
    assert result["detail"]["risk"]["incoming_availability"] is None


# --------------------------------------------------------------------------- R1-4


@pytest.mark.xfail(strict=True, reason="R1-4: tei defaults to 0.0, the 63rd percentile")
def test_unmodeled_players_are_disclosed_not_defaulted(db: Session, seeded_league: dict) -> None:
    result = _evaluate(
        db,
        seeded_league,
        seeded_league["team_b"],
        _moves([seeded_league["unmodeled"]], seeded_league["team_a"], seeded_league["team_b"]),
    )
    assert result.get("has_unmodeled_players") is True
    assert seeded_league["unmodeled"].full_name in (result.get("unmodeled_players") or [])
    incoming = result["incoming"][0]
    assert incoming["tei"] is None, "a player with no impact estimate must not report a TEI"


@pytest.mark.xfail(strict=True, reason="R1-4: unmodelled players get TEI_SIGMA_DEFAULT = 1.5")
def test_unmodeled_players_do_not_get_a_confident_band(db: Session, seeded_league: dict) -> None:
    service = EvaluationService(db)
    unmodeled_card = next(
        c
        for c in service._roster_cards(seeded_league["team_a"].id)
        if c.player_id == seeded_league["unmodeled"].id
    )
    modelled_card = next(
        c
        for c in service._roster_cards(seeded_league["team_a"].id)
        if c.player_id != seeded_league["unmodeled"].id
    )
    assert unmodeled_card.tei_sigma is None or unmodeled_card.tei_sigma > modelled_card.tei_sigma


# ---------------------------------------------------------------------- C13 drivers


def test_drivers_reconcile_with_the_composite(db: Session, seeded_league: dict) -> None:
    """Only bites when a component is excluded — `composite_utility` renormalizes the
    surviving weights but `drivers` keeps the originals."""
    result = _evaluate(
        db,
        seeded_league,
        seeded_league["team_a"],
        _moves([seeded_league["no_contract_a"]], seeded_league["team_a"], seeded_league["team_b"])
        + _moves(seeded_league["roster_b"][:1], seeded_league["team_b"], seeded_league["team_a"]),
    )
    assert result["excluded_components"], "the exclusion path must actually be exercised"
    summed = sum(float(d["contribution"]) for d in result["drivers"])
    assert summed == pytest.approx(result["composite_utility"] - 50.0, abs=0.05)


# ------------------------------------------------------------------ C2 / R3-5 units


@pytest.mark.xfail(strict=True, reason="C2/R3-5: the point estimate and the Monte Carlo differ")
def test_monte_carlo_median_reproduces_the_point_estimate(
    db: Session, seeded_league: dict
) -> None:
    """`_performance` normalises over the whole 240-minute reallocation; the Monte Carlo
    sums raw minute shares over traded players only. The gap widens with trade size, so
    a 5-for-5 makes it unmissable."""
    result = _evaluate(
        db,
        seeded_league,
        seeded_league["team_a"],
        _moves(seeded_league["roster_a"][:5], seeded_league["team_a"], seeded_league["team_b"])
        + _moves(seeded_league["roster_b"][:5], seeded_league["team_b"], seeded_league["team_a"]),
    )
    point = result["detail"]["performance"]["delta_wins"]
    median = result["uncertainty"]["median"]
    assert median == pytest.approx(point, abs=0.05)


# ------------------------------------------------------------- C13 sensitivity honesty


def test_composite_utility_is_none_when_nothing_can_be_scored() -> None:
    assert composite_utility(dict.fromkeys(("performance", "fit"), None), {"performance": 1.0}) is None


def test_zeroed_weights_are_not_silently_re_enabled() -> None:
    zeroed = dict.fromkeys(("performance", "fit", "risk"), 0.0)
    assert all(v == 0.0 for v in normalize_weights(zeroed).values())


# ------------------------------------------------ invariants that must never regress


def test_verified_legal_is_never_returned_with_an_unavailable_rule(
    db: Session, seeded_league: dict
) -> None:
    legality = _legality(
        db,
        seeded_league,
        _moves(seeded_league["roster_a"][:1], seeded_league["team_a"], seeded_league["team_b"])
        + _moves(seeded_league["roster_b"][:1], seeded_league["team_b"], seeded_league["team_a"]),
    )
    if any(r["status"] == "unavailable" for r in legality["rule_results"]):
        assert legality["overall_status"] != "verified_legal"


def test_excluded_components_are_reported_and_downgrade_confidence(
    db: Session, seeded_league: dict
) -> None:
    result = _evaluate(
        db,
        seeded_league,
        seeded_league["team_a"],
        _moves(seeded_league["roster_a"][:1], seeded_league["team_a"], seeded_league["team_b"]),
    )
    for key in result["excluded_components"]:
        assert result["components"][key] is None
    if result["excluded_components"]:
        assert result["confidence"] in ("medium", "low")


# ------------------------------------------------------- the executive report (R1-3)


def test_report_refuses_to_recommend_an_illegal_deal(db: Session, seeded_league: dict) -> None:
    """The report is the highest-stakes artifact: it must not print a utility for a deal
    that cannot be executed, and it must name the rules that stopped it."""
    from app.services.reports import build_report_markdown

    moves = _moves(
        seeded_league["roster_a"], seeded_league["team_a"], seeded_league["team_b"]
    )
    legality = _legality(db, seeded_league, moves)
    evaluation = _evaluate(db, seeded_league, seeded_league["team_a"], moves)
    markdown = build_report_markdown(
        trade_name="Roster giveaway",
        focal_team_name="Alpha Test Club",
        strategy="contend",
        legality=legality,
        evaluations={seeded_league["team_a"].id: evaluation},
        focal_team_id=seeded_league["team_a"].id,
    )
    assert "Do not proceed — the trade fails implemented CBA rules" in markdown
    assert "Composite utility" not in markdown
    assert "Proceed with further diligence" not in markdown
    assert "ROSTER_SIZE" in markdown


def test_report_omits_the_availability_line_without_incoming_players(
    db: Session, seeded_league: dict
) -> None:
    """QA-8: the report printed 'Historical availability of incoming players: 85%' for a
    deal with no incoming players at all."""
    from app.services.reports import build_report_markdown

    moves = _moves(
        seeded_league["roster_a"][:1], seeded_league["team_a"], seeded_league["team_b"]
    )
    legality = _legality(db, seeded_league, moves)
    evaluation = _evaluate(db, seeded_league, seeded_league["team_a"], moves)
    markdown = build_report_markdown(
        trade_name="Salary dump",
        focal_team_name="Alpha Test Club",
        strategy="contend",
        legality=legality,
        evaluations={seeded_league["team_a"].id: evaluation},
        focal_team_id=seeded_league["team_a"].id,
    )
    assert "Historical availability of incoming players" not in markdown
