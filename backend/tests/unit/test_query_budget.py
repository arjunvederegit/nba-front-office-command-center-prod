"""Query budgets for the two hot paths (R2a).

Measured on the live database at `f16dedc`, with `contracts` at **0 rows** — the
cheapest possible case, because a missing contract is one query that returns nothing:

    POST /trades/evaluate  (2-for-2)        61 queries
    POST /trades/generate  (focal BOS)   21,326 queries in 2.15 s

16,640 of those were the same `SELECT … FROM contracts WHERE player_id = ?` and 1,169
were `SELECT … FROM league_cap_parameters` for one immutable row. The plan measured
47,158 queries / 5.17 s with contract data loaded; on the compose Postgres path that is
7–14 s of pure round-trip latency, which is why the budget is expressed in *queries*
rather than seconds — SQLite hides the cost that matters.

These numbers are ceilings, not targets. They exist so a re-introduced N+1 fails a test
instead of being noticed in production.
"""

import contextlib

import pytest
from sqlalchemy import event, select
from sqlalchemy.orm import Session

from app.cba.builder import build_trade_context
from app.cba.engine import TradeLegalityEngine
from app.services.candidates import generate_candidates
from app.services.evaluation import EvaluationService

EVALUATE_BUDGET = 25  # baseline 61
GENERATE_BUDGET = 3_000  # baseline 21,326


@contextlib.contextmanager
def counting(db: Session):
    counts = {"n": 0}
    engine = db.get_bind()

    def _count(*_args, **_kwargs):
        counts["n"] += 1

    event.listen(engine, "before_cursor_execute", _count)
    try:
        yield counts
    finally:
        event.remove(engine, "before_cursor_execute", _count)


def _moves(league: dict, n: int) -> list[dict]:
    a, b = league["team_a"], league["team_b"]
    return [
        *[
            {"player_id": p.id, "from_team_id": a.id, "to_team_id": b.id}
            for p in league["roster_a"][:n]
        ],
        *[
            {"player_id": p.id, "from_team_id": b.id, "to_team_id": a.id}
            for p in league["roster_b"][:n]
        ],
    ]


def test_a_two_for_two_evaluation_stays_within_budget(db: Session, seeded_league: dict) -> None:
    team_ids = [seeded_league["team_a"].id, seeded_league["team_b"].id]
    moves = _moves(seeded_league, 2)
    service = EvaluationService(db)
    service._skills()  # warm the feature frame; it is cached and not the subject here

    with counting(db) as counts:
        context = build_trade_context(db, team_ids, moves, [])
        legality = TradeLegalityEngine().evaluate(context)
        for team_id in team_ids:
            service.evaluate_for_team(team_id, team_ids, moves, [], "contend", None, legality)

    assert counts["n"] <= EVALUATE_BUDGET, (
        f"{counts['n']} queries for a 2-for-2 evaluation (budget {EVALUATE_BUDGET}, "
        f"baseline 61) — an N+1 has come back"
    )


def test_candidate_generation_stays_within_budget(db: Session, seeded_league: dict) -> None:
    service = EvaluationService(db)
    service._skills()

    with counting(db) as counts:
        generate_candidates(db, seeded_league["team_a"].id, strategy="contend")

    assert counts["n"] <= GENERATE_BUDGET, (
        f"{counts['n']} queries to generate candidates (budget {GENERATE_BUDGET}, "
        f"baseline 21,326)"
    )


def test_cap_parameters_are_fetched_once_per_session(db: Session, seeded_league: dict) -> None:
    """1,169 identical `SELECT … FROM league_cap_parameters` in one request."""
    from app.cba.builder import load_cap_params
    from app.db.models import LeagueCapParameters

    with counting(db) as counts:
        for _ in range(50):
            load_cap_params(db, "2026-27")
    assert counts["n"] == 1

    # …and a write invalidates it, so a cache can never serve a stale row.
    row = db.scalar(select(LeagueCapParameters))
    assert row is not None
    row.salary_cap += 1
    db.commit()
    with counting(db) as counts:
        load_cap_params(db, "2026-27")
    assert counts["n"] == 1, "the cache survived a commit"


