"""Removing test entities from a development database.

The dev database accumulated 22 trade proposals, 16 scenarios and 50 comparison sets
from repeated end-to-end and manual runs — `E2E RosterLab deal`, `Smoke test deal`,
`BOS — Contend now` fourteen times over. `CONTRIBUTING.md` rule 1 requires fixtures to
live only under `backend/tests`, and no document disclosed that they were here.

The cause is fixed elsewhere: the end-to-end suite runs against its own database
(`make seed-demo`). This clears what earlier runs already left behind.

Only user-authored *analysis* entities are in scope — scenarios, trade proposals and
comparison sets, with the rule results, evaluations, reports and assets that hang off a
proposal. Provider-backed data is never touched.
"""

from __future__ import annotations

import re
from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import (
    ComparisonSet,
    GeneratedReport,
    Scenario,
    TradeAsset,
    TradeEvaluation,
    TradeProposal,
    TradeRuleResult,
    TradeTeam,
)

# Names produced by automated runs. Deliberately narrow: it must not match a name a
# person would plausibly choose for real work.
FIXTURE_NAME = re.compile(r"\b(e2e|smoke|test|fixture|probe)\b", re.IGNORECASE)


def find_fixture_entities(db: Session) -> dict[str, list[tuple[str, str]]]:
    """(id, name) pairs that look automated, per entity type. Read-only."""
    return {
        "scenarios": _matches(db.scalars(select(Scenario)).all()),
        "trades": _matches(db.scalars(select(TradeProposal)).all()),
        "comparisons": _matches(db.scalars(select(ComparisonSet)).all()),
    }


def _matches(rows: Sequence[Scenario | TradeProposal | ComparisonSet]) -> list[tuple[str, str]]:
    return [(r.id, r.name) for r in rows if FIXTURE_NAME.search(r.name or "")]


def purge_fixtures(db: Session, *, dry_run: bool = True) -> dict:
    """Delete matching entities and everything that hangs off them.

    Defaults to a dry run: this deletes a developer's saved work if the pattern is
    wrong, so the destructive path has to be asked for explicitly.
    """
    found = find_fixture_entities(db)
    summary: dict = {
        "dry_run": dry_run,
        "matched": {key: [name for _, name in rows] for key, rows in found.items()},
        "counts": {key: len(rows) for key, rows in found.items()},
    }
    if dry_run:
        return summary

    trade_ids = [tid for tid, _ in found["trades"]]
    if trade_ids:
        # Children first: a proposal's rule results, evaluations, reports and assets.
        for child in (TradeRuleResult, TradeEvaluation, GeneratedReport, TradeAsset, TradeTeam):
            for row in db.scalars(
                select(child).where(child.trade_id.in_(trade_ids))
            ).all():
                db.delete(row)
    for entity_id, _ in found["comparisons"]:
        _delete(db, ComparisonSet, entity_id)
    for entity_id, _ in found["trades"]:
        _delete(db, TradeProposal, entity_id)
    for entity_id, _ in found["scenarios"]:
        _delete(db, Scenario, entity_id)

    # Comparison sets store trade ids as a JSON list, so removing a proposal can leave a
    # set pointing at nothing. A dangling reference is worse than the row it replaced —
    # the comparison would 404 as a whole — so the survivors are repaired here.
    summary["repaired_comparisons"] = _repair_comparisons(db, set(trade_ids))
    db.commit()
    return summary


def _repair_comparisons(db: Session, removed_trade_ids: set[str]) -> dict[str, int]:
    """Drop removed ids from every comparison set, and delete sets left uncomparable."""
    live = {t.id for t in db.scalars(select(TradeProposal)).all()}
    pruned = 0
    deleted = 0
    for comparison in db.scalars(select(ComparisonSet)).all():
        ids = list(comparison.trade_ids or [])
        kept = [tid for tid in ids if tid in live]
        if kept == ids:
            continue
        if len(kept) < 2:
            db.delete(comparison)
            deleted += 1
        else:
            comparison.trade_ids = kept
            pruned += 1
    _ = removed_trade_ids  # reported by the caller; recomputed from `live` for safety
    return {"pruned": pruned, "deleted": deleted}


def _delete(db: Session, model: type, entity_id: str) -> None:
    entity = db.get(model, entity_id)
    if entity is not None:
        db.delete(entity)
