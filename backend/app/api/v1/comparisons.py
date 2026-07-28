from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.analytics.sensitivity import normalize_weights, rank_stability
from app.api.schemas import ComparisonIn
from app.core.errors import NotFoundError
from app.db.base import get_db
from app.db.models import ComparisonSet, Scenario, TradeProposal
from app.services.evaluation import DEFAULT_WEIGHTS

router = APIRouter(prefix="/comparisons", tags=["comparisons"])


def _pareto_flags(rows: list[dict]) -> None:
    """Mark alternatives dominated on (performance, risk) with utility as tiebreak —
    an alternative is dominated if another is >= on all displayed axes and > on one."""
    axes = ["performance", "fit", "timeline", "assets", "risk"]
    for row in rows:
        row["dominated_by"] = None
    for row in rows:
        for other in rows:
            if other is row:
                continue
            row_values = [row["components"].get(a) for a in axes]
            other_values = [other["components"].get(a) for a in axes]
            pairs = [
                (o, r)
                for o, r in zip(other_values, row_values, strict=False)
                if o is not None and r is not None
            ]
            if len(pairs) < 2:
                continue
            if all(o >= r for o, r in pairs) and any(o > r for o, r in pairs):
                row["dominated_by"] = other["trade_id"]
                break


@router.post("", status_code=201)
def create_comparison(payload: ComparisonIn, db: Session = Depends(get_db)) -> dict:
    for trade_id in payload.trade_ids:
        if db.get(TradeProposal, trade_id) is None:
            raise NotFoundError(f"trade {trade_id} not found")
    comparison = ComparisonSet(
        name=payload.name, scenario_id=payload.scenario_id, trade_ids=payload.trade_ids
    )
    db.add(comparison)
    db.commit()
    return get_comparison(comparison.id, db)


@router.get("/{comparison_id}")
def get_comparison(comparison_id: str, db: Session = Depends(get_db)) -> dict:
    from app.api.v1.trades import _trade_detail

    comparison = db.get(ComparisonSet, comparison_id)
    if comparison is None:
        raise NotFoundError(f"comparison {comparison_id} not found")

    scenario = db.get(Scenario, comparison.scenario_id) if comparison.scenario_id else None
    focal_team_id = scenario.focal_team_id if scenario else None
    strategy = scenario.strategy if scenario else "custom"
    weights = (
        {w.component: w.weight for w in scenario.weights}
        if scenario and scenario.weights
        else DEFAULT_WEIGHTS.get(strategy, DEFAULT_WEIGHTS["custom"])
    )
    weights = normalize_weights(weights)

    rows = []
    for trade_id in comparison.trade_ids:
        detail = _trade_detail(db, trade_id)
        team_id = focal_team_id or detail["teams"][0]["team_id"]
        evaluation = detail["evaluations"].get(team_id)
        if evaluation is None:
            continue
        team_legality = evaluation.get("legality", {})
        decision_status = evaluation.get("decision_status", "scored")
        rows.append(
            {
                "trade_id": trade_id,
                "name": detail["name"],
                "legality_status": detail["legality"]["overall_status"],
                "decision_status": decision_status,
                "suppression": evaluation.get("suppression"),
                # Carried so the comparison board renders the same confidence the
                # Trade Evaluator does, instead of synthesizing its own (C13).
                "confidence": evaluation.get("confidence"),
                "has_unmodeled_players": evaluation.get("has_unmodeled_players", False),
                "unmodeled_players": evaluation.get("unmodeled_players", []),
                "composite_utility": evaluation["composite_utility"],
                "components": evaluation["components"],
                # A suppressed evaluation carries no detail at all — the deal cannot be
                # executed, so there is no projected win change to report.
                "delta_wins": (evaluation.get("detail") or {})
                .get("performance", {})
                .get("delta_wins"),
                "uncertainty": evaluation["uncertainty"],
                "payroll_after": team_legality.get("payroll_after"),
                "apron_status_after": team_legality.get("apron_status_after"),
                "incoming": evaluation["incoming"],
                "outgoing": evaluation["outgoing"],
            }
        )

    # Only deals that can actually be executed compete. Ranking an illegal deal against
    # legal ones invites picking the one that cannot happen.
    rankable = [r for r in rows if r["decision_status"] == "scored"]
    _pareto_flags(rankable)
    for row in rows:
        row.setdefault("dominated_by", None)
    stability = rank_stability({r["trade_id"]: r["components"] for r in rankable}, weights)
    rows.sort(
        key=lambda r: (r["decision_status"] == "scored", r["composite_utility"] or 0),
        reverse=True,
    )
    excluded = [r["trade_id"] for r in rows if r["decision_status"] != "scored"]
    return {
        "id": comparison.id,
        "name": comparison.name,
        "scenario_id": comparison.scenario_id,
        "focal_team_id": focal_team_id,
        "weights": weights,
        "alternatives": rows,
        "sensitivity": stability,
        "excluded_from_ranking": excluded,
        "note": "Alternatives marked dominated_by are Pareto-dominated across displayed "
        "component axes under the current data. Deals that fail a verified rule, or that "
        "no component could score, are listed but never ranked.",
    }