def test_salaries_are_batched_not_per_player(db: Session, seeded_league: dict) -> None:
    from app.cba.builder import player_salaries

    player_ids = [p.id for p in seeded_league["roster_a"]]
    with counting(db) as counts:
        resolved = player_salaries(db, player_ids, "2026-27")
    assert set(resolved) == set(player_ids)
    # Three, and constant in the batch size: contracts, their years for the league
    # year, and one `selectin` load of `Contract.years` from the relationship. The
    # point is that none of them scales with the number of players — the path this
    # replaces was two queries *each*.
    assert counts["n"] <= 3, f"{counts['n']} queries for {len(player_ids)} players"

    with counting(db) as counts:
        player_salaries(db, player_ids, "2026-27")
    assert counts["n"] == 0, "a repeat lookup re-queried"


def test_batched_salaries_agree_with_the_per_player_path(db: Session, seeded_league: dict) -> None:
    """The optimisation must not change a single answer."""
    from app.cba import resolver
    from app.cba.builder import _player_salary, player_salaries

    player_ids = [p.id for p in seeded_league["roster_a"] + seeded_league["roster_b"]]
    batched = player_salaries(db, player_ids, "2026-27")
    resolver.reset(db)
    for pid in player_ids:
        resolver.reset(db)
        assert _player_salary(db, pid, "2026-27")[0] == batched[pid][0]


def test_payroll_is_memoized_per_team(db: Session, seeded_league: dict) -> None:
    from app.cba.builder import _team_payroll

    with counting(db) as first:
        payroll = _team_payroll(db, seeded_league["team_a"].id, "2025-26", "2026-27")
    with counting(db) as second:
        again = _team_payroll(db, seeded_league["team_a"].id, "2025-26", "2026-27")
    assert payroll == again
    assert first["n"] > 0 and second["n"] == 0
    # AAA[13] has no contract. The *verified* payroll is therefore still unavailable —
    # that rule is deliberate and survived both the batching and R2c — while the known
    # sum and its coverage are now carried instead of discarded.
    assert payroll.verified is None
    assert payroll.complete is False
    assert payroll.players_total == 15
    assert payroll.players_known == 14
    assert payroll.players_unknown == 1
    assert payroll.known > 0


@pytest.mark.parametrize("reverse", [False, True])
def test_the_simulation_does_not_depend_on_player_order(reverse: bool) -> None:
    """Each player draws from a stream keyed on identity, not position.

    A shared generator consumed in list order meant the same trade produced different
    numbers depending on the order players happened to arrive in — which was database
    order until `_roster_cards` gained an `ORDER BY`.
    """
    from app.analytics.uncertainty import PlayerDraw, simulate_delta_wins

    incoming = [
        PlayerDraw(2.1, 1.2, 0.9, 0.1, key="p1"),
        PlayerDraw(-0.4, 1.5, 0.7, 0.06, key="p2"),
        PlayerDraw(1.0, 0.9, 0.85, 0.08, key="p3"),
    ]
    outgoing = [PlayerDraw(0.5, 1.1, 0.8, 0.09, key="p4")]
    mapping = {"slope": 2.235}

    baseline = simulate_delta_wins(incoming, outgoing, mapping)
    shuffled = simulate_delta_wins(
        list(reversed(incoming)) if reverse else incoming[1:] + incoming[:1],
        outgoing,
        mapping,
    )
    for field in ("median", "p10", "p90", "prob_positive"):
        assert baseline[field] == pytest.approx(shuffled[field]), field


def test_the_batch_cost_does_not_scale_with_roster_size(db: Session, seeded_league: dict) -> None:
    """The claim the budget rests on: one player or thirty, the query count is the same."""
    from app.cba import resolver
    from app.cba.builder import player_salaries

    everyone = [p.id for p in seeded_league["roster_a"] + seeded_league["roster_b"]]

    resolver.reset(db)
    with counting(db) as one:
        player_salaries(db, everyone[:1], "2026-27")
    resolver.reset(db)
    with counting(db) as many:
        player_salaries(db, everyone, "2026-27")

    assert len(everyone) == 30
    assert many["n"] == one["n"], f"{one['n']} queries for 1 player, {many['n']} for 30"
