"""Constrained trade-candidate generation (optional recommendation engine).

Generates two-team candidates from real rosters via beam search:
outgoing packages → matching incoming packages → legality → both-sides utility →
ranked survivors. Combinatorial explosion is bounded by package-size limits, per-stage
pruning, and an evaluation budget. Model utility is never presented as proof a real
front office would accept the deal."""

from itertools import combinations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.analytics.sensitivity import composite_utility
from app.cba.builder import build_trade_context
from app.cba.engine import TradeLegalityEngine
from app.config import get_settings
from app.db.models import RosterEntry, Team
from app.services.evaluation import DEFAULT_WEIGHTS, EvaluationService

MAX_OUTGOING_PACKAGES = 12
MAX_INCOMING_PER_TEAM = 8
MAX_PLAYERS_PER_SIDE = 2
EVALUATION_BUDGET = 400
TOP_K = 8
COUNTERPARTY_MIN_UTILITY = 42.0


def generate_candidates(
    db: Session,
    focal_team_id: str,
    strategy: str = "custom",
    weights: dict[str, float] | None = None,
    untouchable_player_ids: list[str] | None = None,
    preferred_outgoing_ids: list[str] | None = None,
    max_candidates: int = TOP_K,
) -> dict:
    settings = get_settings()
    service = EvaluationService(db)
    untouchables = set(untouchable_player_ids or [])
    preferred = set(preferred_outgoing_ids or [])
    weights = weights or DEFAULT_WEIGHTS.get(strategy, DEFAULT_WEIGHTS["custom"])

    focal_roster = service._roster_cards(focal_team_id)
    focal_needs = service._team_needs(focal_team_id)
    if not focal_needs:
        return {"error": "team needs not computed; run `make score` first", "candidates": []}

    tradeable = [c for c in focal_roster if c.player_id not in untouchables]
    tradeable.sort(key=lambda c: (c.player_id not in preferred, -c.minutes))

    outgoing_packages: list[list] = [[c] for c in tradeable[:MAX_OUTGOING_PACKAGES]]
    for pair in combinations(tradeable[:8], 2):
        outgoing_packages.append(list(pair))
    outgoing_packages = outgoing_packages[:MAX_OUTGOING_PACKAGES * 2]

    top_needs = sorted(focal_needs.items(), key=lambda kv: kv[1], reverse=True)[:3]
    need_skills = {kv[0] for kv in top_needs}
    from app.analytics.needs import NEED_TO_SKILL

    target_skills = {NEED_TO_SKILL[k] for k in need_skills if k in NEED_TO_SKILL}

    teams = db.scalars(select(Team).where(Team.id != focal_team_id)).all()
    engine = TradeLegalityEngine()
    evaluated = 0
    candidates: list[dict] = []

    for other in teams:
        if evaluated >= EVALUATION_BUDGET:
            break
        other_roster = service._roster_cards(other.id)
        # incoming candidates: address the focal team's top needs, best first
        def need_score(card) -> float:
            return sum(card.skills.get(s, 0.0) for s in target_skills)

        incoming_pool = sorted(
            (c for c in other_roster if c.skills),
            key=need_score,
            reverse=True,
        )[:MAX_INCOMING_PER_TEAM]

        incoming_packages: list[list] = [[c] for c in incoming_pool[:4]]
        for pair in combinations(incoming_pool[:4], 2):
            incoming_packages.append(list(pair))

        for outgoing in outgoing_packages[:10]:
            for incoming in incoming_packages:
                if evaluated >= EVALUATION_BUDGET:
                    break
                if len(outgoing) > MAX_PLAYERS_PER_SIDE or len(incoming) > MAX_PLAYERS_PER_SIDE:
                    continue
                # quick TEI sanity: skip wildly lopsided candidates
                tei_gap = sum(c.tei for c in incoming) - sum(c.tei for c in outgoing)
                if abs(tei_gap) > 6.0:
                    continue
                evaluated += 1
                moves = [
                    {"player_id": c.player_id, "from_team_id": focal_team_id, "to_team_id": other.id}
                    for c in outgoing
                ] + [
                    {"player_id": c.player_id, "from_team_id": other.id, "to_team_id": focal_team_id}
                    for c in incoming
                ]
                team_ids = [focal_team_id, other.id]
                try:
                    context = build_trade_context(db, team_ids, moves)
                    legality = engine.evaluate(context)
                except Exception:
                    continue
                if legality["overall_status"] == "verified_illegal":
                    continue
                focal_eval = service.evaluate_for_team(
                    focal_team_id, team_ids, moves, [], strategy, weights, legality
                )
                if (focal_eval["composite_utility"] or 0) < 48:
                    continue
                other_eval = service.evaluate_for_team(
                    other.id, team_ids, moves, [], "custom", None, legality
                )
                if (other_eval["composite_utility"] or 0) < COUNTERPARTY_MIN_UTILITY:
                    continue
                candidates.append(
                    {
                        "counterparty": {"team_id": other.id, "abbreviation": other.abbreviation,
                                         "name": other.full_name},
                        "outgoing": [{"player_id": c.player_id, "name": c.name, "tei": round(c.tei, 2)} for c in outgoing],
                        "incoming": [{"player_id": c.player_id, "name": c.name, "tei": round(c.tei, 2)} for c in incoming],
                        "legality_status": legality["overall_status"],
                        "focal_utility": focal_eval["composite_utility"],
                        "counterparty_utility": other_eval["composite_utility"],
                        "focal_components": focal_eval["components"],
                        "rationale": _rationale(top_needs, incoming),
                    }
                )

    candidates.sort(key=lambda c: c["focal_utility"], reverse=True)
    return {
        "focal_team_id": focal_team_id,
        "strategy": strategy,
        "target_needs": [k for k, _ in top_needs],
        "evaluations_run": evaluated,
        "note": (
            "Candidates are model-generated explorations under documented constraints; "
            "utility scores are not evidence that a real front office would accept."
        ),
        "candidates": candidates[:max_candidates],
    }


def _rationale(top_needs: list[tuple[str, float]], incoming: list) -> str:
    needs_text = ", ".join(k.replace("_", " ") for k, _ in top_needs)
    names = ", ".join(c.name for c in incoming)
    return f"Targets top roster needs ({needs_text}) with {names}."
